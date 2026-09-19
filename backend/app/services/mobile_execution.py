import os
from pathlib import Path

from app.schemas.execution import MobileExecutionRequest, Step


class MobileRunnerNotConfigured(RuntimeError):
	pass


def _resolve_secret(step: Step) -> str:
	if step.secret_name:
		value = os.getenv(step.secret_name)
		if value is None:
			raise MobileRunnerNotConfigured(f"Secret {step.secret_name} is not configured")
		return value
	return step.value or ""


def validate_mobile_request(request: MobileExecutionRequest) -> None:
	artifact = Path(request.artifact_path)
	if request.platform == "android" and artifact.suffix.lower() != ".apk":
		raise ValueError("Android execution requires an .apk artifact")
	if request.platform == "ios" and artifact.suffix.lower() != ".ipa":
		raise ValueError("iOS execution requires an .ipa artifact")
	if not artifact.is_file():
		raise FileNotFoundError(f"Mobile artifact does not exist: {artifact}")
	if request.platform == "ios" and not request.appium_url:
		raise MobileRunnerNotConfigured("iOS requires an Appium/XCUITest provider URL")
	if request.platform == "android" and not request.appium_url:
		raise MobileRunnerNotConfigured("Android requires an Appium provider URL")
	for step in request.steps:
		if step.action == "type":
			_resolve_secret(step)


async def execute_mobile_target(request: MobileExecutionRequest) -> dict[str, str]:
	validate_mobile_request(request)
	try:
		from appium import webdriver
		from appium.options.android import UiAutomator2Options
		from appium.options.ios import XCUITestOptions
	except ImportError as error:
		raise MobileRunnerNotConfigured("Install appium-python-client to enable mobile execution") from error

	options = UiAutomator2Options() if request.platform == "android" else XCUITestOptions()
	options.set_capability("platformName", "Android" if request.platform == "android" else "iOS")
	options.set_capability("deviceName", request.device_name)
	options.set_capability("app", request.artifact_path)
	driver = webdriver.Remote(str(request.appium_url), options=options)
	try:
		for step in request.steps:
			if step.action == "click" and step.selector:
				driver.find_element("xpath", step.selector).click()
			elif step.action == "type" and step.selector:
				driver.find_element("xpath", step.selector).send_keys(_resolve_secret(step))
		return {"status": "passed", "platform": request.platform, "device_name": request.device_name}
	finally:
		driver.quit()