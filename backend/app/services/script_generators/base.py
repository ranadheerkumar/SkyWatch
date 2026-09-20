"""Abstract base class for multi-framework script generators."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.test_case import TestCase


@dataclass(frozen=True)
class ScriptOutput:
    """Result of generating a test script."""

    code: str
    filename: str
    framework: str
    language: str
    file_extension: str


class ScriptGenerator(ABC):
    """Base class that all framework generators must extend."""

    @abstractmethod
    def framework_name(self) -> str:
        """Human-readable framework name (e.g. 'Playwright TypeScript')."""

    @abstractmethod
    def language(self) -> str:
        """Target language identifier (e.g. 'typescript', 'python')."""

    @abstractmethod
    def file_extension(self) -> str:
        """File extension including dot (e.g. '.spec.ts')."""

    @abstractmethod
    def generate_code(
        self,
        test_case: "TestCase",
        application: "Application",
        steps: list[dict],
        checks: list[dict],
    ) -> str:
        """Produce the script source code from the compiled IR steps and checks."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        test_case: "TestCase",
        application: "Application",
        steps: list[dict] | None = None,
        checks: list[dict] | None = None,
    ) -> ScriptOutput:
        """Full pipeline: compile steps if needed, generate code, produce output."""
        if steps is None or checks is None:
            from app.services.automation_builder import build_case_automation_from_text

            compiled_steps, compiled_checks = build_case_automation_from_text(
                test_case, application
            )
            steps = steps or compiled_steps
            checks = checks or compiled_checks

        code = self.generate_code(test_case, application, steps, checks)
        filename = self.file_naming(test_case)

        return ScriptOutput(
            code=code,
            filename=filename,
            framework=self.framework_name(),
            language=self.language(),
            file_extension=self.file_extension(),
        )

    def file_naming(self, test_case: "TestCase") -> str:
        """Generate a safe filename for the test script."""
        safe_name = re.sub(r"[^\w\-]", "_", test_case.title.lower()).strip("_")
        return f"{safe_name or f'tc_{test_case.id}'}{self.file_extension()}"

    @staticmethod
    def safe_title(test_case: "TestCase") -> str:
        """Sanitize a test case title for use in code comments/strings."""
        return (
            re.sub(r"[^\w\s\-.,:()]", "", test_case.title).strip()
            or f"TC{test_case.id:02d}"
        )

    @staticmethod
    def escape_single_quotes(value: str) -> str:
        return value.replace("'", "\\'")

    @staticmethod
    def escape_double_quotes(value: str) -> str:
        return value.replace('"', '\\"')
