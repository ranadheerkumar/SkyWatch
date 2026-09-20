"""Unit tests for the Multi-Framework Script Generation Engine."""

import os
import sys
import unittest

# Ensure backend root is in sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import types
if "app.services" not in sys.modules:
    dummy_services = types.ModuleType("app.services")
    dummy_services.__path__ = [os.path.join(BACKEND_DIR, "app", "services")]
    sys.modules["app.services"] = dummy_services

from app.services.script_generators.base import ScriptGenerator, ScriptOutput
from app.services.script_generators.cypress_gen import CypressGenerator
from app.services.script_generators.selenium_python_gen import SeleniumPythonGenerator
from app.services.script_generators.robot_gen import RobotFrameworkGenerator
from app.services.script_generators.java_testng_gen import JavaTestNGGenerator
from app.services.script_generators.jest_puppeteer_gen import JestPuppeteerGenerator
from app.services.script_generators import FRAMEWORK_REGISTRY, generate_script


class MockApplication:
    id = 1
    name = "Apollo Retail"
    target = "https://apollo.example.com"
    platform = "web"


class MockTestCase:
    id = 42
    title = "Customer Checkout Flow"
    steps = "1. Navigate to store\n2. Add item to cart\n3. Click checkout"
    expected_result = "Order confirmation page displayed"


class TestScriptGenerators(unittest.TestCase):
    def setUp(self):
        self.app = MockApplication()
        self.test_case = MockTestCase()
        self.sample_steps = [
            {"action": "navigate", "value": "https://apollo.example.com/checkout", "description": "Open checkout"},
            {"action": "type", "selector": "#email-input", "value": "qa@example.com", "description": "Enter email"},
            {"action": "click", "selector": "button#submit-order", "description": "Click submit"},
        ]
        self.sample_checks = [
            {"type": "visible", "value": ".confirmation-message", "description": "Verify confirmation"},
        ]

    def test_framework_registry_contains_all_six_frameworks(self):
        expected = {"playwright", "cypress", "selenium_python", "robot", "java_testng", "jest_puppeteer"}
        self.assertEqual(set(FRAMEWORK_REGISTRY.keys()), expected)

    def test_cypress_generator(self):
        gen = CypressGenerator()
        self.assertEqual(gen.framework_name(), "Cypress JavaScript")
        self.assertEqual(gen.language(), "javascript")
        self.assertEqual(gen.file_extension(), ".cy.js")

        output = gen.generate(self.test_case, self.app, self.sample_steps, self.sample_checks)
        self.assertIsInstance(output, ScriptOutput)
        self.assertTrue(output.filename.endswith(".cy.js"))
        self.assertEqual(output.framework, gen.framework_name())
        self.assertEqual(output.language, "javascript")
        self.assertIn("describe('Customer Checkout Flow'", output.code)
        self.assertIn("cy.visit(", output.code)
        self.assertIn("cy.get('#email-input').first().clear().type('qa@example.com')", output.code)
        self.assertIn("cy.get('button#submit-order').first().click()", output.code)
        self.assertIn(".should('be.visible')", output.code)

    def test_selenium_python_generator(self):
        gen = SeleniumPythonGenerator()
        self.assertEqual(gen.framework_name(), "Selenium Python")
        self.assertEqual(gen.language(), "python")
        self.assertEqual(gen.file_extension(), ".py")

        output = gen.generate(self.test_case, self.app, self.sample_steps, self.sample_checks)
        self.assertIsInstance(output, ScriptOutput)
        self.assertTrue(output.filename.startswith("test_"))
        self.assertTrue(output.filename.endswith(".py"))
        self.assertEqual(output.framework, gen.framework_name())
        self.assertEqual(output.language, "python")
        self.assertIn("import pytest", output.code)
        self.assertIn("from selenium import webdriver", output.code)
        self.assertIn("driver.get(", output.code)
        self.assertIn("element.send_keys(\"qa@example.com\")", output.code)
        self.assertIn("WebDriverWait", output.code)
        self.assertIn("driver.find_element(By.CSS_SELECTOR, \"button#submit-order\").click()", output.code)

    def test_robot_framework_generator(self):
        gen = RobotFrameworkGenerator()
        self.assertEqual(gen.framework_name(), "Robot Framework")
        self.assertEqual(gen.language(), "robotframework")
        self.assertEqual(gen.file_extension(), ".robot")

        output = gen.generate(self.test_case, self.app, self.sample_steps, self.sample_checks)
        self.assertIsInstance(output, ScriptOutput)
        self.assertTrue(output.filename.endswith(".robot"))
        self.assertEqual(output.framework, gen.framework_name())
        self.assertEqual(output.language, "robotframework")
        self.assertIn("*** Settings ***", output.code)
        self.assertIn("*** Test Cases ***", output.code)
        self.assertIn("Open Browser", output.code)
        self.assertIn("Input Text", output.code)
        self.assertIn("Click Element", output.code)
        self.assertIn("Wait Until Element Is Visible", output.code)

    def test_java_testng_generator(self):
        gen = JavaTestNGGenerator()
        self.assertEqual(gen.framework_name(), "Java TestNG + Selenium")
        self.assertEqual(gen.language(), "java")
        self.assertEqual(gen.file_extension(), ".java")

        output = gen.generate(self.test_case, self.app, self.sample_steps, self.sample_checks)
        self.assertIsInstance(output, ScriptOutput)
        self.assertTrue(output.filename.endswith("Test.java"))
        self.assertEqual(output.framework, gen.framework_name())
        self.assertEqual(output.language, "java")
        self.assertIn("import org.testng.annotations.*;", output.code)
        self.assertIn("public class", output.code)
        self.assertIn("@Test", output.code)
        self.assertIn("driver.get(", output.code)
        self.assertIn('driver.findElement(By.id("email-input")).sendKeys("qa@example.com");', output.code)

    def test_jest_puppeteer_generator(self):
        gen = JestPuppeteerGenerator()
        self.assertEqual(gen.framework_name(), "Jest + Puppeteer")
        self.assertEqual(gen.language(), "javascript")
        self.assertEqual(gen.file_extension(), ".test.js")

        output = gen.generate(self.test_case, self.app, self.sample_steps, self.sample_checks)
        self.assertIsInstance(output, ScriptOutput)
        self.assertTrue(output.filename.endswith(".test.js"))
        self.assertEqual(output.framework, gen.framework_name())
        self.assertEqual(output.language, "javascript")
        self.assertIn("describe('Customer Checkout Flow'", output.code)
        self.assertIn("await page.goto(", output.code)
        self.assertIn("await input_2.type('qa@example.com')", output.code)
        self.assertIn("await page.click('button#submit-order')", output.code)

    def test_generate_script_entrypoint(self):
        output = generate_script(
            framework="cypress",
            test_case=self.test_case,
            application=self.app,
            steps=self.sample_steps,
            checks=self.sample_checks,
        )
        self.assertEqual(output.framework, "Cypress JavaScript")
        self.assertTrue(output.filename.endswith(".cy.js"))

    def test_generate_script_unknown_framework_raises(self):
        with self.assertRaises(ValueError):
            generate_script(
                framework="unknown_framework_xyz",
                test_case=self.test_case,
                application=self.app,
                steps=[],
                checks=[],
            )


if __name__ == "__main__":
    unittest.main()
