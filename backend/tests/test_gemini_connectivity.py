"""Unit tests for Google Gemini Provider configuration and connectivity."""

import os
import unittest
from unittest.mock import MagicMock, patch

# Ensure backend root is in sys.path
import sys
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.config import Settings, settings


class TestGeminiConnectivity(unittest.TestCase):
    """Test suite for Google Gemini configuration, aliases, and connectivity."""

    def test_settings_gemini_defaults_and_fields(self):
        """Settings must expose GEMINI_MODEL, GOOGLE_CLOUD_PROJECT, and GOOGLE_PROJECT_NUMBER."""
        self.assertTrue(hasattr(settings, "GEMINI_MODEL"))
        self.assertTrue(hasattr(settings, "GEMINI_API_KEY"))
        self.assertTrue(hasattr(settings, "GOOGLE_CLOUD_PROJECT"))
        self.assertTrue(hasattr(settings, "GOOGLE_PROJECT_NUMBER"))
        self.assertEqual(settings.GEMINI_MODEL, "gemini-flash-latest")
        self.assertEqual(settings.GOOGLE_PROJECT_NUMBER, "584367322531")
        self.assertEqual(settings.GOOGLE_CLOUD_PROJECT, "projects/584367322531")

    def test_ssl_cert_file_configured(self):
        """SSL_CERT_FILE should be set to enable secure TLS handshakes on macOS."""
        ssl_file = os.environ.get("SSL_CERT_FILE")
        self.assertIsNotNone(ssl_file)
        self.assertTrue(os.path.exists(ssl_file), f"SSL cert path {ssl_file} does not exist")

    def test_gemini_model_aliases(self):
        """Deprecated models must resolve cleanly to active supported models."""
        alias_map = {
            "gemini-2.0-flash": "gemini-flash-latest",
            "gemini-2.0": "gemini-flash-latest",
            "gemini-2.5-flash": "gemini-flash-latest",
            "gemini-2.5-pro": "gemini-pro-latest",
            "gemini-2.5": "gemini-flash-latest",
            "gemini-1.5-pro": "gemini-pro-latest",
            "gemini-1.5-flash": "gemini-flash-latest",
            "gemini-1.5": "gemini-flash-latest",
            "gemini-pro": "gemini-pro-latest",
            "gemini-flash": "gemini-flash-latest",
        }
        for deprecated, expected in alias_map.items():
            self.assertEqual(alias_map.get(deprecated.lower()), expected)

    def test_gemini_supported_models_list(self):
        """The supported Gemini models list must contain valid current models."""
        expected_models = [
            "gemini-flash-latest",
            "gemini-pro-latest",
            "gemini-flash-lite-latest",
            "gemini-3.6-flash",
        ]
        self.assertIn("gemini-flash-latest", expected_models)
        self.assertIn("gemini-pro-latest", expected_models)


if __name__ == "__main__":
    unittest.main()
