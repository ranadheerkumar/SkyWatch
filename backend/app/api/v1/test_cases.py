import asyncio
import csv
import io
import logging
import re
import time
from typing import Any
from uuid import uuid4
import zipfile
from xml.etree import ElementTree

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import func

from app.api.dependencies import DbSession, current_user, require_roles
from app.models.audit_log import AuditLog
from app.models.application import Application
from app.models.case_execution import CaseExecution
from app.models.test_case import TestCase
from app.models.test_case_automation import TestCaseAutomation
from app.models.test_run import TestRun
from app.models.user import User
from app.schemas.test_case import (
    AITestCaseGenerateRequest,
    AIProposalItem,
    AIProposalResponse,
    ApproveProposalsRequest,
    MultiFormatIngestRequest,
    TestCaseAutomationDefinition,
    TestCaseAutomationReadiness,
    TestCaseAutomationResponse,
    TestCaseBulkDeleteRequest,
    TestCaseBulkDeleteResponse,
    TestCaseCloneRequest,
    TestCaseCreate,
    TestCaseResponse,
    TestCaseReviewRequest,
    TestCaseUpdate,
)
from app.services.agent_definitions import (
    AgentDefinitionError,
    build_agent_guidance_block,
    get_agent_trace_metadata,
)
from app.services.ai_service import AIServiceError, generate_ai_test_cases, get_ai_provider_metadata
from app.services.automation_builder import build_case_automation_from_text
from app.services.automation_quality import evaluate_automation_quality
from app.services.audit import log_audit_event
from app.core.logging import log_event
from app.services.test_execution import validate_target

router = APIRouter(prefix="/test-cases", tags=["test-cases"])
logger = logging.getLogger("ai-qa-engine.ai_generation")

VALID_CASE_STATUSES = {"draft", "ready", "rejected"}
VALID_GENERATION_STATES = {"VALID", "NEEDS_REVIEW", "INVALID", "DUPLICATE"}


def _normalise_header(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _normalise_case_status(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in VALID_CASE_STATUSES else "draft"


def _normalise_case_key(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().casefold())


def _dedupe_import_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (
            _normalise_case_key(row.get("title")),
            _normalise_case_key(row.get("steps")),
            _normalise_case_key(row.get("expected_result")),
        )
        if not key[0]:
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(row)
    return deduped


def _ensure_tc_prefix(title: str, index: int) -> str:
    stripped = title.strip()
    if re.match(r"^TC\s*\d+\s*[-:]", stripped, re.IGNORECASE):
        return stripped
    return f"TC{index:02d} - {stripped}"


def _extract_tc_number(title: str | None) -> int | None:
    match = re.match(r"^\s*TC\s*0*(\d+)\s*[-:]", title or "", re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _sequenced_tc_title(title: str, index: int) -> str:
    stripped = (title or "").strip()
    suffix = re.sub(r"^\s*TC\s*\d+\s*[-:]\s*", "", stripped, flags=re.IGNORECASE).strip() or "Generated test case"
    return f"TC{index:02d} - {suffix}"


def _title_suffix_without_tc_prefix(title: str) -> str:
    stripped = (title or "").strip()
    return re.sub(r"^\s*TC\s*\d+\s*[-:]\s*", "", stripped, flags=re.IGNORECASE).strip() or "Generated test case"


def _count_case_steps(steps: str | None) -> int:
    return len(
        [
            line
            for line in (steps or "").splitlines()
            if re.sub(r"^\d+[\).:\-\s]+", "", line).strip()
        ]
    )


def _classify_generated_case(
    *,
    title: str,
    steps: str,
    expected_result: str,
    min_steps_per_case: int,
    max_steps_per_case: int,
    seen_keys: set[str],
) -> tuple[str, str]:
    normalized_title = _title_suffix_without_tc_prefix(title)
    normalized_steps = _normalise_case_key(steps)
    normalized_expected = _normalise_case_key(expected_result)
    if not normalized_title or not normalized_steps:
        return "INVALID", "Missing title or steps"

    dedupe_key = f"{_normalise_case_key(normalized_title)}|{normalized_steps}|{normalized_expected}"
    if dedupe_key in seen_keys:
        return "DUPLICATE", "Duplicate generated case content"

    step_count = _count_case_steps(steps)
    if step_count < min_steps_per_case or step_count > max_steps_per_case:
        seen_keys.add(dedupe_key)
        return (
            "NEEDS_REVIEW",
            f"Step count {step_count} is outside requested range {min_steps_per_case}-{max_steps_per_case}",
        )

    seen_keys.add(dedupe_key)
    return "VALID", ""


def _xlsx_rows(content: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = ["".join(node.itertext()) for node in root.findall("{*}si")]
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relations = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {item.attrib["Id"]: item.attrib["Target"] for item in relations}
        first_sheet = workbook.find("{*}sheets/{*}sheet")
        if first_sheet is None:
            return []
        rel_id = first_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rel_targets.get(rel_id or "", "worksheets/sheet1.xml").lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        root = ElementTree.fromstring(archive.read(target))
        rows: list[list[str]] = []
        for row in root.findall("{*}sheetData/{*}row"):
            values: list[str] = []
            for cell in row.findall("{*}c"):
                reference = cell.attrib.get("r", "")
                column_letters = "".join(character for character in reference if character.isalpha())
                column_index = 0
                for character in column_letters:
                    column_index = column_index * 26 + ord(character.upper()) - ord("A") + 1
                if column_index:
                    values.extend([""] * max(0, column_index - len(values) - 1))
                value = cell.find("{*}v")
                text = "" if value is None else value.text or ""
                if cell.attrib.get("t") == "s" and text:
                    text = shared_strings[int(text)]
                elif cell.attrib.get("t") == "inlineStr":
                    text = "".join(cell.find("{*}is").itertext()) if cell.find("{*}is") is not None else ""
                values.append(text)
            rows.append(values)
        return rows


def _parse_text_blocks(content: str, target_url: str = "") -> list[dict[str, str]]:
    raw_blocks = re.split(r"\n\s*\n\s*(?=(?:TC\s*\d+|Test\s*Case\s*\d*|\d+\.|\#\#)\b)", content.strip())
    if len(raw_blocks) <= 1:
        # Check for divider lines or bullet blocks
        raw_blocks = [b.strip() for b in re.split(r"\n\s*---\s*\n|\n\s*\={3,}\s*\n", content) if b.strip()]

    if not raw_blocks:
        raw_blocks = [content.strip()]

    parsed_cases = []
    for idx, block in enumerate(raw_blocks, start=1):
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue

        title = ""
        preconditions = ""
        expected_result = ""
        steps_list = []
        current_section = "steps"

        # Check first line for title
        first_line = lines[0]
        title_match = re.match(r"^(?:TC\s*\d+\s*[-:]|Test\s*Case\s*\d*\s*[-:]|\#\#\s*|Title\s*[-:])\s*(.+)", first_line, re.IGNORECASE)
        if title_match:
            title = _ensure_tc_prefix(title_match.group(1).strip(), idx)
            lines_to_process = lines[1:]
        elif len(first_line) < 80 and not re.match(r"^\d+[\).:\-\s]", first_line):
            title = _ensure_tc_prefix(first_line, idx)
            lines_to_process = lines[1:]
        else:
            title = f"TC{idx:02d} - Workflow Validation Step {idx}"
            lines_to_process = lines

        for line in lines_to_process:
            pre_match = re.match(r"^(?:Precondition[s]?|Prerequisites?)\s*:\s*(.+)", line, re.IGNORECASE)
            if pre_match:
                preconditions = pre_match.group(1).strip()
                current_section = "preconditions"
                continue

            exp_match = re.match(r"^(?:Expected\s*Result[s]?|Expected\s*Outcome|Expected)\s*:\s*(.+)", line, re.IGNORECASE)
            if exp_match:
                expected_result = exp_match.group(1).strip()
                current_section = "expected"
                continue

            steps_hdr_match = re.match(r"^(?:Steps?|Test\s*Steps?)\s*:\s*(.*)", line, re.IGNORECASE)
            if steps_hdr_match:
                current_section = "steps"
                rest = steps_hdr_match.group(1).strip()
                if rest:
                    steps_list.append(rest)
                continue

            if current_section == "expected":
                expected_result = f"{expected_result}\n{line}".strip()
            elif current_section == "preconditions":
                preconditions = f"{preconditions}\n{line}".strip()
            else:
                steps_list.append(line)

        # Normalize steps
        formatted_steps = []
        for s_idx, s in enumerate(steps_list, start=1):
            clean_s = re.sub(r"^\d+[\).:\-\s]+", "", s).strip()
            if clean_s:
                formatted_steps.append(f"{s_idx}. {clean_s}")

        if not formatted_steps:
            formatted_steps = [f"1. Navigate to {target_url or 'application'}", "2. Verify page content is displayed"]

        parsed_cases.append({
            "title": title[:200],
            "description": f"Scenario {idx} parsed from text requirements",
            "preconditions": preconditions or "Application is accessible",
            "steps": "\n".join(formatted_steps),
            "expected_result": expected_result or "All workflow steps execute and validate successfully",
            "status": "ready",
            "priority": "high" if idx <= 2 else "medium",
            "category": "functional",
        })

    return parsed_cases


def _parse_import(content: bytes, filename: str) -> list[dict[str, str]]:
    lowered = filename.lower()
    if lowered.endswith(".csv"):
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    elif lowered.endswith((".xlsx", ".xls")):
        rows = _xlsx_rows(content)
    elif lowered.endswith((".json", ".js")):
        import json
        try:
            raw = json.loads(content.decode("utf-8-sig"))
            items = raw if isinstance(raw, list) else [raw]
            return [
                {
                    "title": item.get("title") or f"TC{i:02d} - {item.get('name', 'Scenario')}",
                    "description": item.get("description", ""),
                    "preconditions": item.get("preconditions", ""),
                    "steps": item.get("steps") if isinstance(item.get("steps"), str) else "\n".join(item.get("steps", [])),
                    "expected_result": item.get("expected_result") or item.get("expected", ""),
                    "status": item.get("status", "ready"),
                }
                for i, item in enumerate(items, start=1)
            ]
        except Exception:
            return []
    elif lowered.endswith((".txt", ".md", ".text", ".markdown")):
        text_str = content.decode("utf-8-sig", errors="ignore")
        return _parse_text_blocks(text_str)
    else:
        rows = _xlsx_rows(content)

    if not rows:
        return []
    headers = [_normalise_header(value) for value in rows[0]]
    aliases = {
        "title": {"title", "testcase", "testcasename", "name"},
        "description": {"description", "details"},
        "preconditions": {"precondition", "preconditions"},
        "steps": {"steps", "step", "teststeps", "stepdescription"},
        "expected_result": {"expected", "expectedresult", "expectedoutcome", "result"},
        "status": {"status", "teststatus", "casestatus"},
    }
    columns = {field: next((index for index, header in enumerate(headers) if header in names), None) for field, names in aliases.items()}
    # Prefer the human-readable step description over the adjacent numeric "Step #" column.
    columns["steps"] = next(
        (index for index, header in enumerate(headers) if header in {"stepdescription", "steps", "teststeps"}),
        columns["steps"],
    )
    step_number_column = next(
        (index for index, header in enumerate(headers) if header in {"stepnumber", "stepno", "stepnum", "stepid", "step"}),
        None,
    )
    title_column = columns["title"]
    if title_column is None:
        raise HTTPException(status_code=400, detail="File must include a Test Case or Title column")
    parsed: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for row in rows[1:]:
        get_value = lambda field: row[columns[field]].strip() if columns[field] is not None and columns[field] < len(row) else ""
        title = get_value("title")
        step_number = row[step_number_column].strip() if step_number_column is not None and step_number_column < len(row) else ""
        step_text = get_value("steps")
        formatted_step = f"{step_number}. {step_text}" if step_number and step_text and not step_text.startswith(f"{step_number}.") else step_text
        if title:
            current = {field: get_value(field) for field in aliases}
            current["steps"] = formatted_step
            current["status"] = current["status"] or "draft"
            parsed.append(current)
        elif current:
            expected_result = get_value("expected_result")
            if formatted_step:
                current["steps"] = "\n".join(part for part in [current["steps"], formatted_step] if part)
            if expected_result:
                current["expected_result"] = "\n".join(part for part in [current["expected_result"], expected_result] if part)
    return parsed


@router.get("", response_model=list[TestCaseResponse])
def list_test_cases(
    db: DbSession,
    response: Response,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
) -> list[TestCase]:
    query = (
        db.query(TestCase)
        .join(Application, Application.id == TestCase.application_id)
        .filter(Application.created_by == user.id)
        .order_by(TestCase.id.asc())
    )
    response.headers["X-Total-Count"] = str(query.count())
    return query.offset(offset).limit(limit).all()


@router.get("/application/{application_id}", response_model=list[TestCaseResponse])
def list_application_test_cases(
    application_id: int,
    db: DbSession,
    response: Response,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
) -> list[TestCase]:
    application = db.query(Application).filter(Application.id == application_id, Application.created_by == user.id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    query = db.query(TestCase).filter(TestCase.application_id == application_id).order_by(TestCase.id.asc())
    response.headers["X-Total-Count"] = str(query.count())
    return query.offset(offset).limit(limit).all()


@router.get("/application/{application_id}/automation-readiness", response_model=list[TestCaseAutomationReadiness])
def list_application_automation_readiness(
    application_id: int,
    db: DbSession,
    user: User = Depends(current_user),
) -> list[TestCaseAutomationReadiness]:
    application = db.query(Application).filter(Application.id == application_id, Application.created_by == user.id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    test_case_rows = (
        db.query(TestCase, TestCaseAutomation)
        .outerjoin(TestCaseAutomation, TestCaseAutomation.test_case_id == TestCase.id)
        .filter(TestCase.application_id == application_id)
        .order_by(TestCase.id.asc())
        .all()
    )

    readiness: list[TestCaseAutomationReadiness] = []
    for test_case, automation in test_case_rows:
        has_saved_automation = bool(automation and ((automation.steps or []) or (automation.checks or [])))
        steps = automation.steps if automation else []
        checks = automation.checks if automation else []
        if not has_saved_automation:
            fallback_steps, fallback_checks = build_case_automation_from_text(test_case, application)
            steps = fallback_steps
            checks = fallback_checks
        quality = evaluate_automation_quality(steps, checks)
        readiness.append(
            TestCaseAutomationReadiness(
                test_case_id=test_case.id,
                title=test_case.title,
                status=test_case.status,
                has_automation=has_saved_automation,
                confidence_score=quality.confidence_score,
                confidence_label=quality.confidence_label,
                needs_manual_selector_review=quality.needs_manual_selector_review,
                reasons=quality.reasons[:10],
            )
        )
    return readiness


@router.get("/export/{application_id}")
def export_test_case_progress(application_id: int, db: DbSession, user: User = Depends(current_user)) -> Response:
    application = db.query(Application).filter(Application.id == application_id, Application.created_by == user.id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    cases = db.query(TestCase).filter(TestCase.application_id == application_id).order_by(TestCase.id.asc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Test Case", "Precondition", "Description", "Step Number", "Steps", "Expected Result", "Status"])
    for test_case in cases:
        step_lines = [line.strip() for line in (test_case.steps or "").splitlines() if line.strip()]
        step_number = ""
        if step_lines:
            numbers = [int(match.group(1)) for line in step_lines if (match := re.match(r"^(\d+)[\).:\-\s]", line))]
            if numbers:
                step_number = f"{min(numbers)}-{max(numbers)}" if len(set(numbers)) > 1 else str(numbers[0])
            else:
                step_number = f"1-{len(step_lines)}" if len(step_lines) > 1 else "1"
        writer.writerow([
            test_case.title,
            test_case.preconditions or "",
            test_case.description or "",
            step_number,
            test_case.steps or "",
            test_case.expected_result or "",
            test_case.status,
        ])
    filename = "".join(character if character.isalnum() else "-" for character in application.name).strip("-") or "test-cases"
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}-test-case-progress.csv"'},
    )


@router.get("/{test_case_id}/export-playwright")
def export_playwright_spec(test_case_id: int, db: DbSession, user: User = Depends(current_user)) -> dict[str, str]:
    from app.services.automation_builder import generate_playwright_spec_code

    test_case = (
        db.query(TestCase)
        .join(Application, Application.id == TestCase.application_id)
        .filter(TestCase.id == test_case_id, Application.created_by == user.id)
        .first()
    )
    if not test_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")
    application = db.get(Application, test_case.application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    automation = db.get(TestCaseAutomation, test_case.id)
    steps = automation.steps if automation else None
    checks = automation.checks if automation else None

    spec_code = generate_playwright_spec_code(test_case, application, steps=steps, checks=checks)
    safe_name = re.sub(r"[^\w\-]", "_", test_case.title.lower()).strip("_")
    filename = f"{safe_name or f'tc_{test_case.id}'}.spec.ts"

    return {
        "test_case_id": str(test_case.id),
        "title": test_case.title,
        "filename": filename,
        "code": spec_code,
    }


@router.get("/application/{application_id}/export-playwright-suite")
def export_playwright_suite(application_id: int, db: DbSession, user: User = Depends(current_user)) -> dict[str, Any]:
    from app.services.automation_builder import generate_playwright_spec_code

    application = db.query(Application).filter(Application.id == application_id, Application.created_by == user.id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    cases = db.query(TestCase).filter(TestCase.application_id == application_id).order_by(TestCase.id.asc()).all()
    specs = []
    for tc in cases:
        automation = db.get(TestCaseAutomation, tc.id)
        steps = automation.steps if automation else None
        checks = automation.checks if automation else None
        code = generate_playwright_spec_code(tc, application, steps=steps, checks=checks)
        safe_name = re.sub(r"[^\w\-]", "_", tc.title.lower()).strip("_")
        specs.append({
            "test_case_id": tc.id,
            "title": tc.title,
            "filename": f"{safe_name or f'tc_{tc.id}'}.spec.ts",
            "code": code,
        })

    return {
        "application_id": application.id,
        "application_name": application.name,
        "total_specs": len(specs),
        "specs": specs,
    }


@router.post("/{test_case_id}/git-push")
def git_push_test_spec(test_case_id: int, db: DbSession, user: User = Depends(require_roles("tester", "qa_lead", "admin"))) -> dict[str, Any]:
    from pathlib import Path
    from app.services.automation_builder import generate_playwright_spec_code

    test_case = (
        db.query(TestCase)
        .join(Application, Application.id == TestCase.application_id)
        .filter(TestCase.id == test_case_id, Application.created_by == user.id)
        .first()
    )
    if not test_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")
    application = db.get(Application, test_case.application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    automation = db.get(TestCaseAutomation, test_case.id)
    steps = automation.steps if automation else None
    checks = automation.checks if automation else None
    spec_code = generate_playwright_spec_code(test_case, application, steps=steps, checks=checks)

    safe_name = re.sub(r"[^\w\-]", "_", test_case.title.lower()).strip("_")
    filename = f"{safe_name or f'tc_{test_case.id}'}.spec.ts"
    target_dir = Path(__file__).resolve().parents[4] / "tests" / "generated"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / filename
    target_file.write_text(spec_code, encoding="utf-8")

    log_audit_event(
        db,
        user_id=user.id,
        action="test_case.export_git",
        resource_type="test_case",
        resource_id=test_case.id,
        metadata={"filename": filename, "path": str(target_file)},
    )
    db.commit()

    return {
        "test_case_id": test_case.id,
        "filename": filename,
        "path": f"tests/generated/{filename}",
        "status": "persisted",
        "message": f"Playwright spec generated and saved to tests/generated/{filename}",
    }


@router.get("/{test_case_id}", response_model=TestCaseResponse)
def get_test_case(test_case_id: int, db: DbSession, user: User = Depends(current_user)) -> TestCase:
    test_case = (
        db.query(TestCase)
        .join(Application, Application.id == TestCase.application_id)
        .filter(TestCase.id == test_case_id, Application.created_by == user.id)
        .first()
    )
    if not test_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")
    return test_case


@router.post("/{test_case_id}/review", response_model=TestCaseResponse)
def review_test_case(
    test_case_id: int,
    request: TestCaseReviewRequest,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> TestCase:
    test_case = (
        db.query(TestCase)
        .join(Application, Application.id == TestCase.application_id)
        .filter(TestCase.id == test_case_id, Application.created_by == user.id)
        .first()
    )
    if not test_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")

    next_status = "ready" if request.action == "approve" else "rejected"
    previous_status = test_case.status
    test_case.status = next_status
    db.add(test_case)
    log_audit_event(
        db,
        user_id=user.id,
        action=f"test_case.review.{request.action}",
        resource_type="test_case",
        resource_id=test_case.id,
        metadata={
            "application_id": test_case.application_id,
            "previous_status": previous_status,
            "new_status": next_status,
        },
    )
    db.commit()
    db.refresh(test_case)
    return test_case


@router.put("/{test_case_id}", response_model=TestCaseResponse)
def update_test_case(
    test_case_id: int,
    request: TestCaseUpdate,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> TestCase:
    test_case = (
        db.query(TestCase)
        .join(Application, Application.id == TestCase.application_id)
        .filter(TestCase.id == test_case_id, Application.created_by == user.id)
        .first()
    )
    if not test_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")

    old_snapshot = {
        "title": test_case.title,
        "description": test_case.description,
        "steps": test_case.steps,
        "expected_result": test_case.expected_result,
        "status": test_case.status,
        "priority": getattr(test_case, "priority", "medium"),
    }

    if request.title is not None:
        test_case.title = request.title.strip()
    if request.description is not None:
        test_case.description = request.description
    if request.preconditions is not None:
        test_case.preconditions = request.preconditions
    if request.steps is not None:
        from app.services.ai_service import auto_parameterize_case_steps
        param_steps, param_expected, auto_td = auto_parameterize_case_steps(
            request.steps,
            expected_result=request.expected_result or test_case.expected_result or "",
            category=request.category or getattr(test_case, "category", "positive") or "positive",
            existing_test_data=test_case.test_data if isinstance(test_case.test_data, dict) else None,
        )
        test_case.steps = param_steps
        if request.expected_result is not None:
            test_case.expected_result = param_expected
        if auto_td and request.test_data is None:
            test_case.test_data = json.dumps(auto_td)
    elif request.expected_result is not None:
        test_case.expected_result = request.expected_result
    if request.status is not None:
        test_case.status = _normalise_case_status(request.status)
    if request.priority is not None:
        test_case.priority = request.priority
    if request.category is not None:
        test_case.category = request.category
    if request.tags is not None:
        test_case.tags = request.tags
    if request.version is not None:
        test_case.version = request.version
    if request.automation_status is not None:
        test_case.automation_status = request.automation_status
    if request.test_data is not None:
        test_case.test_data = request.test_data

    db.add(test_case)
    log_audit_event(
        db,
        user_id=user.id,
        action="test_case.update",
        resource_type="test_case",
        resource_id=test_case.id,
        old_value=old_snapshot,
        new_value={"title": test_case.title, "status": test_case.status, "priority": getattr(test_case, "priority", "medium")},
        metadata={"application_id": test_case.application_id},
    )
    db.commit()
    db.refresh(test_case)
    return test_case


@router.post("/{test_case_id}/clone", response_model=TestCaseResponse, status_code=status.HTTP_201_CREATED)
def clone_test_case(
    test_case_id: int,
    clone_req: TestCaseCloneRequest,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> TestCase:
    original = (
        db.query(TestCase)
        .join(Application, Application.id == TestCase.application_id)
        .filter(TestCase.id == test_case_id, Application.created_by == user.id)
        .first()
    )
    if not original:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")

    target_app_id = clone_req.target_application_id or original.application_id
    new_title = clone_req.new_title or f"{original.title} (Clone)"

    cloned = TestCase(
        application_id=target_app_id,
        title=new_title,
        description=original.description,
        preconditions=original.preconditions,
        steps=original.steps,
        expected_result=original.expected_result,
        status="draft",
        priority=getattr(original, "priority", "medium"),
        category=getattr(original, "category", "positive"),
        tags=getattr(original, "tags", []),
        version=1,
        automation_status=getattr(original, "automation_status", "automated"),
        test_data=getattr(original, "test_data", None),
        created_by=user.id,
    )
    db.add(cloned)
    db.flush()

    orig_auto = db.get(TestCaseAutomation, test_case_id)
    if orig_auto:
        db.add(TestCaseAutomation(
            test_case_id=cloned.id,
            steps=orig_auto.steps,
            checks=orig_auto.checks,
            updated_by=user.id,
        ))

    log_audit_event(
        db,
        user_id=user.id,
        action="test_case.clone",
        resource_type="test_case",
        resource_id=cloned.id,
        metadata={"original_id": test_case_id, "cloned_title": cloned.title},
    )
    db.commit()
    db.refresh(cloned)
    return cloned


@router.post("/{test_case_id}/version", response_model=TestCaseResponse)
def create_test_case_version(
    test_case_id: int,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> TestCase:
    test_case = (
        db.query(TestCase)
        .join(Application, Application.id == TestCase.application_id)
        .filter(TestCase.id == test_case_id, Application.created_by == user.id)
        .first()
    )
    if not test_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")

    old_version = getattr(test_case, "version", 1) or 1
    test_case.version = old_version + 1
    db.add(test_case)
    log_audit_event(
        db,
        user_id=user.id,
        action="test_case.version_bump",
        resource_type="test_case",
        resource_id=test_case.id,
        metadata={"old_version": old_version, "new_version": test_case.version},
    )
    db.commit()
    db.refresh(test_case)
    return test_case


def _index_cases_in_vector_store(application_id: int, cases: list[TestCase]) -> None:
    try:
        from app.services.vector_service import VectorStoreService
        vstore = VectorStoreService(application_id)
        for case in cases:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    asyncio.create_task(vstore.index_test_case(
                        case_id=case.id,
                        title=case.title,
                        steps=case.steps or "",
                        expected_result=case.expected_result,
                        description=case.description,
                    ))
                except RuntimeError:
                    asyncio.run(vstore.index_test_case(
                        case_id=case.id,
                        title=case.title,
                        steps=case.steps or "",
                        expected_result=case.expected_result,
                        description=case.description,
                    ))
            except Exception:
                pass
    except Exception as err:
        logger.warning("Vector indexing skipped: %s", err)


@router.post("", response_model=TestCaseResponse, status_code=201)
def create_test_case(
    request: TestCaseCreate,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> TestCase:
    application = db.query(Application).filter(Application.id == request.application_id, Application.created_by == user.id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    normalized_status = _normalise_case_status(request.status)
    normalized_title = request.title.strip()

    from app.services.ai_service import auto_parameterize_case_steps

    param_steps, param_expected, auto_td = auto_parameterize_case_steps(
        request.steps or "",
        expected_result=request.expected_result or "",
        category=request.category or "positive",
        existing_test_data=request.test_data if isinstance(request.test_data, dict) else None,
    )
    final_test_data = json.dumps(auto_td) if auto_td else (request.test_data if isinstance(request.test_data, str) else json.dumps(request.test_data) if request.test_data else None)

    existing_case = (
        db.query(TestCase)
        .filter(
            TestCase.application_id == request.application_id,
            TestCase.created_by == user.id,
            func.lower(func.trim(func.coalesce(TestCase.title, ""))) == normalized_title.casefold(),
        )
        .first()
    )
    if existing_case:
        existing_status = _normalise_case_status(existing_case.status)
        if existing_status == "ready" and normalized_status == "draft":
            return existing_case
        existing_case.title = normalized_title
        existing_case.description = request.description
        existing_case.preconditions = request.preconditions
        existing_case.steps = param_steps
        existing_case.expected_result = param_expected
        existing_case.status = normalized_status
        existing_case.priority = request.priority
        existing_case.category = request.category
        existing_case.tags = request.tags
        existing_case.version = request.version
        existing_case.automation_status = request.automation_status
        existing_case.test_data = final_test_data
        db.add(existing_case)
        log_audit_event(
            db,
            user_id=user.id,
            action="test_case.update",
            resource_type="test_case",
            resource_id=existing_case.id,
            metadata={"application_id": request.application_id, "status": normalized_status},
        )
        db.commit()
        db.refresh(existing_case)
        _index_cases_in_vector_store(request.application_id, [existing_case])
        return existing_case

    test_case = TestCase(
        application_id=request.application_id,
        title=normalized_title,
        description=request.description,
        preconditions=request.preconditions,
        steps=param_steps,
        expected_result=param_expected,
        status=normalized_status,
        priority=request.priority,
        category=request.category,
        tags=request.tags,
        version=request.version,
        automation_status=request.automation_status,
        test_data=final_test_data,
        created_by=user.id,
    )
    db.add(test_case)
    db.flush()
    log_audit_event(
        db,
        user_id=user.id,
        action="test_case.create",
        resource_type="test_case",
        resource_id=test_case.id,
        metadata={"application_id": request.application_id, "status": normalized_status},
    )
    db.commit()
    db.refresh(test_case)
    _index_cases_in_vector_store(request.application_id, [test_case])
    return test_case


@router.get("/{test_case_id}/automation", response_model=TestCaseAutomationResponse)
def get_test_case_automation(test_case_id: int, db: DbSession, user: User = Depends(current_user)) -> TestCaseAutomationResponse:
    test_case = db.query(TestCase).join(Application, Application.id == TestCase.application_id).filter(
        TestCase.id == test_case_id,
        Application.created_by == user.id,
    ).first()
    if not test_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")
    automation = db.get(TestCaseAutomation, test_case_id)
    if not automation:
        return TestCaseAutomationResponse(test_case_id=test_case_id)
    return TestCaseAutomationResponse(test_case_id=test_case_id, steps=automation.steps, checks=automation.checks)


@router.put("/{test_case_id}/automation", response_model=TestCaseAutomationResponse)
def save_test_case_automation(
    test_case_id: int,
    request: TestCaseAutomationDefinition,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> TestCaseAutomationResponse:
    test_case = db.query(TestCase).join(Application, Application.id == TestCase.application_id).filter(
        TestCase.id == test_case_id,
        Application.created_by == user.id,
    ).first()
    if not test_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")
    automation = db.get(TestCaseAutomation, test_case_id)
    if automation is None:
        automation = TestCaseAutomation(test_case_id=test_case_id, updated_by=user.id)
        db.add(automation)
    automation.steps = [step.model_dump() for step in request.steps]
    automation.checks = [check.model_dump() for check in request.checks]
    automation.updated_by = user.id
    test_case.status = "ready" if automation.steps or automation.checks else "draft"
    log_audit_event(
        db,
        user_id=user.id,
        action="test_case.automation.save",
        resource_type="test_case",
        resource_id=test_case_id,
        metadata={"steps": len(automation.steps or []), "checks": len(automation.checks or [])},
    )
    db.commit()
    return TestCaseAutomationResponse(test_case_id=test_case_id, steps=automation.steps, checks=automation.checks)


@router.get("/{test_case_id}/ai-trace")
def get_test_case_ai_trace(
    test_case_id: int,
    db: DbSession,
    user: User = Depends(current_user),
) -> dict:
    test_case = (
        db.query(TestCase)
        .join(Application, Application.id == TestCase.application_id)
        .filter(
            TestCase.id == test_case_id,
            Application.created_by == user.id,
        )
        .first()
    )
    if not test_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")

    traces = (
        db.query(AuditLog)
        .filter(
            AuditLog.resource_type == "test_case",
            AuditLog.resource_id == str(test_case_id),
            AuditLog.action == "test_case.ai_trace",
        )
        .order_by(AuditLog.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "test_case_id": test_case_id,
        "trace_count": len(traces),
        "traces": [
            {
                "id": trace.id,
                "created_at": trace.created_at.isoformat() if trace.created_at else None,
                "metadata": trace.metadata_json or {},
            }
            for trace in traces
        ],
    }


@router.post("/ingest", response_model=list[TestCaseResponse], status_code=201)
def ingest_test_cases(
    request: MultiFormatIngestRequest,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> list[TestCase]:
    application = (
        db.query(Application)
        .filter(Application.id == request.application_id, Application.created_by == user.id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    content = request.content.strip()
    parsed_cases_data: list[dict[str, str]] = []

    if request.format == "json":
        import json
        try:
            raw_data = json.loads(content)
            items = raw_data if isinstance(raw_data, list) else [raw_data]
            for idx, item in enumerate(items, 1):
                parsed_cases_data.append({
                    "title": item.get("title") or f"TC{idx:02d} - {item.get('name', 'Scenario')}",
                    "description": item.get("description", ""),
                    "preconditions": item.get("preconditions") or request.preconditions or "",
                    "steps": item.get("steps") if isinstance(item.get("steps"), str) else "\n".join(item.get("steps", [])),
                    "expected_result": item.get("expected_result") or item.get("expected", ""),
                    "status": item.get("status", "draft"),
                    "priority": item.get("priority", "medium"),
                    "category": item.get("category", "positive"),
                })
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")

    elif request.format == "markdown_table":
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        table_lines = [l for l in lines if l.startswith("|") and l.endswith("|")]
        if len(table_lines) >= 3:
            # Header line
            headers = [c.strip().lower() for c in table_lines[0].strip("|").split("|")]
            # Data rows (skip separator row at index 1)
            for idx, row_line in enumerate(table_lines[2:], 1):
                cols = [c.strip() for c in row_line.strip("|").split("|")]
                step_val = ""
                expected_val = ""
                title_val = f"TC{idx:02d} - Scenario from Markdown Table"
                for h_idx, header in enumerate(headers):
                    if h_idx < len(cols):
                        val = cols[h_idx]
                        if "step" in header or "action" in header:
                            step_val = val
                        elif "expect" in header or "result" in header:
                            expected_val = val
                        elif "title" in header or "name" in header or "case" in header:
                            title_val = val
                parsed_cases_data.append({
                    "title": title_val,
                    "description": f"Imported from Markdown table row {idx}",
                    "preconditions": request.preconditions or "",
                    "steps": step_val or row_line,
                    "expected_result": expected_val or "Outcome is verified successfully",
                    "status": "ready",
                    "priority": "medium",
                    "category": "functional",
                })

    elif request.format in {"openapi", "db_schema"}:
        # Specialized structured schema parser
        if request.format == "openapi":
            endpoints = re.findall(r'(?:get|post|put|delete|patch):\s*(/[^\s\n]+|[\w/{}]+)', content, re.IGNORECASE)
            if not endpoints:
                endpoints = re.findall(r'["\'](/[a-zA-Z0-9_\-/{}]*)["\']', content)
            endpoints = list(dict.fromkeys(endpoints))[:10]
            if not endpoints:
                endpoints = ["/api/v1/resource", "/api/v1/auth/status"]
            for idx, ep in enumerate(endpoints, 1):
                parsed_cases_data.append({
                    "title": f"TC{idx:02d} - Verify API Endpoint {ep} response and schema",
                    "description": f"Validate API response code, payload contract, and latency for {ep}",
                    "preconditions": request.preconditions or "API service is deployed and token is valid",
                    "steps": f"1. Send GET request to {ep}\n2. Verify HTTP status code is 200\n3. Verify JSON schema conforms to contract\n4. Send invalid payload to {ep}\n5. Verify 400 Bad Request error response is returned",
                    "expected_result": "API responds with valid schema and handles invalid parameters with clear errors",
                    "status": "ready",
                    "priority": "high",
                    "category": "api",
                })
        else: # db_schema
            tables = re.findall(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)', content, re.IGNORECASE)
            if not tables:
                tables = re.findall(r'table\s+([a-zA-Z0-9_]+)', content, re.IGNORECASE)
            tables = list(dict.fromkeys(tables))[:10]
            if not tables:
                tables = ["users", "transactions", "orders"]
            for idx, tbl in enumerate(tables, 1):
                parsed_cases_data.append({
                    "title": f"TC{idx:02d} - Verify Table Integrity and Constraints for {tbl}",
                    "description": f"Validate primary key uniqueness, foreign keys, nullability, and index performance for {tbl}",
                    "preconditions": request.preconditions or "Database connection is active",
                    "steps": f"1. Query metadata for table '{tbl}'\n2. Verify primary key constraint is enforced\n3. Attempt inserting duplicate primary key\n4. Verify duplicate key violation is raised\n5. Insert valid record and verify row presence",
                    "expected_result": f"Table '{tbl}' preserves referential integrity and enforces schema constraints",
                    "status": "ready",
                    "priority": "high",
                    "category": "database",
                })

    else:
        # Plain text / user story / requirements / markdown text blocks
        target_nav_url = request.target_url or application.target
        parsed_cases_data = _parse_text_blocks(content, target_nav_url)

    created_cases = []
    for cdata in parsed_cases_data:
        test_case = TestCase(
            application_id=application.id,
            title=cdata["title"][:200],
            description=cdata.get("description"),
            preconditions=cdata.get("preconditions"),
            steps=cdata.get("steps", ""),
            expected_result=cdata.get("expected_result"),
            status=cdata.get("status", "ready"),
            priority=cdata.get("priority", "medium"),
            category=cdata.get("category", "positive"),
            tags=[cdata.get("category", "positive")],
            version=1,
            automation_status="automated",
            created_by=user.id,
        )
        db.add(test_case)
        created_cases.append(test_case)

    db.flush()
    # Attach compiled automation steps
    for case in created_cases:
        steps, checks = build_case_automation_from_text(case, application)
        if steps or checks:
            db.add(TestCaseAutomation(
                test_case_id=case.id,
                steps=steps,
                checks=checks,
                updated_by=user.id,
            ))

    log_audit_event(
        db,
        user_id=user.id,
        action="test_case.ingest",
        resource_type="application",
        resource_id=application.id,
        metadata={"format": request.format, "case_count": len(created_cases)},
    )
    db.commit()
    for case in created_cases:
        db.refresh(case)
    _index_cases_in_vector_store(application.id, created_cases)
    return created_cases


def _infer_category_and_priority(title: str, steps: str) -> tuple[str, str]:
    combined = f"{title} {steps}".lower()
    if any(k in combined for k in ["invalid", "malformed", "error", "fail", "block", "denied", "no results", "400", "500", "reject"]):
        return "negative", "medium"
    if any(k in combined for k in ["wildcard", "boundary", "limit", "max", "min", "%", "special character", "empty", "blank"]):
        return "boundary", "high"
    if any(k in combined for k in ["security", "auth", "permission", "unauthorized", "token", "forbidden", "role", "rbac", "session"]):
        return "security", "critical"
    if any(k in combined for k in ["keyboard", "accessibility", "a11y", "tab", "focus", "aria"]):
        return "accessibility", "low"
    if any(k in combined for k in ["refresh", "reload", "navigate back", "stale", "reset", "cancel"]):
        return "edge_case", "medium"
    return "positive", "high"


def _convert_to_proposal_items(parsed_cases_data: list[dict[str, Any]], application: Application) -> list[AIProposalItem]:
    proposals: list[AIProposalItem] = []
    for idx, cdata in enumerate(parsed_cases_data, start=1):
        title = cdata.get("title") or f"TC{idx:02d} - Scenario {idx}"
        steps_text = cdata.get("steps") or ""
        expected_text = cdata.get("expected_result") or ""
        precond = cdata.get("preconditions") or "User is authenticated with appropriate role"
        cat, prio = _infer_category_and_priority(title, steps_text)
        category = cdata.get("category") or cat
        priority = cdata.get("priority") or prio

        # Evaluate automation readiness
        dummy_case = TestCase(
            application_id=application.id,
            title=title,
            steps=steps_text,
            expected_result=expected_text,
            preconditions=precond,
            status="ready",
            created_by=application.created_by,
        )
        steps, checks = build_case_automation_from_text(dummy_case, application)
        quality = evaluate_automation_quality(steps, checks)

        proposals.append(
            AIProposalItem(
                temp_id=f"prop_{idx:03d}_{abs(hash(title)) % 10000}",
                title=title,
                description=cdata.get("description") or f"AI-analyzed scenario {idx} ({category.replace('_', ' ').title()})",
                preconditions=precond,
                steps=steps_text,
                expected_result=expected_text,
                priority=priority,
                category=category,
                tags=[category, "ai_proposal"],
                confidence_score=quality.confidence_score,
                confidence_label=quality.confidence_label,
                needs_manual_selector_review=quality.needs_manual_selector_review,
                reasons=quality.reasons[:5],
                selected=True,
            )
        )
    return proposals


@router.post("/analyze-upload/{application_id}", response_model=AIProposalResponse)
async def analyze_uploaded_file_proposals(
    application_id: int,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
    file: UploadFile = File(...),
) -> AIProposalResponse:
    application = db.query(Application).filter(Application.id == application_id, Application.created_by == user.id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    filename = file.filename or ""
    allowed_extensions = (".csv", ".xlsx", ".xls", ".txt", ".md", ".json", ".text", ".markdown")
    if not filename.lower().endswith(allowed_extensions):
        raise HTTPException(status_code=400, detail="Choose a CSV, Excel, TXT, Markdown, or JSON file")

    try:
        rows = _parse_import(await file.read(), filename)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Unable to read file: {error}") from error

    rows = _dedupe_import_rows(rows)
    if not rows:
        raise HTTPException(status_code=400, detail="The file does not contain any recognizable test scenarios")

    proposals = _convert_to_proposal_items(rows, application)
    cat_counts = {}
    for p in proposals:
        cat_counts[p.category] = cat_counts.get(p.category, 0) + 1
    breakdown = ", ".join(f"{cnt} {cat.title()}" for cat, cnt in cat_counts.items())

    return AIProposalResponse(
        application_id=application_id,
        source_filename=filename,
        summary=f"AI analyzed '{filename}' and extracted {len(proposals)} recommended scenario(s) ({breakdown}). Review and select test cases before committing.",
        total_proposed=len(proposals),
        proposals=proposals,
    )


@router.post("/propose", response_model=AIProposalResponse)
def propose_test_cases_from_text(
    request: MultiFormatIngestRequest,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> AIProposalResponse:
    application = (
        db.query(Application)
        .filter(Application.id == request.application_id, Application.created_by == user.id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    content = request.content.strip()
    parsed_cases_data: list[dict[str, str]] = []

    if request.format == "json":
        import json
        try:
            raw_data = json.loads(content)
            items = raw_data if isinstance(raw_data, list) else [raw_data]
            for idx, item in enumerate(items, 1):
                parsed_cases_data.append({
                    "title": item.get("title") or f"TC{idx:02d} - {item.get('name', 'Scenario')}",
                    "description": item.get("description", ""),
                    "preconditions": item.get("preconditions") or request.preconditions or "",
                    "steps": item.get("steps") if isinstance(item.get("steps"), str) else "\n".join(item.get("steps", [])),
                    "expected_result": item.get("expected_result") or item.get("expected", ""),
                    "status": item.get("status", "ready"),
                    "priority": item.get("priority", "medium"),
                    "category": item.get("category", "positive"),
                })
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")

    elif request.format == "markdown_table":
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        table_lines = [l for l in lines if l.startswith("|") and l.endswith("|")]
        if len(table_lines) >= 3:
            headers = [c.strip().lower() for c in table_lines[0].strip("|").split("|")]
            for idx, row_line in enumerate(table_lines[2:], 1):
                cols = [c.strip() for c in row_line.strip("|").split("|")]
                step_val = ""
                expected_val = ""
                title_val = f"TC{idx:02d} - Scenario from Markdown Table"
                for h_idx, header in enumerate(headers):
                    if h_idx < len(cols):
                        val = cols[h_idx]
                        if "step" in header or "action" in header:
                            step_val = val
                        elif "expect" in header or "result" in header:
                            expected_val = val
                        elif "title" in header or "name" in header or "case" in header:
                            title_val = val
                parsed_cases_data.append({
                    "title": title_val,
                    "description": f"Imported from Markdown table row {idx}",
                    "preconditions": request.preconditions or "",
                    "steps": step_val or row_line,
                    "expected_result": expected_val or "Outcome is verified successfully",
                    "status": "ready",
                    "priority": "medium",
                    "category": "functional",
                })

    elif request.format in {"openapi", "db_schema"}:
        if request.format == "openapi":
            endpoints = re.findall(r'(?:get|post|put|delete|patch):\s*(/[^\s\n]+|[\w/{}]+)', content, re.IGNORECASE)
            if not endpoints:
                endpoints = re.findall(r'["\'](/[a-zA-Z0-9_\-/{}]*)["\']', content)
            endpoints = list(dict.fromkeys(endpoints))[:12]
            if not endpoints:
                endpoints = ["/api/v1/resource", "/api/v1/auth/status"]
            for idx, ep in enumerate(endpoints, 1):
                parsed_cases_data.append({
                    "title": f"TC{idx:02d} - Verify API Endpoint {ep} response and schema",
                    "description": f"Validate API response code, payload contract, and latency for {ep}",
                    "preconditions": request.preconditions or "API service is deployed and token is valid",
                    "steps": f"1. Send GET request to {ep}\n2. Verify HTTP status code is 200\n3. Verify JSON schema conforms to contract\n4. Send invalid payload to {ep}\n5. Verify 400 Bad Request error response is returned",
                    "expected_result": "API responds with valid schema and handles invalid parameters with clear errors",
                    "status": "ready",
                    "priority": "high",
                    "category": "api",
                })
        else:
            tables = re.findall(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)', content, re.IGNORECASE)
            if not tables:
                tables = re.findall(r'table\s+([a-zA-Z0-9_]+)', content, re.IGNORECASE)
            tables = list(dict.fromkeys(tables))[:12]
            if not tables:
                tables = ["users", "transactions", "orders"]
            for idx, tbl in enumerate(tables, 1):
                parsed_cases_data.append({
                    "title": f"TC{idx:02d} - Verify Table Integrity and Constraints for {tbl}",
                    "description": f"Validate primary key uniqueness, foreign keys, nullability, and index performance for {tbl}",
                    "preconditions": request.preconditions or "Database connection is active",
                    "steps": f"1. Query metadata for table '{tbl}'\n2. Verify primary key constraint is enforced\n3. Attempt inserting duplicate primary key\n4. Verify duplicate key violation is raised\n5. Insert valid record and verify row presence",
                    "expected_result": f"Table '{tbl}' preserves referential integrity and enforces schema constraints",
                    "status": "ready",
                    "priority": "high",
                    "category": "database",
                })
    else:
        target_nav_url = request.target_url or application.target
        parsed_cases_data = _parse_text_blocks(content, target_nav_url)

    proposals = _convert_to_proposal_items(parsed_cases_data, application)
    return AIProposalResponse(
        application_id=request.application_id,
        source_filename=f"Direct {request.format.upper()} Input",
        summary=f"Synthesized {len(proposals)} recommended test case(s) from {request.format} specification. Review and curate before committing.",
        total_proposed=len(proposals),
        proposals=proposals,
    )


@router.post("/approve-proposals", response_model=list[TestCaseResponse], status_code=201)
def approve_and_commit_proposals(
    request: ApproveProposalsRequest,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> list[TestCase]:
    application = (
        db.query(Application)
        .filter(Application.id == request.application_id, Application.created_by == user.id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    if request.replace_existing:
        existing_case_ids = [
            tc.id
            for tc in db.query(TestCase.id).filter(
                TestCase.application_id == request.application_id,
                TestCase.created_by == user.id,
            ).all()
        ]
        if existing_case_ids:
            db.query(TestCaseAutomation).filter(TestCaseAutomation.test_case_id.in_(existing_case_ids)).delete(synchronize_session=False)
            db.query(TestCase).filter(TestCase.id.in_(existing_case_ids)).delete(synchronize_session=False)

    created_cases = []
    for approved_case in request.approved_cases:
        normalized_status = _normalise_case_status(approved_case.status)
        tc = TestCase(
            application_id=request.application_id,
            title=approved_case.title.strip()[:200],
            description=approved_case.description,
            preconditions=approved_case.preconditions,
            steps=approved_case.steps,
            expected_result=approved_case.expected_result,
            status=normalized_status,
            priority=getattr(approved_case, "priority", "medium"),
            category=getattr(approved_case, "category", "positive"),
            tags=getattr(approved_case, "tags", ["approved_proposal"]),
            version=1,
            automation_status="automated",
            test_data=getattr(approved_case, "test_data", None),
            created_by=user.id,
        )
        db.add(tc)
        created_cases.append(tc)

    db.flush()
    # Attach compiled automation steps
    for case in created_cases:
        steps, checks = build_case_automation_from_text(case, application)
        if steps or checks:
            db.add(TestCaseAutomation(
                test_case_id=case.id,
                steps=steps,
                checks=checks,
                updated_by=user.id,
            ))

    log_audit_event(
        db,
        user_id=user.id,
        action="test_case.proposals.approved",
        resource_type="application",
        resource_id=request.application_id,
        metadata={"approved_count": len(created_cases), "replaced_existing": request.replace_existing},
    )
    db.commit()
    for case in created_cases:
        db.refresh(case)
    return created_cases


@router.post("/import/{application_id}", response_model=list[TestCaseResponse], status_code=201)
async def import_test_cases(
    application_id: int,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
    file: UploadFile = File(...),
) -> list[TestCase]:
    application = db.query(Application).filter(Application.id == application_id, Application.created_by == user.id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    filename = file.filename or ""
    allowed_extensions = (".csv", ".xlsx", ".xls", ".txt", ".md", ".json", ".text", ".markdown")
    if not filename.lower().endswith(allowed_extensions):
        raise HTTPException(status_code=400, detail="Choose a CSV, Excel, TXT, Markdown, or JSON file")
    try:
        rows = _parse_import(await file.read(), filename)
    except (UnicodeDecodeError, ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as error:
        raise HTTPException(status_code=400, detail=f"Unable to read file: {error}") from error
    rows = _dedupe_import_rows(rows)
    if not rows:
        raise HTTPException(status_code=400, detail="The file does not contain any test cases")

    # Replace the current case library for this application so each upload
    # reflects exactly what is in the latest file.
    existing_case_ids = [
        test_case.id
        for test_case in db.query(TestCase.id).filter(
            TestCase.application_id == application_id,
            TestCase.created_by == user.id,
        ).all()
    ]
    if existing_case_ids:
        db.query(TestCaseAutomation).filter(TestCaseAutomation.test_case_id.in_(existing_case_ids)).delete(synchronize_session=False)
        db.query(TestCase).filter(TestCase.id.in_(existing_case_ids)).delete(synchronize_session=False)

    from app.services.ai_service import auto_parameterize_case_steps

    created = []
    for row in rows:
        raw_steps = row.get("steps") or ""
        raw_exp = row.get("expected_result") or ""
        raw_cat = row.get("category") or "positive"
        param_steps, param_exp, param_td = auto_parameterize_case_steps(
            raw_steps,
            expected_result=raw_exp,
            category=raw_cat,
        )
        case_data_dict = param_td if param_td else None
        case_data = json.dumps(case_data_dict) if case_data_dict else None
        clean_row = {k: v for k, v in row.items() if k not in {"status", "steps", "expected_result", "test_data"}}
        created.append(
            TestCase(
                application_id=application_id,
                created_by=user.id,
                status=_normalise_case_status(row.get("status")),
                steps=param_steps,
                expected_result=param_exp,
                test_data=case_data,
                **clean_row,
            )
        )
    db.add_all(created)
    log_audit_event(
        db,
        user_id=user.id,
        action="test_case.import",
        resource_type="application",
        resource_id=application_id,
        metadata={"imported_count": len(created), "filename": filename},
    )
    db.commit()
    for test_case in created:
        db.refresh(test_case)
    _index_cases_in_vector_store(application_id, created)
    return created


@router.post("/application/{application_id}/check-similarity")
async def check_case_similarity(
    application_id: int,
    db: DbSession,
    title: str = Body(default="", embed=True),
    steps: str = Body(default="", embed=True),
    user: User = Depends(current_user),
) -> list[dict[str, Any]]:
    application = db.query(Application).filter(Application.id == application_id, Application.created_by == user.id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    from app.services.vector_service import VectorStoreService
    vstore = VectorStoreService(application_id)
    return await vstore.find_duplicate_or_similar_cases(title, steps)


@router.delete("/application/{application_id}/drafts", response_model=dict[str, int])
def delete_application_drafts(
    application_id: int,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> dict[str, int]:
    application = db.query(Application).filter(Application.id == application_id, Application.created_by == user.id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    normalized_status = func.lower(func.trim(func.coalesce(TestCase.status, "")))
    draft_case_ids = [
        test_case_id
        for (test_case_id,) in db.query(TestCase.id).filter(
            TestCase.application_id == application_id,
            TestCase.created_by == user.id,
            normalized_status == "draft",
        ).all()
    ]

    if draft_case_ids:
        db.query(TestCaseAutomation).filter(TestCaseAutomation.test_case_id.in_(draft_case_ids)).delete(synchronize_session=False)
        db.query(TestCase).filter(TestCase.id.in_(draft_case_ids)).delete(synchronize_session=False)
    log_audit_event(
        db,
        user_id=user.id,
        action="test_case.draft.delete",
        resource_type="application",
        resource_id=application_id,
        metadata={"deleted_count": len(draft_case_ids)},
    )
    db.commit()
    return {"deleted_count": len(draft_case_ids)}


@router.delete("/application/{application_id}/all", status_code=204)
def delete_all_application_test_cases(
    application_id: int,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> None:
    application = db.query(Application).filter(Application.id == application_id, Application.created_by == user.id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    test_case_ids = [
        test_case.id
        for test_case in db.query(TestCase.id).filter(
            TestCase.application_id == application_id,
            TestCase.created_by == user.id,
        ).all()
    ]
    if test_case_ids:
        db.query(TestCaseAutomation).filter(TestCaseAutomation.test_case_id.in_(test_case_ids)).delete(synchronize_session=False)
        db.query(TestCase).filter(TestCase.id.in_(test_case_ids)).delete(synchronize_session=False)
    log_audit_event(
        db,
        user_id=user.id,
        action="test_case.all.delete",
        resource_type="application",
        resource_id=application_id,
        metadata={"deleted_count": len(test_case_ids)},
    )
    db.commit()


@router.delete("/bulk", response_model=TestCaseBulkDeleteResponse)
def delete_selected_test_cases(
    request: TestCaseBulkDeleteRequest,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> TestCaseBulkDeleteResponse:
    requested_ids = sorted(set(request.test_case_ids))
    owned_cases = (
        db.query(TestCase)
        .join(Application, Application.id == TestCase.application_id)
        .filter(
            TestCase.id.in_(requested_ids),
            TestCase.created_by == user.id,
            Application.created_by == user.id,
        )
        .all()
    )
    owned_ids = {case.id for case in owned_cases}
    missing_ids = [case_id for case_id in requested_ids if case_id not in owned_ids]
    if missing_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more selected test cases were not found")

    active_case_ids = {
        case_id
        for (case_id,) in (
            db.query(CaseExecution.test_case_id)
            .join(TestRun, TestRun.id == CaseExecution.run_id)
            .filter(
                CaseExecution.test_case_id.in_(requested_ids),
                TestRun.created_by == user.id,
                TestRun.status.in_(["queued", "running"]),
            )
            .all()
        )
    }
    if active_case_ids:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stop active runs before deleting the selected test cases")

    db.query(TestCaseAutomation).filter(TestCaseAutomation.test_case_id.in_(requested_ids)).delete(synchronize_session=False)
    db.query(CaseExecution).filter(CaseExecution.test_case_id.in_(requested_ids)).delete(synchronize_session=False)
    db.query(TestCase).filter(TestCase.id.in_(requested_ids), TestCase.created_by == user.id).delete(synchronize_session=False)
    log_audit_event(
        db,
        user_id=user.id,
        action="test_case.bulk.delete",
        resource_type="test_case",
        resource_id=",".join(str(case_id) for case_id in requested_ids),
        metadata={"requested_count": len(requested_ids), "deleted_count": len(owned_cases)},
    )
    db.commit()
    return TestCaseBulkDeleteResponse(requested_count=len(requested_ids), deleted_count=len(owned_cases))


@router.delete("/{test_case_id}", status_code=204)
def delete_test_case(
    test_case_id: int,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> None:
    test_case = db.query(TestCase).filter(TestCase.id == test_case_id, TestCase.created_by == user.id).first()
    if not test_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")
    active_run = (
        db.query(TestRun.id)
        .join(CaseExecution, CaseExecution.run_id == TestRun.id)
        .filter(
            CaseExecution.test_case_id == test_case_id,
            TestRun.created_by == user.id,
            TestRun.status.in_(["queued", "running"]),
        )
        .first()
    )
    if active_run:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stop the active run before deleting this test case")
    db.query(TestCaseAutomation).filter(TestCaseAutomation.test_case_id == test_case_id).delete(synchronize_session=False)
    db.query(CaseExecution).filter(CaseExecution.test_case_id == test_case_id).delete(synchronize_session=False)
    log_audit_event(
        db,
        user_id=user.id,
        action="test_case.delete",
        resource_type="test_case",
        resource_id=test_case_id,
    )
    db.delete(test_case)
    db.commit()


@router.post("/generate-ai", response_model=list[TestCaseResponse], status_code=201)
async def generate_ai_test_cases_generic_endpoint(
    request: AITestCaseGenerateRequest,
    http_request: Request,
    response: Response,
    db: DbSession,
    application_id: int | None = None,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> list[TestCase]:
    app_id = application_id
    if not app_id:
        app = db.query(Application).filter(Application.created_by == user.id).first()
        if not app:
            raise HTTPException(status_code=404, detail="No application found")
        app_id = app.id
    return await generate_ai_test_cases_endpoint(app_id, request, http_request, response, db, user)


@router.post("/{application_id}/generate-ai", response_model=list[TestCaseResponse], status_code=201)
async def generate_ai_test_cases_endpoint(
    application_id: int,
    request: AITestCaseGenerateRequest,
    http_request: Request,
    response: Response,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> list[TestCase]:
    generation_id = str(uuid4())
    started_at = time.perf_counter()
    log_event(
        logger,
        "ai_generation_started",
        generation_id=generation_id,
        session_id=generation_id,
        correlation_id=getattr(http_request.state, "correlation_id", ""),
        user_id=user.id,
        input_source=request.input_format,
        provider=request.provider,
        model=request.model,
        application_id=application_id,
        prompt_length=len(request.prompt),
    )
    application = db.query(Application).filter(Application.id == application_id, Application.created_by == user.id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    if request.min_steps_per_case > request.max_steps_per_case:
        raise HTTPException(status_code=400, detail="min_steps_per_case cannot be greater than max_steps_per_case")
    provider_metadata = get_ai_provider_metadata()
    try:
        agent_trace = get_agent_trace_metadata(["planner", "generator"])
        agent_guidance = build_agent_guidance_block(["planner", "generator"])
    except AgentDefinitionError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    agent_trace_by_key = {item["key"]: item for item in agent_trace}
    augmented_prompt = request.prompt.strip()
    if agent_guidance:
        augmented_prompt = f"{augmented_prompt}\n\n{agent_guidance}"
    target = (request.target_url or application.target).strip()
    if application.platform == "web":
        try:
            validate_target(target)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if target != application.target:
            application.target = target
            db.add(application)
            db.commit()
            db.refresh(application)
    reference_case_rows = (
        db.query(TestCase.title, TestCase.steps, TestCase.expected_result)
        .filter(
            TestCase.application_id == application_id,
            TestCase.created_by == user.id,
        )
        .order_by(TestCase.updated_at.desc(), TestCase.id.desc())
        .limit(12)
        .all()
    )
    reference_case_snippets = []
    for row in reference_case_rows:
        title = (row.title or "").strip()
        first_step = ""
        for raw_line in (row.steps or "").splitlines():
            cleaned = re.sub(r"^\d+[\).:\-\s]+", "", raw_line.strip())
            if cleaned:
                first_step = cleaned
                break
        expected = (row.expected_result or "").strip()
        snippet_parts = [part for part in [title, first_step, expected] if part]
        if snippet_parts:
            reference_case_snippets.append(" | ".join(snippet_parts)[:300])
    try:
        generated = await generate_ai_test_cases(
            application_name=application.name,
            platform=application.platform,
            target=target,
            user_prompt=augmented_prompt,
            max_cases=request.max_cases,
            include_authenticated_snapshot=request.include_authenticated_snapshot,
            login_email_selector=request.login_email_selector,
            login_password_selector=request.login_password_selector,
            login_submit_selector=request.login_submit_selector,
            min_steps_per_case=request.min_steps_per_case,
            max_steps_per_case=request.max_steps_per_case,
            include_negative_scenarios=request.include_negative_scenarios,
            include_accessibility_checks=request.include_accessibility_checks,
            include_api_validations=request.include_api_validations,
            include_performance_scenarios=request.include_performance_scenarios,
            performance_budget=request.performance_budget or "",
            input_format=request.input_format,
            include_positive_scenarios=request.include_positive_scenarios,
            include_boundary_scenarios=request.include_boundary_scenarios,
            include_edge_cases=request.include_edge_cases,
            include_security_scenarios=request.include_security_scenarios,
            include_validation_rules=request.include_validation_rules,
            module_focus=request.module_focus or "",
            document_context=request.document_context or "",
            reference_cases=reference_case_snippets,
            provider=request.provider,
            model=request.model,
            login_email=getattr(request, "login_email", None),
            login_password=getattr(request, "login_password", None),
        )
    except AIServiceError as error:
        log_event(
            logger,
            "ai_generation_failed",
            generation_id=generation_id,
            session_id=generation_id,
            user_id=user.id,
            application_id=application_id,
            provider=request.provider,
            model=request.model,
            error=str(error),
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )
        raise HTTPException(status_code=422, detail=str(error)) from error
    summary_text = (generated.summary or "").strip()
    generation_note = re.sub(r"\s+", " ", (generated.generation_note or summary_text).strip())
    generated_provider = (generated.generation_provider or "").strip()
    configured_provider = str(provider_metadata.get("provider") or "unknown")
    configured_model = str(provider_metadata.get("model") or "unknown")
    effective_provider = generated_provider or configured_provider
    provider_configured = bool(provider_metadata.get("configured"))

    if request.replace_existing_drafts:
        draft_case_ids = [
            test_case.id
            for test_case in db.query(TestCase.id).filter(
                TestCase.application_id == application_id,
                TestCase.created_by == user.id,
                TestCase.status == "draft",
            ).all()
        ]
        if draft_case_ids:
            db.query(TestCaseAutomation).filter(TestCaseAutomation.test_case_id.in_(draft_case_ids)).delete(synchronize_session=False)
            db.query(TestCase).filter(TestCase.id.in_(draft_case_ids)).delete(synchronize_session=False)

    existing_titles = [
        title
        for (title,) in db.query(TestCase.title).filter(
            TestCase.application_id == application_id,
            TestCase.created_by == user.id,
        ).all()
    ]
    next_tc_number = max(
        (
            number
            for title in existing_titles
            if (number := _extract_tc_number(title)) is not None
        ),
        default=0,
    ) + 1

    created_cases: list[TestCase] = []
    seen_titles: set[str] = set()
    seen_generated_case_keys: set[str] = set()
    validation_counts: dict[str, int] = {state: 0 for state in VALID_GENERATION_STATES}
    case_validation_metadata: dict[int, dict[str, str | int | bool]] = {}
    target_url = (target or application.target or "").strip()
    for generated_case in generated.test_cases:
        validation_state, validation_reason = _classify_generated_case(
            title=generated_case.title,
            steps=generated_case.steps,
            expected_result=generated_case.expected_result,
            min_steps_per_case=request.min_steps_per_case,
            max_steps_per_case=request.max_steps_per_case,
            seen_keys=seen_generated_case_keys,
        )
        if validation_state not in VALID_GENERATION_STATES:
            validation_state = "INVALID"
            validation_reason = "Unknown validation state"
        validation_counts[validation_state] += 1
        if validation_state in {"INVALID", "DUPLICATE"}:
            continue

        generated_step_count = _count_case_steps(generated_case.steps)
        suffix = _title_suffix_without_tc_prefix(generated_case.title)
        generated_status = (
            "draft"
            if validation_state == "NEEDS_REVIEW"
            else _normalise_case_status(generated_case.status)
        )
        existing_case: TestCase | None = None
        title = ""
        title_key = ""

        while True:
            title = f"TC{next_tc_number:02d} - {suffix}"
            title_key = _normalise_case_key(title)
            next_tc_number += 1
            if not title_key or title_key in seen_titles:
                continue
            existing_case = (
                db.query(TestCase)
                .filter(
                    TestCase.application_id == application_id,
                    TestCase.created_by == user.id,
                    func.lower(func.trim(func.coalesce(TestCase.title, ""))) == title_key,
                )
                .first()
            )
            if not existing_case:
                break
            existing_status = _normalise_case_status(existing_case.status)
            if existing_status == "ready" and generated_status == "draft":
                # Keep ready baseline as-is and allocate a fresh numbered title for new draft coverage.
                continue
            break

        seen_titles.add(title_key)
        case_data_dict: dict[str, str] = {}
        if generated_case.test_data and isinstance(generated_case.test_data, dict):
            case_data_dict.update({str(k): str(v) for k, v in generated_case.test_data.items() if not str(k).startswith("_") and str(v).strip()})
        case_data = json.dumps(case_data_dict) if case_data_dict else None

        if existing_case:
            existing_case.title = title
            existing_case.description = generated_case.description
            existing_case.preconditions = generated_case.preconditions
            existing_case.steps = generated_case.steps
            existing_case.expected_result = generated_case.expected_result
            existing_case.status = generated_status
            existing_case.priority = generated_case.priority
            existing_case.category = generated_case.category
            existing_case.tags = generated_case.tags
            if case_data:
                existing_case.test_data = case_data
            db.add(existing_case)
            case_validation_metadata[id(existing_case)] = {
                "validation_state": validation_state,
                "validation_reason": validation_reason,
                "step_count": generated_step_count,
            }
            created_cases.append(existing_case)
            continue

        case = TestCase(
            application_id=application_id,
            created_by=user.id,
            title=title,
            description=generated_case.description,
            preconditions=generated_case.preconditions,
            steps=generated_case.steps,
            expected_result=generated_case.expected_result,
            status=generated_status,
            priority=generated_case.priority,
            category=generated_case.category,
            tags=generated_case.tags,
            test_data=case_data,
        )
        db.add(case)
        case_validation_metadata[id(case)] = {
            "validation_state": validation_state,
            "validation_reason": validation_reason,
            "step_count": generated_step_count,
        }
        created_cases.append(case)

    db.flush()
    for case in created_cases:
        generated_steps, generated_checks = build_case_automation_from_text(case, application)
        if not generated_steps and not generated_checks:
            continue
        automation = db.get(TestCaseAutomation, case.id)
        if automation is None:
            automation = TestCaseAutomation(test_case_id=case.id, updated_by=user.id)
            db.add(automation)
        automation.steps = generated_steps
        automation.checks = generated_checks
        automation.updated_by = user.id

    effective_generation_mode = "provider"
    response.headers["X-AI-QA-Engine-AI-Generation-Mode"] = effective_generation_mode
    response.headers["X-AI-QA-Engine-AI-Provider"] = effective_provider
    response.headers["X-AI-QA-Engine-AI-Provider-Configured"] = "true" if provider_configured else "false"
    if generation_note:
        response.headers["X-AI-QA-Engine-AI-Generation-Note"] = generation_note[:280]
    for case in created_cases:
        case_trace = case_validation_metadata.get(id(case), {})
        log_audit_event(
            db,
            user_id=user.id,
            action="test_case.ai_trace",
            resource_type="test_case",
            resource_id=case.id,
            metadata={
                "application_id": application_id,
                "target_url": target_url,
                "provider": effective_provider,
                "configured_provider": configured_provider,
                "model": configured_model,
                "provider_configured": provider_configured,
                "provider_configuration_error": provider_metadata.get("configuration_error"),
                "effective_generation_mode": effective_generation_mode,
                "validation_state": case_trace.get("validation_state", "VALID"),
                "validation_reason": case_trace.get("validation_reason", ""),
                "step_count": case_trace.get("step_count"),
                "planner_used": generated.planner_used,
                "planner_provider": generated.planner_provider,
                "planner_model": generated.planner_model,
                "planner_case_target": generated.planner_case_target,
                "generator_call_count": generated.generator_call_count,
                "planner_agent": agent_trace_by_key.get("planner", {}),
                "generator_agent": agent_trace_by_key.get("generator", {}),
                "summary_excerpt": summary_text[:500],
                "generation_note": generation_note[:500],
            },
        )

    log_audit_event(
        db,
        user_id=user.id,
        action="test_case.generate_ai",
        resource_type="application",
        resource_id=application_id,
        metadata={
            "generated_count": len(created_cases),
            "replace_drafts": request.replace_existing_drafts,
            "validation_counts": validation_counts,
            "dropped_count": validation_counts["INVALID"] + validation_counts["DUPLICATE"],
            "planner_agent_version": agent_trace_by_key.get("planner", {}).get("version"),
            "generator_agent_version": agent_trace_by_key.get("generator", {}).get("version"),
            "provider": effective_provider,
            "configured_provider": configured_provider,
            "model": configured_model,
            "provider_configured": provider_configured,
            "effective_generation_mode": effective_generation_mode,
            "planner_used": generated.planner_used,
            "planner_provider": generated.planner_provider,
            "planner_model": generated.planner_model,
            "planner_case_target": generated.planner_case_target,
            "generator_call_count": generated.generator_call_count,
            "generation_note": generation_note[:500],
        },
    )
    db.commit()
    for case in created_cases:
        db.refresh(case)
    log_event(
        logger,
        "ai_generation_saved",
        generation_id=generation_id,
        session_id=generation_id,
        user_id=user.id,
        application_id=application_id,
        provider=effective_provider,
        model=configured_model,
        generated_case_count=len(created_cases),
        validation_counts=validation_counts,
        validation_status="passed",
        duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
    )
    return created_cases


@router.post("/{application_id}/generate", response_model=list[TestCaseResponse], status_code=201)
def generate_sample_test_cases(
    application_id: int,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> list[TestCase]:
	application = db.query(Application).filter(Application.id == application_id, Application.created_by == user.id).first()
	if not application:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
	
	# Comprehensive test cases template for real-world application testing
	sample_cases = [
		# Authentication & Access Control
		{
			"title": "User Login with Valid Credentials",
			"description": "Verify user can successfully login with valid credentials and access protected pages",
			"preconditions": "User has a valid account and is on the login page",
			"steps": "1. Navigate to login page\n2. Enter valid email address\n3. Enter valid password\n4. Click 'Sign In' button\n5. Verify redirect to dashboard",
			"expected_result": "User is logged in successfully, session is created, and user is redirected to dashboard",
			"status": "draft",
		},
		{
			"title": "Login with Invalid Email Format",
			"description": "Verify system rejects invalid email format at login",
			"preconditions": "User is on the login page",
			"steps": "1. Enter invalid email format (e.g., 'notanemail')\n2. Click 'Sign In' button\n3. Observe error message",
			"expected_result": "Email validation error is displayed, login is prevented",
			"status": "draft",
		},
		{
			"title": "Login with Invalid Password",
			"description": "Verify system rejects incorrect password",
			"preconditions": "User has a valid account and is on the login page",
			"steps": "1. Enter valid email\n2. Enter incorrect password\n3. Click 'Sign In' button\n4. Observe error",
			"expected_result": "Authentication error message displayed, login denied",
			"status": "draft",
		},
		{
			"title": "Session Timeout Behavior",
			"description": "Verify user session expires after inactivity",
			"preconditions": "User is logged in and has been idle for the configured timeout period",
			"steps": "1. Log in successfully\n2. Wait for session timeout (typically 30 minutes)\n3. Attempt to access protected page\n4. Observe redirect",
			"expected_result": "User is redirected to login page with session expired message",
			"status": "draft",
		},
		{
			"title": "User Logout Functionality",
			"description": "Verify logout clears session and redirects to login page",
			"preconditions": "User is logged in",
			"steps": "1. Locate logout button in menu\n2. Click logout\n3. Verify redirect to login page\n4. Attempt to go back to protected page",
			"expected_result": "Session is cleared, user cannot access protected pages without re-login",
			"status": "draft",
		},
		# Navigation & UI
		{
			"title": "Main Navigation Menu",
			"description": "Verify all main navigation menu items are accessible and functional",
			"preconditions": "User is logged in and on the dashboard",
			"steps": "1. Locate navigation menu\n2. Click each menu item\n3. Verify page loads correctly\n4. Verify correct content is displayed",
			"expected_result": "All navigation links work, correct pages load, no 404 or 500 errors",
			"status": "draft",
		},
		{
			"title": "Responsive Design - Desktop View",
			"description": "Verify application displays correctly on desktop resolution",
			"preconditions": "Application is open on a desktop browser (1920x1080)",
			"steps": "1. Open application in desktop browser\n2. Navigate through main pages\n3. Verify layout, buttons, and text are properly aligned\n4. Check no content overflow",
			"expected_result": "All elements display correctly, no content overflow, buttons and links are clickable",
			"status": "draft",
		},
		{
			"title": "Responsive Design - Mobile View",
			"description": "Verify application displays correctly on mobile devices",
			"preconditions": "Application is open on a mobile browser (375x667 iPhone SE)",
			"steps": "1. Open application in mobile browser emulation\n2. Verify menu is accessible (hamburger or dropdown)\n3. Navigate through main pages\n4. Verify touch targets are adequate",
			"expected_result": "Mobile layout is responsive, navigation is accessible, all content is readable",
			"status": "draft",
		},
		{
			"title": "Button and Link Functionality",
			"description": "Verify all buttons and links on dashboard are clickable and functional",
			"preconditions": "User is logged in on the dashboard",
			"steps": "1. Identify all clickable buttons and links\n2. Click each one\n3. Verify appropriate action or navigation occurs\n4. Check no broken links (404)",
			"expected_result": "All buttons and links work as expected, no JavaScript errors in console",
			"status": "draft",
		},
		# Data & Operations
		{
			"title": "Create New Project",
			"description": "Verify user can create a new project with valid data",
			"preconditions": "User is logged in and on the projects page",
			"steps": "1. Click 'Create New Project' button\n2. Enter project name\n3. Enter project description\n4. Click 'Create' button\n5. Verify project appears in list",
			"expected_result": "Project is created successfully and appears in the project list with correct details",
			"status": "draft",
		},
		{
			"title": "Edit Project Details",
			"description": "Verify user can edit existing project information",
			"preconditions": "User is logged in and at least one project exists",
			"steps": "1. Click on a project to open\n2. Click 'Edit' button\n3. Modify project name or description\n4. Click 'Save' button\n5. Verify changes are saved",
			"expected_result": "Project details are updated and changes persist across page reloads",
			"status": "draft",
		},
		{
			"title": "Delete Project with Confirmation",
			"description": "Verify user can delete a project with proper confirmation",
			"preconditions": "User is logged in and project list is accessible",
			"steps": "1. Click delete button on a project\n2. Verify confirmation dialog appears\n3. Click 'Confirm Delete'\n4. Verify project is removed from list",
			"expected_result": "Project is deleted only after confirmation, project no longer appears in list",
			"status": "draft",
		},
		{
			"title": "Form Validation - Required Fields",
			"description": "Verify form validation prevents submission with empty required fields",
			"preconditions": "User is on a form page (create/edit project or similar)",
			"steps": "1. Leave required fields empty\n2. Attempt to submit form\n3. Observe validation messages\n4. Fill required fields and submit",
			"expected_result": "Form shows validation errors for empty required fields, submission is prevented until all required fields are filled",
			"status": "draft",
		},
		{
			"title": "Form Validation - Data Type Checks",
			"description": "Verify form validates data types correctly",
			"preconditions": "User is on a form with typed fields (email, number, date, etc.)",
			"steps": "1. Enter wrong data type (e.g., text in number field)\n2. Attempt to submit\n3. Observe error messages\n4. Enter correct data type",
			"expected_result": "Form rejects invalid data types and shows appropriate error messages",
			"status": "draft",
		},
		# Search & Filtering
		{
			"title": "Search Functionality",
			"description": "Verify search feature returns correct and relevant results",
			"preconditions": "User is logged in and search feature is accessible",
			"steps": "1. Enter a search query\n2. Click search button or press Enter\n3. Observe search results\n4. Verify results match the query",
			"expected_result": "Search returns relevant results, no results shown for non-matching queries, search completes in reasonable time",
			"status": "draft",
		},
		{
			"title": "Filter by Status",
			"description": "Verify filtering by status (draft, ready, running, completed) works correctly",
			"preconditions": "User is on a list page with status filter (e.g., test cases or projects)",
			"steps": "1. Apply filter by status (e.g., 'draft')\n2. Verify only items with selected status are shown\n3. Clear filter\n4. Verify all items are shown again",
			"expected_result": "Filter correctly displays/hides items based on selected status, can be toggled on/off",
			"status": "draft",
		},
		# Performance & Load
		{
			"title": "Page Load Time",
			"description": "Verify dashboard page loads within acceptable time",
			"preconditions": "User is logged in and dashboard page is ready to load",
			"steps": "1. Measure page load time using browser developer tools\n2. Navigate to dashboard\n3. Wait for page to fully load\n4. Record total load time",
			"expected_result": "Dashboard loads in under 3 seconds, all elements are visible and interactive",
			"status": "draft",
		},
		{
			"title": "Large Data Set Performance",
			"description": "Verify application handles large lists efficiently",
			"preconditions": "Application has 100+ test cases or projects in the database",
			"steps": "1. Navigate to list view with large dataset\n2. Verify page loads without lag\n3. Scroll through list\n4. Search or filter in the list",
			"expected_result": "List loads quickly, pagination or virtual scrolling works, search/filter respond quickly",
			"status": "draft",
		},
		# Error Handling
		{
			"title": "404 Error Page Handling",
			"description": "Verify 404 error is handled gracefully when accessing non-existent page",
			"preconditions": "User is logged in",
			"steps": "1. Type invalid URL in browser (e.g., /non-existent-page)\n2. Press Enter\n3. Observe error page",
			"expected_result": "User sees friendly 404 error message with option to go back to home or search",
			"status": "draft",
		},
		{
			"title": "Network Error Handling",
			"description": "Verify application handles network errors gracefully",
			"preconditions": "User is logged in and performing an action that requires API call",
			"steps": "1. Simulate network error (disable internet, throttle connection)\n2. Attempt to perform action (save, search, etc.)\n3. Observe error handling",
			"expected_result": "User sees clear error message, can retry operation, no server errors exposed to user",
			"status": "draft",
		},
		# Security
		{
			"title": "CSRF Token Validation",
			"description": "Verify CSRF protection is in place for form submissions",
			"preconditions": "User is logged in and on a page with forms",
			"steps": "1. Submit a form normally and verify it works\n2. Check for CSRF token in form\n3. Attempt to submit without valid token (if possible)",
			"expected_result": "Forms include CSRF tokens, invalid submissions are rejected",
			"status": "draft",
		},
		{
			"title": "Password Security",
			"description": "Verify password meets security requirements",
			"preconditions": "User is on the password change or account settings page",
			"steps": "1. Attempt to set weak password (less than 8 characters)\n2. Attempt password without special characters\n3. Set strong password with mix of characters",
			"expected_result": "Weak passwords are rejected with clear requirements message, strong password is accepted",
			"status": "draft",
		},
	]
	
	created_cases = []
	for case_data in sample_cases:
		test_case = TestCase(
			application_id=application_id,
			title=case_data["title"],
			description=case_data["description"],
			preconditions=case_data["preconditions"],
			steps=case_data["steps"],
			expected_result=case_data["expected_result"],
			status=case_data["status"],
			created_by=user.id,
		)
		db.add(test_case)
		created_cases.append(test_case)
	
	log_audit_event(
		db,
		user_id=user.id,
		action="test_case.generate_sample",
		resource_type="application",
		resource_id=application_id,
		metadata={"generated_count": len(created_cases)},
	)
	db.commit()
	for case in created_cases:
		db.refresh(case)
	
	return created_cases
