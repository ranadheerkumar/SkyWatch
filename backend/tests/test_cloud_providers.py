"""Unit tests for SkyWatch Cloud Abstraction Providers."""

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

if "app.services" not in sys.modules:
    dummy_services = types.ModuleType("app.services")
    dummy_services.__path__ = [os.path.join(BACKEND_DIR, "app", "services")]
    sys.modules["app.services"] = dummy_services

from app.services.cloud_providers import (
    LocalStorageProvider,
    LocalEnvSecretProvider,
    get_storage_provider,
    get_secret_provider,
)


class TestCloudProviders(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = LocalStorageProvider(base_dir=self.temp_dir.name)
        self.secrets = LocalEnvSecretProvider()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_local_storage_upload_download(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test artifact content")
            src_path = f.name

        try:
            url = self.storage.upload_file(src_path, "runs/123/screenshot.png")
            self.assertTrue(url.startswith("file://"))

            with tempfile.NamedTemporaryFile(delete=False) as dest:
                dest_path = dest.name

            success = self.storage.download_file("runs/123/screenshot.png", dest_path)
            self.assertTrue(success)
            self.assertEqual(Path(dest_path).read_text(), "test artifact content")

            files = self.storage.list_files("runs/123")
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0], "runs/123/screenshot.png")

            deleted = self.storage.delete_file("runs/123/screenshot.png")
            self.assertTrue(deleted)
            self.assertEqual(len(self.storage.list_files("runs/123")), 0)
        finally:
            if os.path.exists(src_path):
                os.unlink(src_path)

    def test_secret_provider(self) -> None:
        self.secrets.set_secret("TEST_SKYWATCH_SECRET", "super_secret_value")
        val = self.secrets.get_secret("TEST_SKYWATCH_SECRET")
        self.assertEqual(val, "super_secret_value")

        self.secrets.delete_secret("TEST_SKYWATCH_SECRET")
        self.assertIsNone(self.secrets.get_secret("TEST_SKYWATCH_SECRET"))

    def test_factory_defaults(self) -> None:
        storage = get_storage_provider("local")
        self.assertEqual(storage.provider_name, "local")

        secrets = get_secret_provider("local_env")
        self.assertEqual(secrets.provider_name, "local_env")


if __name__ == "__main__":
    unittest.main()
