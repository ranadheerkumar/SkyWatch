import asyncio
import concurrent.futures
import json
import logging
import os
import re
from datetime import datetime, timezone
from threading import Thread

from app.core.database import SessionLocal
from app.models.ai_generation_job import AIGenerationJob
from app.models.application import Application
from app.models.test_case import TestCase
from app.models.test_case_automation import TestCaseAutomation
from app.services.automation_builder import build_case_automation_from_text
from app.services.ai_service import (
    _extract_credentials_from_text,
    _extract_target_url_from_text,
    discover_application_context,
    extract_intake_signals_with_ai,
    generate_ai_test_cases,
    generate_ai_test_plan,
    serialize_target_ui_context,
)
from app.services.ai_generation_pipeline import (
    build_context_snapshot,
    build_planner_snapshot,
    build_scenario_snapshot,
    build_validation_snapshot,
    initial_agent_stages,
    initial_workflow_result,
    update_agent_stages,
)
from app.services.guardrails import GuardrailViolationError, sanitize_and_validate_prompt, validate_target_url
from app.services.generation_logger import GenerationLogger, get_active_generation_logger
from app.services.self_learning import SelfLearningEngine
from app.services.test_data_generator import TestDataGeneratorService

logger = logging.getLogger("ai-qa-engine.ai_generation_jobs")


class AIQueueUnavailableError(RuntimeError):
    pass


def _run_coro_sync(coro):
    """Safely executes an async coroutine from synchronous background worker threads."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()


def _set_job_stage(
    db,
    job: AIGenerationJob,
    stages: list[dict],
    stage_key: str,
    *,
    status: str,
    detail: str,
    progress: int,
    metrics: dict | None = None,
) -> list[dict]:
    next_stages = update_agent_stages(
        stages,
        stage_key,
        status=status,
        detail=detail,
        progress=progress,
        metrics=metrics,
    )
    job.phase = stage_key
    active_logger = get_active_generation_logger(job.id)
    current_logs = (job.result or {}).get("logs", [])
    if active_logger:
        current_logs = active_logger.get_entries()
    job.result = {**(job.result or {}), "agent_stages": next_stages, "logs": current_logs}
    db.commit()
    return next_stages


def _run_job(job_id: str) -> None:
    db = SessionLocal()
    job: AIGenerationJob | None = None
    gen_logger: GenerationLogger | None = None
    agent_stages = initial_agent_stages()
    current_stage_key = "document_analysis"
    try:
        job = db.get(AIGenerationJob, job_id)
        if not job:
            return
        gen_logger = GenerationLogger(job_id=job.id, db=db, correlation_id=job.correlation_id or "")
        job.status = "running"
        job.phase = current_stage_key
        job.started_at = datetime.now(timezone.utc)
        job.result = {**initial_workflow_result(), "logs": gen_logger.get_entries()}
        agent_stages = job.result["agent_stages"]
        db.commit()

        application = db.get(Application, job.application_id)
        if not application:
            raise ValueError("Application not found")
        gen_logger.info(
            f"AI Generation job started for application '{application.name}' (target: {application.target or 'N/A'})",
            provider=job.provider or "auto",
            model=job.model or "auto",
        )
        payload = job.request_payload
        raw_document_context = (payload.get("document_context") or "").strip()[:60_000]
        raw_jira_context = (payload.get("jira_context") or "").strip()[:60_000]
        jira_key = (payload.get("jira_key") or "").strip()

        if raw_jira_context and raw_document_context:
            document_context = f"{raw_jira_context}\n\n---\n\n{raw_document_context}"[:60_000]
        elif raw_jira_context:
            document_context = raw_jira_context
        else:
            document_context = raw_document_context

        document_names = [str(name).strip() for name in (payload.get("document_names") or []) if str(name).strip()]
        if document_names and not raw_document_context and not raw_jira_context:
            raise ValueError(
                "Uploaded requirement document text could not be extracted. "
                "Review the document analysis warnings and upload a readable text-based file."
            )
        reference_case_rows = (
            db.query(TestCase.title, TestCase.steps, TestCase.expected_result)
            .filter(
                TestCase.application_id == application.id,
                TestCase.created_by == job.created_by,
            )
            .order_by(TestCase.updated_at.desc(), TestCase.id.desc())
            .limit(12)
            .all()
        )
        reference_cases = []
        for row in reference_case_rows:
            title = (row.title or "").strip()
            first_step = next((line.strip() for line in (row.steps or "").splitlines() if line.strip()), "")
            expected_result = (row.expected_result or "").strip()
            snippet = " | ".join(part for part in (title, first_step, expected_result) if part)
            if snippet:
                reference_cases.append(snippet[:300])

        stage_metrics: dict[str, Any] = {"document_context_chars": len(document_context)}
        if jira_key:
            stage_metrics["jira_key"] = jira_key
        if raw_jira_context:
            stage_metrics["jira_context_chars"] = len(raw_jira_context)

        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="running",
            detail=f"Extracting requirements{f' from Jira issue {jira_key}' if jira_key else ''}, credentials, target URL, parameters, and risk signals with AI Document Analysis.",
            progress=15,
            metrics=stage_metrics,
        )

        intake_signals = _run_coro_sync(
            extract_intake_signals_with_ai(
                prompt=payload["prompt"],
                document_context=document_context,
                provider=payload.get("provider"),
                model=payload.get("model"),
            )
        )

        prompt_target_url = intake_signals.get("target_url") or _extract_target_url_from_text(payload.get("prompt"), document_context)
        effective_target = (payload.get("target_url") or prompt_target_url or application.target or "").strip()

        from app.api.v1.execution import _resolve_application_credentials_and_parameters
        app_creds = _resolve_application_credentials_and_parameters(db, application, None)

        extracted_email = intake_signals.get("username")
        extracted_password = intake_signals.get("password")
        if not extracted_email or not extracted_password:
            regex_email, regex_password = _extract_credentials_from_text(payload.get("prompt"), document_context)
            extracted_email = extracted_email or regex_email
            extracted_password = extracted_password or regex_password

        resolved_job_email = payload.get("login_email") or extracted_email or app_creds.get("login_email")
        resolved_job_password = payload.get("login_password") or extracted_password or app_creds.get("login_password")
        job_include_authenticated = payload.get("include_authenticated_snapshot", False) or bool(resolved_job_email and resolved_job_password)

        login_email_sel = payload.get("login_email_selector") or intake_signals.get("login_email_selector")
        login_password_sel = payload.get("login_password_selector") or intake_signals.get("login_password_selector")
        login_submit_sel = payload.get("login_submit_selector") or intake_signals.get("login_submit_selector")

        context_snapshot = build_context_snapshot(
            application_name=application.name,
            platform=application.platform,
            target=effective_target,
            prompt=payload["prompt"],
            document_context=document_context,
            reference_cases=reference_cases,
        )
        if intake_signals.get("modules"):
            existing_modules = context_snapshot.get("modules") or []
            merged_modules = list(dict.fromkeys([*intake_signals["modules"], *existing_modules]))
            context_snapshot["modules"] = merged_modules[:30]
        if intake_signals.get("requirements"):
            context_snapshot["requirements_found"] = max(context_snapshot.get("requirements_found", 0), len(intake_signals["requirements"]))
        if intake_signals.get("workflows"):
            context_snapshot["workflow_signals"] = max(context_snapshot.get("workflow_signals", 0), len(intake_signals["workflows"]))
        if intake_signals.get("risk_signals"):
            context_snapshot["risk_signals"] = list(dict.fromkeys([*context_snapshot.get("risk_signals", []), *intake_signals["risk_signals"]]))[:16]
        if intake_signals.get("runtime_parameters"):
            context_snapshot["runtime_parameters"] = intake_signals["runtime_parameters"]

        learning_metrics = SelfLearningEngine.get_telemetry_metrics(application.id)
        context_snapshot["self_learning_metrics"] = learning_metrics

        vector_chunks_indexed = 0
        if document_context.strip():
            try:
                from app.services.vector_service import VectorStoreService
                from app.services.document_analysis import DocumentFileAnalysis, chunk_document_analyses
                vstore = VectorStoreService(application.id)
                doc_blocks = re.split(r"\n+(?=DOCUMENT:\s*)", document_context)
                synthetic_analyses = []
                for block in doc_blocks:
                    block = block.strip()
                    if not block:
                        continue
                    m = re.match(r"^DOCUMENT:\s*([^\n]+)\n+(.*)", block, re.DOTALL)
                    if m:
                        fname = m.group(1).strip()
                        ftext = m.group(2).strip()
                    else:
                        fname = "specification.md"
                        ftext = block
                    synthetic_analyses.append(DocumentFileAnalysis(
                        filename=fname,
                        extension="." + (fname.split(".")[-1] if "." in fname else "md"),
                        size_bytes=len(ftext.encode("utf-8")),
                        pages_parsed=1,
                        requirements_found=1,
                        features_identified=1,
                        modules_identified=[],
                        business_rules_found=1,
                        workflows_discovered=1,
                        extracted_characters=len(ftext),
                        warnings=[],
                        text=ftext,
                    ))
                chunks = chunk_document_analyses(synthetic_analyses)
                if chunks:
                    vector_chunks_indexed = _run_coro_sync(vstore.index_document_chunks(chunks))
            except Exception as v_err:
                logger.warning("Vector indexing skipped during document analysis: %s", v_err)

        job.result = {
            **(job.result or {}),
            "application_context": context_snapshot,
            "intake_signals": intake_signals,
            "vector_chunks_indexed": vector_chunks_indexed,
        }
        if gen_logger:
            gen_logger.step(
                f"Document analysis completed: extracted {context_snapshot['requirements_found']} requirement(s), {len(context_snapshot['modules'])} module(s), indexed {vector_chunks_indexed} vector chunk(s)",
                requirements_count=context_snapshot["requirements_found"],
                modules_count=len(context_snapshot["modules"]),
            )
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="completed",
            detail=f"AI Document Analysis extracted {context_snapshot['requirements_found']} requirement(s), {len(context_snapshot['modules'])} module(s), and indexed {vector_chunks_indexed} vector chunk(s).",
            progress=100,
            metrics={
                "requirements_found": context_snapshot["requirements_found"],
                "module_count": len(context_snapshot["modules"]),
                "risk_signal_count": len(context_snapshot["risk_signals"]),
                "vector_chunks_indexed": vector_chunks_indexed,
                "has_credentials": bool(resolved_job_email and resolved_job_password),
                "target_url": effective_target,
            },
        )

        current_stage_key = "application_discovery"
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="running",
            detail="Inspecting the authorized target, then exercising bounded safe controls for exploratory workflow signals.",
            progress=20,
        )
        discovery_context = _run_coro_sync(
            discover_application_context(
                effective_target,
                include_authenticated_snapshot=job_include_authenticated,
                login_email_selector=login_email_sel,
                login_password_selector=login_password_sel,
                login_submit_selector=login_submit_sel,
                login_email=resolved_job_email,
                login_password=resolved_job_password,
            )
        )
        discovery_snapshot = serialize_target_ui_context(discovery_context)
        context_snapshot = build_context_snapshot(
            application_name=application.name,
            platform=application.platform,
            target=effective_target,
            prompt=payload["prompt"],
            document_context=document_context,
            reference_cases=reference_cases,
            discovery_snapshot=discovery_snapshot,
        )
        if intake_signals.get("modules"):
            existing_modules = context_snapshot.get("modules") or []
            merged_modules = list(dict.fromkeys([*intake_signals["modules"], *existing_modules]))
            context_snapshot["modules"] = merged_modules[:30]
        if intake_signals.get("requirements"):
            context_snapshot["requirements_found"] = max(context_snapshot.get("requirements_found", 0), len(intake_signals["requirements"]))
        if intake_signals.get("workflows"):
            context_snapshot["workflow_signals"] = max(context_snapshot.get("workflow_signals", 0), len(intake_signals["workflows"]))
        if intake_signals.get("risk_signals"):
            context_snapshot["risk_signals"] = list(dict.fromkeys([*context_snapshot.get("risk_signals", []), *intake_signals["risk_signals"]]))[:16]
        if intake_signals.get("runtime_parameters"):
            context_snapshot["runtime_parameters"] = intake_signals["runtime_parameters"]
        job.result = {
            **(job.result or {}),
            "discovery": discovery_snapshot,
            "application_context": context_snapshot,
        }
        if gen_logger:
            gen_logger.step(
                f"Target discovery completed: found {len(discovery_context.headings)} headings, {len(discovery_context.buttons) + len(discovery_context.links)} controls on {effective_target}",
                target_url=effective_target,
                headings_count=len(discovery_context.headings),
                controls_count=len(discovery_context.buttons) + len(discovery_context.links),
            )
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="completed",
            detail=(
                f"Discovery captured {len(discovery_context.headings)} headings, "
                f"{len(discovery_context.buttons) + len(discovery_context.links)} controls, "
                f"{len(discovery_context.observed_routes)} route signal(s), and "
                f"{len(discovery_context.exploratory_observations)} bounded exploratory observation(s)."
            ),
            progress=100,
            metrics={
                "heading_count": len(discovery_context.headings),
                "control_count": len(discovery_context.buttons) + len(discovery_context.links),
                "input_hint_count": len(discovery_context.input_hints),
                "route_count": len(discovery_context.observed_routes),
                "exploratory_observation_count": len(discovery_context.exploratory_observations),
                "exploratory_hypothesis_count": len(discovery_context.exploratory_hypotheses),
            },
        )

        # Auto-learn live entities from discovered headings, controls, inputs, and hints
        try:
            learner = SelfLearningEngine(application.id)
            harvest_signals = " ".join([
                discovery_context.title,
                *discovery_context.headings,
                *discovery_context.buttons,
                *discovery_context.links,
                *discovery_context.input_hints,
                *discovery_context.exploratory_observations,
            ])
            if harvest_signals.strip():
                learner.harvest_text_signals(harvest_signals)
        except Exception as harvest_err:
            logger.warning("Discovery entity harvesting skipped: %s", harvest_err)

        current_stage_key = "context_builder"
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="running",
            detail="Combining application, document, and reference-case signals.",
            progress=25,
        )
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="completed",
            detail="Application context, exploratory findings, and module relationships prepared.",
            progress=100,
            metrics={"module_count": len(context_snapshot["modules"]), "reference_case_count": len(reference_cases)},
        )

        current_stage_key = "playwright_planner"
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="running",
            detail="Mapping entry points, navigation paths, exploratory findings, coverage, and exit criteria.",
            progress=40,
        )
        planner_result = _run_coro_sync(
            generate_ai_test_plan(
                application_name=application.name,
                platform=application.platform,
                target=effective_target,
                user_prompt=payload["prompt"],
                max_cases=payload.get("max_cases"),
                module_focus=payload.get("module_focus") or "",
                include_negative_scenarios=payload.get("include_negative_scenarios", True),
                include_accessibility_checks=payload.get("include_accessibility_checks", True),
                include_api_validations=payload.get("include_api_validations", False),
                include_performance_scenarios=payload.get("include_performance_scenarios", False),
                performance_budget=payload.get("performance_budget") or "",
                input_format=payload.get("input_format", "text"),
                include_positive_scenarios=payload.get("include_positive_scenarios", True),
                include_boundary_scenarios=payload.get("include_boundary_scenarios", True),
                include_edge_cases=payload.get("include_edge_cases", True),
                include_security_scenarios=payload.get("include_security_scenarios", True),
                include_validation_rules=payload.get("include_validation_rules", True),
                document_context=document_context,
                reference_cases=reference_cases,
                context_snapshot=context_snapshot,
                observed_target_context=json.dumps(discovery_snapshot, ensure_ascii=True),
                provider=payload.get("provider"),
                model=payload.get("model"),
            )
        )
        ai_planner_plan = planner_result["plan"]
        planner_snapshot = {
            **build_planner_snapshot(
                target=effective_target,
                context=context_snapshot,
            ),
            "ai_plan": ai_planner_plan,
            "ai_provider": planner_result.get("provider"),
            "ai_model": planner_result.get("model"),
            "planner_used": True,
        }
        job.result = {**(job.result or {}), "planner": planner_snapshot}
        if gen_logger:
            gen_logger.llm(
                f"AI Planner completed: synthesized {ai_planner_plan['recommended_case_count']} scenario blueprint(s) across {len(ai_planner_plan['coverage_matrix'])} coverage area(s)",
                provider=planner_result.get("provider"),
                model=planner_result.get("model"),
                case_target=ai_planner_plan["recommended_case_count"],
            )
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="completed",
            detail=f"AI Planner prepared a {ai_planner_plan['recommended_case_count']}-case coverage target and Playwright-oriented execution plan.",
            progress=100,
            metrics={
                "entry_point_count": len(planner_snapshot["entry_points"]),
                "planned_module_count": len(planner_snapshot["navigation_plan"]),
                "recommended_case_count": ai_planner_plan["recommended_case_count"],
                "coverage_area_count": len(ai_planner_plan["coverage_matrix"]),
                "exploratory_charter_count": len(ai_planner_plan.get("exploratory_charters") or []),
                "provider": str(planner_result.get("provider") or "unknown"),
            },
        )

        current_stage_key = "scenario_agent"
        scenario_snapshot = build_scenario_snapshot(payload, context_snapshot, ai_planner_plan)
        job.result = {**(job.result or {}), "scenario_plan": scenario_snapshot}
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="running",
            detail="Selecting positive, negative, boundary, edge, exploratory, security, and accessibility coverage.",
            progress=55,
        )
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="completed",
            detail="Scenario coverage categories are ready for generation.",
            progress=100,
            metrics={"category_count": len(scenario_snapshot["categories"])},
        )

        current_stage_key = "test_case_generator"
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="running",
            detail="Generating structured test cases from source context and exploratory charters.",
            progress=65,
        )
        generated = _run_coro_sync(
            generate_ai_test_cases(
                application_name=application.name,
                platform=application.platform,
                target=effective_target,
                user_prompt=payload["prompt"],
                max_cases=payload.get("max_cases"),
                include_authenticated_snapshot=job_include_authenticated,
                login_email=resolved_job_email,
                login_password=resolved_job_password,
                login_email_selector=login_email_sel,
                login_password_selector=login_password_sel,
                login_submit_selector=login_submit_sel,
                min_steps_per_case=payload.get("min_steps_per_case", 2),
                max_steps_per_case=payload.get("max_steps_per_case", 15),
                include_negative_scenarios=payload.get("include_negative_scenarios", True),
                include_accessibility_checks=payload.get("include_accessibility_checks", True),
                include_api_validations=payload.get("include_api_validations", False),
                include_performance_scenarios=payload.get("include_performance_scenarios", False),
                performance_budget=payload.get("performance_budget") or "",
                input_format=payload.get("input_format", "text"),
                include_positive_scenarios=payload.get("include_positive_scenarios", True),
                include_boundary_scenarios=payload.get("include_boundary_scenarios", True),
                include_edge_cases=payload.get("include_edge_cases", True),
                include_security_scenarios=payload.get("include_security_scenarios", True),
                include_validation_rules=payload.get("include_validation_rules", True),
                module_focus=payload.get("module_focus") or "",
                document_context=document_context,
                reference_cases=reference_cases,
                provider=payload.get("provider"),
                model=payload.get("model"),
                planner_plan=ai_planner_plan,
                planner_provider=str(planner_result.get("provider") or "") or None,
                planner_model=str(planner_result.get("model") or "") or None,
                context_snapshot=context_snapshot,
                observed_target_context=discovery_context,
            )
        )
        if gen_logger:
            gen_logger.llm(
                f"AI Generator produced {len(generated.test_cases)} structured test cases across {generated.generator_call_count} provider call(s)",
                provider=generated.generation_provider or job.provider,
                candidate_count=len(generated.test_cases),
                call_count=generated.generator_call_count,
            )
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="completed",
            detail=f"AI Generator produced {len(generated.test_cases)} structured candidates across {generated.generator_call_count} provider call{'s' if generated.generator_call_count != 1 else ''}.",
            progress=100,
            metrics={
                "candidate_count": len(generated.test_cases),
                "target_case_count": generated.planner_case_target,
                "generator_call_count": generated.generator_call_count,
                "exploratory_charter_count": len(scenario_snapshot.get("exploratory_charters") or []),
            },
        )

        current_stage_key = "test_data_generator"
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="running",
            detail="Synthesizing realistic valid, invalid, boundary, and edge test datasets informed by live application entities.",
            progress=75,
        )
        data_generator = TestDataGeneratorService(application.id)
        raw_fields = intake_signals.get("runtime_parameters") or [
            "first_name", "last_name", "email", "phone", "order_id", "status"
        ]
        if isinstance(raw_fields, dict):
            extracted_fields = list(raw_fields.keys())
        elif isinstance(raw_fields, list):
            extracted_fields = [str(f) for f in raw_fields if isinstance(f, str)]
        else:
            extracted_fields = ["first_name", "last_name", "email", "phone", "order_id", "status"]
        if not extracted_fields:
            extracted_fields = ["first_name", "last_name", "email", "phone", "order_id", "status"]

        # Extract runtime placeholders requested across generated test cases to synthesize complete data coverage
        case_placeholders: list[str] = []
        for tc in generated.test_cases:
            for match in re.findall(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", tc.steps or ""):
                m_clean = match.strip()
                if m_clean.lower() not in {"login_email", "login_password"} and m_clean not in case_placeholders:
                    case_placeholders.append(m_clean)

        combined_fields = list(dict.fromkeys([*extracted_fields, *case_placeholders]))

        data_rows = _run_coro_sync(
            data_generator.generate_dataset(
                dataset_name=f"{application.name} Smart Test Data Matrix",
                description=f"Generated by Test Data Generator Agent for {application.name}",
                field_names=combined_fields[:16],
                scenario_types=["valid", "invalid", "boundary", "edge"],
                row_count=min(12, max(6, len(generated.test_cases))),
                provider=payload.get("provider"),
                model=payload.get("model"),
            )
        )
        if data_rows:
            try:
                from app.models.test_dataset import TestDataset
                existing_ds = db.query(TestDataset).filter(
                    TestDataset.application_id == application.id,
                    TestDataset.created_by == job.created_by,
                ).first()
                if existing_ds:
                    existing_ds.data_rows = data_rows
                    existing_ds.name = f"{application.name} Smart Test Data Matrix"
                    existing_ds.description = f"Generated by Test Data Generator Agent for {application.name}"
                else:
                    new_ds = TestDataset(
                        application_id=application.id,
                        created_by=job.created_by,
                        name=f"{application.name} Smart Test Data Matrix",
                        description=f"Generated by Test Data Generator Agent for {application.name}",
                        data_rows=data_rows,
                    )
                    db.add(new_ds)
                db.flush()
            except Exception as ds_err:
                logger.warning("Test dataset persistence skipped: %s", ds_err)

        test_data_plan = {
            "dataset_name": f"{application.name} Smart Test Data Matrix",
            "row_count": len(data_rows),
            "field_names": combined_fields[:16],
            "sample_rows": data_rows[:4],
        }
        job.result = {**(job.result or {}), "test_data_plan": test_data_plan}
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="completed",
            detail=f"Test Data Generator Agent synthesized {len(data_rows)} realistic test data row(s) covering valid, invalid, boundary, and edge scenarios.",
            progress=100,
            metrics={
                "row_count": len(data_rows),
                "field_count": len(combined_fields[:16]),
                "scenarios": ["valid", "invalid", "boundary", "edge"],
            },
        )

        current_stage_key = "validation_agent"
        validation_snapshot = build_validation_snapshot(
            generated.test_cases,
            min_steps=payload.get("min_steps_per_case", 2),
            max_steps=payload.get("max_steps_per_case", 15),
        )
        job.result = {**(job.result or {}), "validation": validation_snapshot}
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="running",
            detail="Checking completeness, duplicate journeys, and requested step bounds.",
            progress=85,
        )
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="completed",
            detail=f"Validation completed with a {validation_snapshot['coverage_score']}% coverage score.",
            progress=100,
            metrics=validation_snapshot,
        )

        current_stage_key = "repository"
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="running",
            detail="Persisting validated cases and compiling executable automation.",
            progress=92,
        )
        if payload.get("replace_existing_drafts"):
            draft_ids = [
                case_id
                for (case_id,) in db.query(TestCase.id).filter(
                    TestCase.application_id == application.id,
                    TestCase.created_by == job.created_by,
                    TestCase.status == "draft",
                ).all()
            ]
            if draft_ids:
                db.query(TestCaseAutomation).filter(TestCaseAutomation.test_case_id.in_(draft_ids)).delete(synchronize_session=False)
                db.query(TestCase).filter(TestCase.id.in_(draft_ids)).delete(synchronize_session=False)

        existing_titles = {
            title.strip().casefold()
            for (title,) in db.query(TestCase.title).filter(
                TestCase.application_id == application.id,
                TestCase.created_by == job.created_by,
            ).all()
        }
        existing_case_numbers = [
            int(match.group(1))
            for title in existing_titles
            if (match := re.match(r"^tc\s*0*(\d+)\s*[-:]", title, re.IGNORECASE))
        ]
        next_case_number = max(existing_case_numbers, default=0) + 1
        created = []
        for idx, item in enumerate(generated.test_cases):
            title_suffix = re.sub(r"^TC\s*\d+\s*[-:]\s*", "", item.title.strip(), flags=re.IGNORECASE).strip()
            if not title_suffix:
                continue
            while True:
                title = f"TC{next_case_number:02d} - {title_suffix}"
                next_case_number += 1
                if title.casefold() not in existing_titles:
                    break
            case_data_dict: dict[str, str] = {}
            if item.test_data and isinstance(item.test_data, dict):
                case_data_dict.update({str(k): str(v) for k, v in item.test_data.items() if not str(k).startswith("_") and str(v).strip()})
            if data_rows:
                case_cat = (item.category or "positive").lower()
                target_scenario = (
                    "invalid" if case_cat in {"negative", "security"} or "invalid" in item.title.lower() or "error" in item.title.lower()
                    else "boundary" if case_cat == "boundary"
                    else "edge" if case_cat in {"edge", "exploratory"}
                    else "valid"
                )
                matching_rows = [r for r in data_rows if r.get("_scenario") == target_scenario] or [r for r in data_rows if r.get("_scenario") == "valid"] or data_rows
                case_row = matching_rows[idx % len(matching_rows)]
                if isinstance(case_row, dict):
                    for k, v in case_row.items():
                        if not str(k).startswith("_") and str(v).strip() and str(k) not in case_data_dict:
                            case_data_dict[str(k)] = str(v)
            case_data = json.dumps(case_data_dict) if case_data_dict else None
            case = TestCase(
                application_id=application.id,
                created_by=job.created_by,
                title=title,
                description=item.description,
                preconditions=item.preconditions,
                steps=item.steps,
                expected_result=item.expected_result,
                status=item.status,
                priority=item.priority,
                category=item.category,
                tags=item.tags,
                test_data=case_data,
            )
            db.add(case)
            created.append(case)
            existing_titles.add(title.casefold())
        db.flush()
        for case in created:
            steps, checks = build_case_automation_from_text(
                case,
                application,
                login_email_selector=payload.get("login_email_selector"),
                login_password_selector=payload.get("login_password_selector"),
                login_submit_selector=payload.get("login_submit_selector"),
            )
            if not steps and not checks:
                continue
            db.add(TestCaseAutomation(test_case_id=case.id, steps=steps, checks=checks, updated_by=job.created_by))

        # Index created test cases in vector database for semantic retrieval and deduplication
        try:
            from app.services.vector_service import VectorStoreService
            vstore = VectorStoreService(application.id)
            for case in created:
                _run_coro_sync(vstore.index_test_case(
                    case_id=case.id,
                    title=case.title,
                    steps=case.steps or "",
                    expected_result=case.expected_result,
                    description=case.description,
                ))
        except Exception as v_err:
            logger.warning("Vector indexing for test cases skipped: %s", v_err)

        job.status = "completed"
        job.phase = "completed"
        job.generated_count = len(generated.test_cases)
        job.valid_count = len(created)
        job.review_count = sum(1 for item in created if item.status == "draft")
        job.provider = generated.generation_provider or job.provider
        job.result = {
            **(job.result or {}),
            "summary": generated.summary,
            "generation_mode": generated.generation_mode,
            "generation_note": generated.generation_note,
            "generation_provider": generated.generation_provider,
            "document_names": payload.get("document_names") or [],
            "planner_used": generated.planner_used,
            "planner_provider": generated.planner_provider,
            "planner_model": generated.planner_model,
            "planner_case_target": generated.planner_case_target,
            "generator_call_count": generated.generator_call_count,
            "case_ids": [item.id for item in created],
        }
        job.finished_at = datetime.now(timezone.utc)
        agent_stages = _set_job_stage(
            db,
            job,
            agent_stages,
            current_stage_key,
            status="completed",
            detail="Validated cases and automation are available in the repository.",
            progress=100,
            metrics={"persisted_case_count": len(created), "review_count": job.review_count},
        )
        if gen_logger:
            gen_logger.info(
                f"AI Generation job completed successfully: {len(created)} test cases created (IDs: {[c.id for c in created]})",
                persisted_count=len(created),
                review_count=job.review_count,
            )
        job.status = "completed"
        job.phase = "completed"
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as error:
        db.rollback()
        if gen_logger:
            gen_logger.error(
                f"AI Generation failed at stage '{current_stage_key}': {type(error).__name__}: {error}",
                stage=current_stage_key,
                error_type=type(error).__name__,
            )
        failed_job = db.get(AIGenerationJob, job_id)
        if failed_job:
            failed_job.status = "failed"
            failed_job.phase = "failed"
            failed_job.error = f"{type(error).__name__}: {error}"
            result = failed_job.result or {}
            result["agent_stages"] = update_agent_stages(
                agent_stages,
                current_stage_key,
                status="failed",
                detail=f"Stage failed: {type(error).__name__}.",
                progress=0,
            )
            if gen_logger:
                result["logs"] = gen_logger.get_entries()
            failed_job.result = result
            failed_job.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        if gen_logger:
            gen_logger.close(job=job)
        db.close()


def enqueue_ai_generation(job_id: str) -> None:
    backend = os.getenv("AI_QA_ENGINE_QUEUE_BACKEND", "local").strip().lower()
    redis_url = os.getenv("AI_QA_ENGINE_REDIS_URL", "").strip() or os.getenv("REDIS_URL", "").strip()
    if backend == "redis":
        if not redis_url:
            raise AIQueueUnavailableError("AI_QA_ENGINE_REDIS_URL/REDIS_URL is not configured")
        try:
            import redis
            from rq import Queue
        except ImportError as error:
            raise AIQueueUnavailableError("Redis queue dependencies are not installed") from error

        try:
            connection = redis.from_url(redis_url)
            connection.ping()
            Queue(
                name=os.getenv("AI_QA_ENGINE_QUEUE_NAME", "ai-qa-engine-runs"),
                connection=connection,
            ).enqueue(_run_job, job_id, job_id=f"ai-{job_id}", result_ttl=3600, failure_ttl=86400)
            return
        except Exception as error:
            raise AIQueueUnavailableError(f"Redis enqueue failed: {type(error).__name__}") from error
    if backend != "local":
        raise AIQueueUnavailableError(f"Unsupported queue backend '{backend}'")
    Thread(target=_run_job, args=(job_id,), name=f"ai-qa-engine-ai-{job_id[:8]}", daemon=True).start()
