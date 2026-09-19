from app.services.video_audio import build_execution_narration


def test_execution_narration_contains_only_numbered_steps() -> None:
    narration = build_execution_narration(
        "https://example.test",
        [
            "Application loaded: Dashboard",
            "Step 1: Navigating to https://example.test/login.",
            "Step 1 passed.",
            "Check visible passed.",
            "Step 2: Entering secure value into #password.",
            "Execution passed.",
        ],
        "passed",
    )

    assert narration.startswith("Step 1: Navigating to target URL Step 2:")
    assert "protected credential" in narration
    assert "Application loaded" not in narration
    assert "Check visible" not in narration
    assert "Execution passed" not in narration
