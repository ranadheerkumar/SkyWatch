"""Playwright TypeScript script generator.

Wraps the existing ``generate_playwright_spec_code()`` from
``automation_builder`` to conform to the ``ScriptGenerator`` interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import ScriptGenerator

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.test_case import TestCase


class PlaywrightGenerator(ScriptGenerator):
    """Generates Playwright TypeScript test specs (.spec.ts)."""

    def framework_name(self) -> str:
        return "Playwright TypeScript"

    def language(self) -> str:
        return "typescript"

    def file_extension(self) -> str:
        return ".spec.ts"

    def generate_code(
        self,
        test_case: "TestCase",
        application: "Application",
        steps: list[dict],
        checks: list[dict],
    ) -> str:
        from app.services.automation_builder import generate_playwright_spec_code

        return generate_playwright_spec_code(
            test_case, application, steps=steps, checks=checks
        )
