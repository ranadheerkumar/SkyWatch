from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import DbSession, current_user, require_roles
from app.models.application import Application
from app.models.test_dataset import TestDataset
from app.models.user import User
from app.schemas.test_data import (
    SmartTestDataGenerateRequest,
    SmartTestDataGenerateResponse,
    TestDatasetCreate,
    TestDatasetResponse,
    TestDatasetUpdate,
)
from app.services.audit import log_audit_event
from app.services.self_learning import SelfLearningEngine
from app.services.test_data_generator import TestDataGeneratorService

router = APIRouter(prefix="/test-data", tags=["test-data"])


@router.get("", response_model=list[TestDatasetResponse])
def list_test_datasets(
    db: DbSession,
    user: User = Depends(current_user),
) -> list[TestDataset]:
    return (
        db.query(TestDataset)
        .join(Application, Application.id == TestDataset.application_id)
        .filter(Application.created_by == user.id)
        .order_by(TestDataset.id.desc())
        .all()
    )


@router.get("/application/{application_id}", response_model=list[TestDatasetResponse])
def list_application_test_datasets(
    application_id: int,
    db: DbSession,
    user: User = Depends(current_user),
) -> list[TestDataset]:
    application = (
        db.query(Application)
        .filter(Application.id == application_id, Application.created_by == user.id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return (
        db.query(TestDataset)
        .filter(TestDataset.application_id == application_id, TestDataset.created_by == user.id)
        .order_by(TestDataset.id.desc())
        .all()
    )


@router.get("/{dataset_id}", response_model=TestDatasetResponse)
def get_test_dataset(
    dataset_id: int,
    db: DbSession,
    user: User = Depends(current_user),
) -> TestDataset:
    dataset = (
        db.query(TestDataset)
        .join(Application, Application.id == TestDataset.application_id)
        .filter(TestDataset.id == dataset_id, Application.created_by == user.id)
        .first()
    )
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return dataset


@router.post("", response_model=TestDatasetResponse, status_code=status.HTTP_201_CREATED)
def create_test_dataset(
    request: TestDatasetCreate,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> TestDataset:
    application = (
        db.query(Application)
        .filter(Application.id == request.application_id, Application.created_by == user.id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    dataset = TestDataset(
        application_id=request.application_id,
        name=request.name.strip(),
        description=request.description,
        data_rows=request.data_rows,
        created_by=user.id,
    )
    db.add(dataset)
    db.flush()
    log_audit_event(
        db,
        user_id=user.id,
        action="test_data.create",
        resource_type="test_dataset",
        resource_id=dataset.id,
        metadata={"name": dataset.name, "row_count": len(dataset.data_rows or [])},
    )
    db.commit()
    db.refresh(dataset)
    return dataset


@router.put("/{dataset_id}", response_model=TestDatasetResponse)
def update_test_dataset(
    dataset_id: int,
    request: TestDatasetUpdate,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> TestDataset:
    dataset = (
        db.query(TestDataset)
        .join(Application, Application.id == TestDataset.application_id)
        .filter(TestDataset.id == dataset_id, Application.created_by == user.id)
        .first()
    )
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    old_row_count = len(dataset.data_rows or [])
    if request.name is not None:
        dataset.name = request.name.strip()
    if request.description is not None:
        dataset.description = request.description
    if request.data_rows is not None:
        dataset.data_rows = request.data_rows

    db.add(dataset)
    log_audit_event(
        db,
        user_id=user.id,
        action="test_data.update",
        resource_type="test_dataset",
        resource_id=dataset.id,
        metadata={"old_row_count": old_row_count, "new_row_count": len(dataset.data_rows or [])},
    )
    db.commit()
    db.refresh(dataset)
    return dataset


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test_dataset(
    dataset_id: int,
    db: DbSession,
    user: User = Depends(require_roles("qa_lead", "admin")),
) -> None:
    dataset = (
        db.query(TestDataset)
        .join(Application, Application.id == TestDataset.application_id)
        .filter(TestDataset.id == dataset_id, Application.created_by == user.id)
        .first()
    )
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    db.delete(dataset)
    log_audit_event(
        db,
        user_id=user.id,
        action="test_data.delete",
        resource_type="test_dataset",
        resource_id=dataset_id,
        metadata={"name": dataset.name},
    )
    db.commit()


@router.post("/generate/{application_id}", response_model=SmartTestDataGenerateResponse, status_code=status.HTTP_201_CREATED)
async def generate_smart_test_data(
    application_id: int,
    request: SmartTestDataGenerateRequest,
    db: DbSession,
    user: User = Depends(require_roles("tester", "qa_lead", "admin")),
) -> SmartTestDataGenerateResponse:
    application = (
        db.query(Application)
        .filter(Application.id == application_id, Application.created_by == user.id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    generator = TestDataGeneratorService(application_id)
    rows = await generator.generate_dataset(
        dataset_name=request.name,
        description=request.description,
        field_names=request.field_names,
        scenario_types=request.scenario_types,
        row_count=request.row_count,
        provider=request.provider,
        model=request.model,
    )

    dataset_id = None
    if request.save_to_database:
        dataset = TestDataset(
            application_id=application_id,
            name=request.name.strip(),
            description=request.description or f"AI-generated {request.row_count}-row test dataset",
            data_rows=rows,
            created_by=user.id,
        )
        db.add(dataset)
        db.flush()
        dataset_id = dataset.id
        log_audit_event(
            db,
            user_id=user.id,
            action="test_data.generate_and_save",
            resource_type="test_dataset",
            resource_id=dataset.id,
            metadata={"name": dataset.name, "row_count": len(rows)},
        )
        db.commit()

    learned_metric = SelfLearningEngine.get_telemetry_metrics(application_id)

    return SmartTestDataGenerateResponse(
        application_id=application_id,
        dataset_id=dataset_id,
        name=request.name,
        row_count=len(rows),
        data_rows=rows,
        learned_entities_used=learned_metric.get("total_learned_locators", 0),
    )


@router.get("/learned/{application_id}")
def get_learned_application_entities(
    application_id: int,
    db: DbSession,
    user: User = Depends(current_user),
) -> dict:
    application = (
        db.query(Application)
        .filter(Application.id == application_id, Application.created_by == user.id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    from app.services.self_learning import _DISCOVERED_ENTITIES_CACHE
    learner = SelfLearningEngine(application_id)
    default_types = ["first_name", "last_name", "email", "phone", "barcode", "order_id", "status", "id", "city", "state", "zip_code", "address"]
    cached_types = [et for (app_id, et) in _DISCOVERED_ENTITIES_CACHE.keys() if app_id == application_id]
    all_types = list(dict.fromkeys(default_types + cached_types))
    pools = {}
    for et in all_types:
        entities = learner.get_discovered_entities(et, limit=20)
        if entities:
            pools[et] = entities

    return {
        "application_id": application_id,
        "application_name": application.name,
        "discovered_entity_pools": pools,
        "telemetry": SelfLearningEngine.get_telemetry_metrics(application_id),
    }


@router.get("/resolve-parameters/{application_id}")
def resolve_application_parameters(
    application_id: int,
    db: DbSession,
    user: User = Depends(current_user),
) -> dict:
    """
    Scans all test cases for an application, detects all {{parameter}} placeholders,
    and synthesizes/resolves realistic default values from live learned entities,
    attached datasets, and credentials for pre-populating Configure Run.
    """
    import re
    import json
    from uuid import uuid4
    from app.models.test_case import TestCase
    from app.api.v1.execution import _resolve_application_credentials_and_parameters

    application = (
        db.query(Application)
        .filter(Application.id == application_id, Application.created_by == user.id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    test_cases = (
        db.query(TestCase)
        .filter(TestCase.application_id == application_id, TestCase.created_by == user.id)
        .all()
    )

    detected_keys: set[str] = set()
    token_pattern = re.compile(r"\{\{\s*([A-Za-z0-9_.-]{1,63})\s*\}\}|\$\{\s*([A-Za-z0-9_.-]{1,63})\s*\}")

    # Scan test cases for all parameterized tokens
    for tc in test_cases:
        corpus = f"{tc.title} {tc.description or ''} {tc.preconditions or ''} {tc.steps} {tc.expected_result or ''}"
        for match in token_pattern.finditer(corpus):
            k = match.group(1) or match.group(2)
            if k and not k.startswith("_"):
                detected_keys.add(k.strip())

    # Always include login parameters if web application
    if application.platform == "web":
        detected_keys.add("login_email")
        detected_keys.add("login_password")

    # Base resolved application credentials
    base_creds = _resolve_application_credentials_and_parameters(db, application, None)
    learner = SelfLearningEngine(application_id)
    generator = TestDataGeneratorService(application_id)

    # Collect any explicit test case data dictionary rows
    tc_data_map: dict[str, str] = {}
    for tc in test_cases:
        if tc.test_data:
            if isinstance(tc.test_data, dict):
                for k, v in tc.test_data.items():
                    if k and str(v).strip() and not str(k).startswith("_"):
                        tc_data_map[str(k).strip()] = str(v).strip()
            elif isinstance(tc.test_data, str):
                try:
                    parsed_td = json.loads(tc.test_data)
                    if isinstance(parsed_td, dict):
                        for k, v in parsed_td.items():
                            if k and str(v).strip() and not str(k).startswith("_"):
                                tc_data_map[str(k).strip()] = str(v).strip()
                    elif isinstance(parsed_td, list) and parsed_td and isinstance(parsed_td[0], dict):
                        for k, v in parsed_td[0].items():
                            if k and str(v).strip() and not str(k).startswith("_"):
                                tc_data_map[str(k).strip()] = str(v).strip()
                except Exception:
                    pass

    # Collect from saved datasets
    datasets = (
        db.query(TestDataset)
        .filter(TestDataset.application_id == application_id, TestDataset.created_by == user.id)
        .all()
    )
    dataset_data_map: dict[str, str] = {}
    for ds in datasets:
        for row in (ds.data_rows or []):
            if isinstance(row, dict):
                for k, v in row.items():
                    if k and str(v).strip() and not str(k).startswith("_"):
                        dataset_data_map[str(k).strip()] = str(v).strip()

    resolved_parameters = []
    ordered_keys = sorted(list(detected_keys), key=lambda x: (
        0 if x == "login_email" else 1 if x == "login_password" else 2,
        x.lower()
    ))

    for key in ordered_keys:
        val = None
        source = "generated"
        is_sensitive = "password" in key.lower() or "secret" in key.lower() or "token" in key.lower()

        # 1. Credentials
        if key in base_creds and base_creds[key]:
            val = base_creds[key]
            source = "credentials"
        # 2. Test case attached data
        elif key in tc_data_map and tc_data_map[key]:
            val = tc_data_map[key]
            source = "test_case_data"
        # 3. Test dataset
        elif key in dataset_data_map and dataset_data_map[key]:
            val = dataset_data_map[key]
            source = "test_dataset"
        # 4. Self-Learning entity pool
        if not val:
            entities = learner.get_discovered_entities(key, limit=1)
            if entities:
                val = str(entities[0])
                source = "learned_memory"
        # 5. Dynamic synthesis via generator
        if not val:
            norm_fld = re.sub(r"[^a-z0-9]", "_", key.lower()).strip("_")
            synth = generator._generate_valid_field(norm_fld or key.lower(), 0)
            if synth:
                val = str(synth)
                source = "synthesized"

        resolved_parameters.append({
            "id": f"param-{key}-{uuid4().hex[:6]}",
            "key": key,
            "value": str(val or ""),
            "sensitive": is_sensitive,
            "source": source,
        })

    return {
        "application_id": application_id,
        "application_name": application.name,
        "parameters": resolved_parameters,
        "detected_keys": ordered_keys,
    }
