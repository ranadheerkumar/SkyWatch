"""Multi-framework test script generation engine.

Translates the framework-agnostic intermediate representation (IR) produced by
``build_case_automation_from_text()`` into executable test scripts for multiple
automation frameworks: Playwright TypeScript, Cypress JavaScript, Selenium
Python (pytest), Robot Framework, Java TestNG + Selenium, and Jest + Puppeteer.

Usage::

    from app.services.script_generators import generate_script, FRAMEWORK_REGISTRY

    output = generate_script("cypress", test_case, application, steps, checks)
    print(output.code)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import ScriptGenerator, ScriptOutput
from .playwright_gen import PlaywrightGenerator
from .cypress_gen import CypressGenerator
from .selenium_python_gen import SeleniumPythonGenerator
from .robot_gen import RobotFrameworkGenerator
from .java_testng_gen import JavaTestNGGenerator
from .jest_puppeteer_gen import JestPuppeteerGenerator

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.test_case import TestCase


FRAMEWORK_REGISTRY: dict[str, type[ScriptGenerator]] = {
    "playwright": PlaywrightGenerator,
    "cypress": CypressGenerator,
    "selenium_python": SeleniumPythonGenerator,
    "robot": RobotFrameworkGenerator,
    "java_testng": JavaTestNGGenerator,
    "jest_puppeteer": JestPuppeteerGenerator,
}

SUPPORTED_FRAMEWORKS: list[str] = list(FRAMEWORK_REGISTRY.keys())


def generate_script(
    framework: str,
    test_case: "TestCase",
    application: "Application",
    steps: list[dict] | None = None,
    checks: list[dict] | None = None,
) -> ScriptOutput:
    """Generate a test script in the requested framework.

    If *steps* and *checks* are not provided, they are compiled from the test
    case text via ``build_case_automation_from_text()``.
    """
    generator_cls = FRAMEWORK_REGISTRY.get(framework.lower().strip())
    if generator_cls is None:
        raise ValueError(
            f"Unsupported framework '{framework}'. "
            f"Supported: {', '.join(SUPPORTED_FRAMEWORKS)}"
        )
    generator = generator_cls()
    return generator.generate(test_case, application, steps=steps, checks=checks)


__all__ = [
    "FRAMEWORK_REGISTRY",
    "SUPPORTED_FRAMEWORKS",
    "ScriptGenerator",
    "ScriptOutput",
    "generate_script",
]
