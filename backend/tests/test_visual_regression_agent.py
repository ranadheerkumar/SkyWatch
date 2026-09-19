"""Unit tests for SkyWatch Visual Regression Agent."""

import pytest
from app.agent.visual_regression_agent import (
    VisualRegressionAgent,
    _classify_diff,
    _compute_image_hash,
    _compute_html_structure_hash,
    _compute_pixel_diff,
)
from app.agent.types import VisualDiffCategory


def test_compute_image_hash_deterministic():
    data = b"sample image data for hashing"
    h1 = _compute_image_hash(data)
    h2 = _compute_image_hash(data)
    assert h1 == h2
    assert len(h1) == 16  # SHA-256 truncated to 16 chars


def test_compute_image_hash_different_inputs():
    h1 = _compute_image_hash(b"image_a")
    h2 = _compute_image_hash(b"image_b")
    assert h1 != h2


def test_compute_html_structure_hash():
    html1 = "<html><body><div><h1>Hello</h1></div></body></html>"
    html2 = "<html><body><div><h1>World</h1></div></body></html>"
    html3 = "<html><body><section><h2>Different</h2></section></body></html>"

    # Same structure, different content → same hash
    assert _compute_html_structure_hash(html1) == _compute_html_structure_hash(html2)
    # Different structure → different hash
    assert _compute_html_structure_hash(html1) != _compute_html_structure_hash(html3)


def test_classify_diff_identical():
    assert _classify_diff(0.0, 0) == VisualDiffCategory.IDENTICAL


def test_classify_diff_cosmetic():
    assert _classify_diff(0.3, 1) == VisualDiffCategory.COSMETIC


def test_classify_diff_layout_shift():
    assert _classify_diff(3.5, 4) == VisualDiffCategory.LAYOUT_SHIFT


def test_classify_diff_content_change():
    assert _classify_diff(10.0, 8) == VisualDiffCategory.CONTENT_CHANGE


def test_classify_diff_regression_break():
    assert _classify_diff(25.0, 15) == VisualDiffCategory.REGRESSION_BREAK


def test_pixel_diff_identical_bytes():
    data = b"\x89PNG\r\n\x1a\nsome bytes"
    pct, regions = _compute_pixel_diff(data, data)
    assert pct == 0.0
    assert regions == 0


def test_pixel_diff_different_bytes():
    data_a = b"different_data_a"
    data_b = b"different_data_b"
    pct, regions = _compute_pixel_diff(data_a, data_b)
    assert pct > 0


def test_synthetic_screenshot_deterministic():
    agent = VisualRegressionAgent()
    s1 = agent._generate_synthetic_screenshot("/login", 1920, 1080)
    s2 = agent._generate_synthetic_screenshot("/login", 1920, 1080)
    assert s1 == s2
    # Must be valid PNG
    assert s1[:8] == b"\x89PNG\r\n\x1a\n"


def test_synthetic_screenshot_different_routes():
    agent = VisualRegressionAgent()
    s1 = agent._generate_synthetic_screenshot("/login", 1920, 1080)
    s2 = agent._generate_synthetic_screenshot("/dashboard", 1920, 1080)
    assert s1 != s2


@pytest.mark.asyncio
async def test_visual_agent_baseline_capture(tmp_path):
    agent = VisualRegressionAgent(baselines_dir=str(tmp_path))
    screenshot = agent._generate_synthetic_screenshot("/home", 1920, 1080)
    snapshot = await agent.capture_baseline(
        app_id=1, route="/home", viewport_name="1920x1080",
        screenshot_bytes=screenshot, html_content="<html><body>Home</body></html>",
    )
    assert snapshot.app_id == 1
    assert snapshot.route == "/home"
    assert snapshot.viewport == "1920x1080"
    assert len(snapshot.image_hash) == 16


@pytest.mark.asyncio
async def test_visual_agent_compare_identical(tmp_path):
    agent = VisualRegressionAgent(baselines_dir=str(tmp_path))
    screenshot = agent._generate_synthetic_screenshot("/page", 1920, 1080)

    # First call creates baseline
    result1 = await agent.compare_against_baseline(1, "/page", "1920x1080", screenshot)
    assert result1.category == VisualDiffCategory.IDENTICAL

    # Second call compares against baseline — identical
    result2 = await agent.compare_against_baseline(1, "/page", "1920x1080", screenshot)
    assert result2.category == VisualDiffCategory.IDENTICAL
    assert result2.diff_percentage == 0.0


@pytest.mark.asyncio
async def test_visual_audit_multiple_pages(tmp_path):
    agent = VisualRegressionAgent(
        baselines_dir=str(tmp_path),
        viewports=[("desktop", 1920, 1080)],
    )
    pages = [
        {"url": "/login"},
        {"url": "/dashboard"},
        {"url": "/settings"},
    ]
    report = await agent.run_visual_audit(app_id=1, pages=pages)
    assert report.total_comparisons == 3
    assert report.app_id == 1
    assert report.duration_seconds >= 0
    # All should be identical on first run (baselines created)
    assert report.identical == 3


@pytest.mark.asyncio
async def test_visual_audit_report_serialization(tmp_path):
    agent = VisualRegressionAgent(
        baselines_dir=str(tmp_path),
        viewports=[("mobile", 375, 812)],
    )
    report = await agent.run_visual_audit(app_id=42, pages=[{"url": "/"}])
    report_dict = report.to_dict()
    assert report_dict["app_id"] == 42
    assert "results" in report_dict
    assert "total_comparisons" in report_dict
    assert "duration_seconds" in report_dict
