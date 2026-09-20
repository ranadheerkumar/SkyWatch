"""Unit tests for Git Provider abstraction and GitHub provider."""

import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

# Ensure backend root is in sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import types
if "app.services" not in sys.modules:
    dummy_services = types.ModuleType("app.services")
    dummy_services.__path__ = [os.path.join(BACKEND_DIR, "app", "services")]
    sys.modules["app.services"] = dummy_services

if "httpx" not in sys.modules:
    dummy_httpx = types.ModuleType("httpx")
    dummy_httpx.AsyncClient = type("AsyncClient", (), {})
    dummy_httpx.Response = type("Response", (), {})
    dummy_httpx.Timeout = type("Timeout", (), {"__init__": lambda self, *a, **kw: None})
    dummy_httpx.HTTPError = type("HTTPError", (Exception,), {})
    sys.modules["httpx"] = dummy_httpx

from app.services.git_providers.base import (
    CommitResult,
    ConnectionTestResult,
    GitFile,
    GitProvider,
    RepoSummary,
)
from app.services.git_providers.github_provider import GitHubProvider
from app.services.git_providers import GIT_PROVIDER_REGISTRY, get_git_provider


class TestGitProviderBase(unittest.TestCase):
    def test_git_file_dataclass(self):
        f = GitFile(path="tests/spec.ts", content="test code")
        self.assertEqual(f.path, "tests/spec.ts")
        self.assertEqual(f.content, "test code")

    def test_commit_result_dataclass(self):
        res = CommitResult(
            sha="abcdef1234567890",
            url="https://github.com/org/repo/commit/abcdef1",
            branch="main",
            files_committed=3,
            file_paths=["a.ts", "b.ts", "c.ts"],
        )
        self.assertEqual(res.sha, "abcdef1234567890")
        self.assertEqual(res.branch, "main")
        self.assertEqual(res.files_committed, 3)

    def test_registry_contains_github(self):
        self.assertIn("github", GIT_PROVIDER_REGISTRY)

    def test_get_git_provider_factory(self):
        provider = get_git_provider("github")
        self.assertIsInstance(provider, GitHubProvider)

    def test_get_git_provider_unknown_raises(self):
        with self.assertRaises(ValueError):
            get_git_provider("bitbucket_unsupported")


class TestGitHubProvider(unittest.TestCase):
    def setUp(self):
        self.provider = GitHubProvider()

    def test_resolve_repo_valid(self):
        repo = self.provider._resolve_repo("acme-corp/test-automation")
        self.assertEqual(repo, "acme-corp/test-automation")

    def test_resolve_repo_invalid_format_raises(self):
        with self.assertRaises(ValueError):
            self.provider._resolve_repo("invalid-repo-without-slash")

    def test_resolve_repo_empty_raises_when_no_default(self):
        with patch.object(self.provider, "_default_repo", ""):
            with self.assertRaises(ValueError):
                self.provider._resolve_repo("")

    def test_resolve_branch_explicit_overrides_all(self):
        import asyncio
        branch = asyncio.run(
            self.provider.resolve_branch("owner/repo", requested_branch="hotfix/patch")
        )
        self.assertEqual(branch, "hotfix/patch")

    def test_resolve_branch_uses_env_default(self):
        import asyncio
        with patch.object(self.provider, "_default_branch", "feature/tests"):
            branch = asyncio.run(
                self.provider.resolve_branch("owner/repo", requested_branch=None)
            )
            self.assertEqual(branch, "feature/tests")

    def test_resolve_branch_fallback(self):
        import asyncio
        with patch.object(self.provider, "_default_branch", None):
            branch = asyncio.run(
                self.provider.resolve_branch("owner/repo", requested_branch=None)
            )
            self.assertIn(branch, ["main", "master", "skywatch/generated-tests"])


if __name__ == "__main__":
    unittest.main()
