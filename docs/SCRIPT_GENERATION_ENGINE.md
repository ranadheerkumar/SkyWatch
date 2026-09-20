# Enterprise Multi-Framework Script Generation Engine

SkyWatch 2.4+ includes a comprehensive, multi-framework test script generation engine that translates approved test cases and intermediate representation (IR) action steps into idiomatic, executable test automation code across six industry-standard test frameworks and languages.

---

## 1. Overview & Architecture

Previous versions of SkyWatch only supported TypeScript Playwright spec generation. The new Multi-Framework Engine decouples the step/check Intermediate Representation (IR) from framework-specific code emission using the **Strategy & Registry Pattern**.

```mermaid
graph TD
    TC[TestCase + Steps/Checks Text] --> IR[build_case_automation_from_text()]
    IR --> AST[Framework-Agnostic IR: Steps & Checks]
    AST --> Registry[FRAMEWORK_REGISTRY]
    Registry --> PW[PlaywrightGenerator (.spec.ts)]
    Registry --> CY[CypressGenerator (.cy.js)]
    Registry --> SP[SeleniumPythonGenerator (.py)]
    Registry --> RF[RobotFrameworkGenerator (.robot)]
    Registry --> JT[JavaTestNGGenerator (.java)]
    Registry --> JP[JestPuppeteerGenerator (.test.js)]
    PW --> API[Export API & ScriptStudio UI]
    CY --> API
    SP --> API
    RF --> API
    JT --> API
    JP --> API
```

### Core Components

1. **`ScriptGenerator` (Abstract Base Class)**: [`backend/app/services/script_generators/base.py`](file:///Users/rana/git_projects/SkyWatch/backend/app/services/script_generators/base.py)
   Defines the contract for code emission:
   - `generate(test_case, application, steps, checks) -> ScriptOutput`
   - `generate_code(test_case, application, steps, checks) -> str`
   - `file_extension() -> str`
   - `file_naming(test_case) -> str`
   - `framework_name() -> str`
   - `language() -> str`

2. **`ScriptOutput` Dataclass**:
   ```python
   @dataclass
   class ScriptOutput:
       code: str
       filename: str
       framework: str
       language: str
       file_extension: str
       test_case_id: int | None = None
       title: str | None = None
   ```

3. **Registry & Factory**: [`backend/app/services/script_generators/__init__.py`](file:///Users/rana/git_projects/SkyWatch/backend/app/services/script_generators/__init__.py)
   ```python
   from app.services.script_generators import generate_script, FRAMEWORK_REGISTRY

   output = generate_script("cypress", test_case, application, steps, checks)
   ```

---

## 2. Supported Frameworks & Language Matrix

| Framework ID | Framework Name | Language | File Extension | Test Runner | Key Features |
|:---|:---|:---|:---|:---|:---|
| `playwright` | Playwright TypeScript | TypeScript | `.spec.ts` | `@playwright/test` | Async/await, Auto-waiting locators, strict mode disambiguation |
| `cypress` | Cypress JavaScript | JavaScript | `.cy.js` | `cypress run` | Chained `cy.get().type()`, `cy.visit()`, `.should('be.visible')` |
| `selenium_python` | Selenium Python | Python | `.py` | `pytest` | Selenium 4, `WebDriverWait`, `By.*` locators, Chrome headless |
| `robot` | Robot Framework | Robot | `.robot` | `robot` | SeleniumLibrary, Keyword-driven syntax, `*** Settings/Test Cases ***` |
| `java_testng` | Java TestNG + Selenium | Java | `.java` | `mvn test` / TestNG | Java 17+, Selenium 4, `@Test/@BeforeMethod/@AfterMethod` |
| `jest_puppeteer` | Jest + Puppeteer | JavaScript | `.test.js` | `jest` | `puppeteer.launch()`, `page.goto()`, `expect()` matchers |

---

## 3. Step & Check IR Mapping

Every generator accepts the standardized intermediate representation produced by `build_case_automation_from_text()`:

### Action Step Mapping

| IR Action | Playwright | Cypress | Selenium Python | Robot Framework | Java TestNG | Jest Puppeteer |
|:---|:---|:---|:---|:---|:---|:---|
| `navigate` | `await page.goto(url)` | `cy.visit(url)` | `driver.get(url)` | `Go To  ${url}` | `driver.get(url)` | `await page.goto(url)` |
| `click` | `await page.click(sel)` | `cy.get(sel).first().click()` | `driver.find_element(...).click()` | `Click Element  ${sel}` | `driver.findElement(...).click()` | `await page.click(sel)` |
| `type` / `fill` | `await page.fill(sel, val)` | `cy.get(sel).first().clear().type(val)` | `el.clear(); el.send_keys(val)` | `Input Text  ${sel}  ${val}` | `el.clear(); el.sendKeys(val)` | `await el.click({3}); await el.type(val)` |
| `select` | `await page.selectOption(sel, val)` | `cy.get(sel).first().select(val)` | `Select(el).select_by_visible_text(val)` | `Select From List By Label  ${sel}  ${val}` | `new Select(el).selectByVisibleText(val)` | `await page.select(sel, val)` |
| `hover` | `await page.hover(sel)` | `cy.get(sel).first().trigger('mouseover')` | `ActionChains(driver).move_to_element(el).perform()` | `Mouse Over  ${sel}` | `new Actions(driver).moveToElement(el).perform()` | `await page.hover(sel)` |
| `press_key` | `await page.keyboard.press(key)` | `cy.get('body').type('{key}')` | `el.send_keys(Keys.KEY)` | `Press Keys  None  ${key}` | `el.sendKeys(Keys.KEY)` | `await page.keyboard.press(key)` |
| `wait` | `await page.waitForTimeout(ms)` | `cy.wait(ms)` | `time.sleep(sec)` | `Sleep  ${sec}s` | `Thread.sleep(ms)` | `await new Promise(r => setTimeout(r, ms))` |

### Assertion / Check Mapping

| IR Check Type | Playwright | Cypress | Selenium Python | Robot Framework | Java TestNG | Jest Puppeteer |
|:---|:---|:---|:---|:---|:---|:---|
| `visible` | `await expect(page.locator(sel)).toBeVisible()` | `cy.get(sel).first().should('be.visible')` | `wait.until(EC.visibility_of_element_located(...))` | `Wait Until Element Is Visible  ${sel}` | `wait.until(ExpectedConditions.visibilityOfElementLocated(...))` | `await page.waitForSelector(sel, {visible: true})` |
| `text_contains` | `await expect(page.locator('body')).toContainText(val)` | `cy.get('body').should('contain', val)` | `assert val in driver.page_source` | `Wait Until Page Contains  ${val}` | `Assert.assertTrue(driver.getPageSource().contains(val))` | `expect(bodyText).toContain(val)` |
| `title_contains` | `await expect(page).toHaveTitle(new RegExp(val))` | `cy.title().should('include', val)` | `assert val.lower() in driver.title.lower()` | `Title Should Contain  ${val}` | `Assert.assertTrue(driver.getTitle().contains(val))` | `expect(title.toLowerCase()).toContain(val)` |

---

## 4. API Endpoints Contract

### Export Single Script
`GET /api/v1/test-cases/{test_case_id}/export-script?framework={framework}`

**Query Parameters:**
- `framework` (string, optional, default: `"playwright"`): One of `playwright`, `cypress`, `selenium_python`, `robot`, `java_testng`, `jest_puppeteer`.

**Response (200 OK):**
```json
{
  "test_case_id": 42,
  "title": "Customer Checkout Flow",
  "filename": "customer_checkout_flow.cy.js",
  "code": "/// <reference types=\"cypress\" />\n\ndescribe('Customer Checkout Flow', () => { ... });\n",
  "framework": "Cypress JavaScript",
  "language": "javascript",
  "file_extension": ".cy.js"
}
```

### Export Application Suite
`GET /api/v1/test-cases/application/{application_id}/export-script-suite?framework={framework}`

**Response (200 OK):**
```json
{
  "application_id": 1,
  "application_name": "Apollo Retail",
  "framework": "selenium_python",
  "language": "python",
  "file_extension": ".py",
  "total_cases": 15,
  "scripts": [
    {
      "test_case_id": 42,
      "title": "Customer Checkout Flow",
      "filename": "test_customer_checkout_flow.py",
      "code": "import pytest\n...",
      "framework": "Selenium Python",
      "language": "python",
      "file_extension": ".py"
    }
  ]
}
```

### List Supported Frameworks
`GET /api/v1/integrations/git/supported-frameworks`

**Response (200 OK):**
```json
{
  "total": 6,
  "frameworks": [
    { "id": "playwright", "name": "Playwright", "language": "TypeScript", "file_extension": ".spec.ts" },
    { "id": "cypress", "name": "Cypress JavaScript", "language": "javascript", "file_extension": ".cy.js" },
    { "id": "selenium_python", "name": "Selenium Python", "language": "python", "file_extension": ".py" },
    { "id": "robot", "name": "Robot Framework", "language": "robotframework", "file_extension": ".robot" },
    { "id": "java_testng", "name": "Java TestNG + Selenium", "language": "java", "file_extension": ".java" },
    { "id": "jest_puppeteer", "name": "Jest + Puppeteer", "language": "javascript", "file_extension": ".test.js" }
  ]
}
```

---

## 5. Adding a New Framework

To add a 7th framework (e.g., `webdriverio`):

1. Create `backend/app/services/script_generators/webdriverio_gen.py`:
   ```python
   from .base import ScriptGenerator, ScriptOutput

   class WebDriverIOGenerator(ScriptGenerator):
       def framework_name(self) -> str:
           return "WebdriverIO"

       def language(self) -> str:
           return "TypeScript"

       def file_extension(self) -> str:
           return ".e2e.ts"

       def generate_code(self, test_case, application, steps, checks) -> str:
           ...
   ```
2. Register in `backend/app/services/script_generators/__init__.py`:
   ```python
   from .webdriverio_gen import WebDriverIOGenerator
   FRAMEWORK_REGISTRY["webdriverio"] = WebDriverIOGenerator
   ```
3. Frontend `ScriptStudio` will automatically discover the new framework via `/api/v1/integrations/git/supported-frameworks`.
