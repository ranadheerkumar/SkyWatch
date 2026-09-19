"""Unit tests for ReportService."""

from __future__ import annotations

import pytest
from app.core.database import Base, SessionLocal, engine
from app.models.application import Application
from app.models.defect import Defect
from app.models.test_case import TestCase
from app.models.test_run import TestRun
from app.models.user import User
from app.services.report_service import ReportService


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield


def test_generate_application_quality_report():
    with SessionLocal() as db:
        # Create test user
        user = db.query(User).filter(User.email == "report_test@example.com").first()
        if not user:
            user = User(email="report_test@example.com", password_hash="hash", role="admin")
            db.add(user)
            db.commit()
            db.refresh(user)

        # Create test app
        app = Application(
            name="Report Test App",
            target="https://app.test",
            created_by=user.id,
            platform="web",
        )
        db.add(app)
        db.commit()
        db.refresh(app)

        # Add some test cases
        tc1 = TestCase(
            title="Login Success",
            application_id=app.id,
            created_by=user.id,
            status="ready",
            automation_status="automated",
            category="functional",
            priority="high",
        )
        tc2 = TestCase(
            title="Cart Empty Warning",
            application_id=app.id,
            created_by=user.id,
            status="draft",
            automation_status="manual",
            category="ui",
            priority="medium",
        )
        db.add_all([tc1, tc2])

        # Add a run
        import uuid
        run = TestRun(
            id=uuid.uuid4().hex[:16],
            application_id=app.id,
            created_by=user.id,
            status="passed",
            result={"duration_ms": 1200.0},
        )
        db.add(run)

        # Add a defect
        defect = Defect(
            title="Button overlapping",
            application_id=app.id,
            created_by=user.id,
            severity="low",
            status="open",
        )
        db.add(defect)
        db.commit()

        # Generate report
        report = ReportService.generate_application_quality_report(app.id, db)

        assert report["application_name"] == "Report Test App"
        assert report["metrics"]["total_test_cases"] == 2
        assert report["metrics"]["automated_cases"] == 1
        assert report["metrics"]["pass_rate_percent"] == 100.0
        assert report["metrics"]["open_defects_count"] == 1
        assert report["metrics"]["quality_score"] > 0

        # Markdown format check
        md = ReportService.format_as_markdown(report)
        assert "# QA Quality & Release Readiness Report" in md
        assert "Report Test App" in md
        assert "Quality Score" in md
