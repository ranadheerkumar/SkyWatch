"""GitHub REST API Git provider.

Implements the ``GitProvider`` interface using GitHub's REST API v3:
- **Single file commits**: ``PUT /repos/{owner}/{repo}/contents/{path}``
- **Atomic multi-file commits**: Git Trees API (``POST /repos/{owner}/{repo}/git/trees``
  → ``POST /repos/{owner}/{repo}/git/commits`` → ``PATCH /repos/{owner}/{repo}/git/refs/{ref}``)
- **Smart branch resolution**: Detects the repo's default branch, falls back to
  ``skywatch/generated-tests``, and auto-creates branches when needed.

Environment variables:
    ``GITHUB_GIT_TOKEN``   — Personal access token (classic) or fine-grained PAT with ``contents: write``
    ``GITHUB_GIT_REPO``    — Default ``owner/repo`` (e.g. ``acme-corp/web-tests``)
    ``GITHUB_GIT_BRANCH``  — Default target branch (optional; smart detection used otherwise)
    ``GITHUB_GIT_BASE_PATH`` — Directory prefix for committed files (default: ``tests/skywatch/``)
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import httpx

from .base import (
    CommitResult,
    ConnectionTestResult,
    GitFile,
    GitProvider,
    RepoSummary,
)

logger = logging.getLogger("skywatch.git.github")

_API_BASE = "https://api.github.com"
_DEFAULT_BRANCH_NAME = "skywatch/generated-tests"
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class GitHubProvider(GitProvider):
    """GitHub REST API v3 provider for committing generated test scripts."""

    def __init__(self) -> None:
        self._token = (
            os.getenv("GITHUB_GIT_TOKEN")
            or os.getenv("SKYWATCH_GIT_TOKEN", "")
        ).strip()
        self._default_repo = (
            os.getenv("GITHUB_GIT_REPO")
            or os.getenv("SKYWATCH_GIT_REPO", "")
        ).strip()
        self._default_branch = (
            os.getenv("GITHUB_GIT_BRANCH")
            or os.getenv("SKYWATCH_GIT_BRANCH", "")
        ).strip() or None
        self._base_path = (
            os.getenv("GITHUB_GIT_BASE_PATH")
            or os.getenv("SKYWATCH_GIT_BASE_PATH", "tests/skywatch/")
        ).strip().rstrip("/")

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SkyWatch-Git-Provider/2.0",
        }

    def _resolve_repo(self, repo: str | None) -> str:
        r = (repo or self._default_repo).strip()
        if not r:
            raise ValueError(
                "No GitHub repository specified. "
                "Set GITHUB_GIT_REPO or pass `repo` explicitly."
            )
        if "/" not in r:
            raise ValueError(
                f"Invalid GitHub repo format '{r}'. "
                "Expected 'owner/repo' (e.g. 'acme-corp/web-tests')."
            )
        return r

    # ------------------------------------------------------------------
    # Smart Branch Resolution
    # ------------------------------------------------------------------

    async def resolve_branch(self, repo: str, requested_branch: str | None) -> str:
        """Enhanced branch selection strategy.

        Priority order:
        1. Explicitly requested branch (from API call or UI selection).
        2. Environment-configured default branch (GITHUB_GIT_BRANCH).
        3. Auto-detect the repo's default branch via GitHub API.
        4. Fall back to ``skywatch/generated-tests``.
        """
        # 1. Explicitly requested
        if requested_branch:
            return requested_branch.strip()

        # 2. Environment default
        if self._default_branch:
            return self._default_branch

        # 3. Auto-detect from repo
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"{_API_BASE}/repos/{repo}",
                    headers=self._headers,
                )
                if resp.status_code == 200:
                    default = resp.json().get("default_branch", "main")
                    logger.info(
                        "Resolved default branch for %s: %s", repo, default
                    )
                    return default
        except Exception as exc:
            logger.warning("Failed to detect default branch for %s: %s", repo, exc)

        # 4. Fallback
        return _DEFAULT_BRANCH_NAME

    async def _ensure_branch_exists(
        self,
        client: httpx.AsyncClient,
        repo: str,
        branch: str,
    ) -> str:
        """Ensure the target branch exists. If not, create it from the repo's default branch."""
        # Check if branch exists
        resp = await client.get(
            f"{_API_BASE}/repos/{repo}/git/refs/heads/{branch}",
            headers=self._headers,
        )
        if resp.status_code == 200:
            return resp.json()["object"]["sha"]

        # Branch doesn't exist — create from default branch
        logger.info("Branch '%s' not found in %s, creating it...", branch, repo)
        repo_resp = await client.get(
            f"{_API_BASE}/repos/{repo}",
            headers=self._headers,
        )
        if repo_resp.status_code != 200:
            raise RuntimeError(f"Cannot access repo {repo}: {repo_resp.status_code}")

        default_branch = repo_resp.json().get("default_branch", "main")

        # Get SHA of default branch
        ref_resp = await client.get(
            f"{_API_BASE}/repos/{repo}/git/refs/heads/{default_branch}",
            headers=self._headers,
        )
        if ref_resp.status_code != 200:
            raise RuntimeError(
                f"Cannot find default branch '{default_branch}' in {repo}"
            )
        base_sha = ref_resp.json()["object"]["sha"]

        # Create the new branch
        create_resp = await client.post(
            f"{_API_BASE}/repos/{repo}/git/refs",
            headers=self._headers,
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )
        if create_resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Failed to create branch '{branch}': {create_resp.status_code} {create_resp.text}"
            )
        logger.info("Created branch '%s' from '%s' in %s", branch, default_branch, repo)
        return base_sha

    # ------------------------------------------------------------------
    # Commit Operations
    # ------------------------------------------------------------------

    async def commit_files(
        self,
        repo: str | None = None,
        branch: str | None = None,
        files: list[GitFile] | None = None,
        message: str = "SkyWatch: Add generated test scripts",
    ) -> CommitResult:
        """Commit files to GitHub.

        For a single file, uses the Contents API.
        For multiple files, uses the Git Trees API for an atomic commit.
        """
        repo = self._resolve_repo(repo)
        files = files or []
        if not files:
            raise ValueError("No files to commit")

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resolved_branch = await self.resolve_branch(repo, branch)
            await self._ensure_branch_exists(client, repo, resolved_branch)

            if len(files) == 1:
                return await self._commit_single_file(
                    client, repo, resolved_branch, files[0], message
                )
            return await self._commit_multiple_files(
                client, repo, resolved_branch, files, message
            )

    async def _commit_single_file(
        self,
        client: httpx.AsyncClient,
        repo: str,
        branch: str,
        git_file: GitFile,
        message: str,
    ) -> CommitResult:
        """Commit a single file via the Contents API."""
        file_path = f"{self._base_path}/{git_file.path}".lstrip("/")
        encoded_content = base64.b64encode(git_file.content.encode("utf-8")).decode("ascii")

        # Check if file exists (to get SHA for update)
        existing_sha: str | None = None
        check_resp = await client.get(
            f"{_API_BASE}/repos/{repo}/contents/{file_path}",
            headers=self._headers,
            params={"ref": branch},
        )
        if check_resp.status_code == 200:
            existing_sha = check_resp.json().get("sha")

        payload: dict[str, Any] = {
            "message": message,
            "content": encoded_content,
            "branch": branch,
        }
        if existing_sha:
            payload["sha"] = existing_sha

        resp = await client.put(
            f"{_API_BASE}/repos/{repo}/contents/{file_path}",
            headers=self._headers,
            json=payload,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"GitHub Contents API error: {resp.status_code} {resp.text}"
            )

        data = resp.json()
        commit_sha = data.get("commit", {}).get("sha", "")
        commit_url = data.get("commit", {}).get("html_url", "")

        logger.info(
            "Committed %s to %s@%s (SHA: %s)",
            file_path, repo, branch, commit_sha[:8],
        )
        return CommitResult(
            sha=commit_sha,
            url=commit_url,
            branch=branch,
            files_committed=1,
            file_paths=[file_path],
        )

    async def _commit_multiple_files(
        self,
        client: httpx.AsyncClient,
        repo: str,
        branch: str,
        files: list[GitFile],
        message: str,
    ) -> CommitResult:
        """Commit multiple files atomically via the Git Trees API."""
        # 1. Get current branch HEAD SHA
        ref_resp = await client.get(
            f"{_API_BASE}/repos/{repo}/git/refs/heads/{branch}",
            headers=self._headers,
        )
        if ref_resp.status_code != 200:
            raise RuntimeError(
                f"Cannot get ref for branch '{branch}': {ref_resp.status_code}"
            )
        head_sha = ref_resp.json()["object"]["sha"]

        # 2. Get the current commit to find the base tree
        commit_resp = await client.get(
            f"{_API_BASE}/repos/{repo}/git/commits/{head_sha}",
            headers=self._headers,
        )
        if commit_resp.status_code != 200:
            raise RuntimeError(
                f"Cannot get commit {head_sha}: {commit_resp.status_code}"
            )
        base_tree_sha = commit_resp.json()["tree"]["sha"]

        # 3. Create blobs for each file
        tree_items: list[dict[str, str]] = []
        committed_paths: list[str] = []
        for gf in files:
            file_path = f"{self._base_path}/{gf.path}".lstrip("/")
            encoded = base64.b64encode(gf.content.encode("utf-8")).decode("ascii")

            blob_resp = await client.post(
                f"{_API_BASE}/repos/{repo}/git/blobs",
                headers=self._headers,
                json={"content": encoded, "encoding": "base64"},
            )
            if blob_resp.status_code != 201:
                raise RuntimeError(
                    f"Failed to create blob for {file_path}: {blob_resp.status_code}"
                )
            blob_sha = blob_resp.json()["sha"]
            tree_items.append({
                "path": file_path,
                "mode": "100644",
                "type": "blob",
                "sha": blob_sha,
            })
            committed_paths.append(file_path)

        # 4. Create a new tree
        tree_resp = await client.post(
            f"{_API_BASE}/repos/{repo}/git/trees",
            headers=self._headers,
            json={"base_tree": base_tree_sha, "tree": tree_items},
        )
        if tree_resp.status_code != 201:
            raise RuntimeError(
                f"Failed to create tree: {tree_resp.status_code} {tree_resp.text}"
            )
        new_tree_sha = tree_resp.json()["sha"]

        # 5. Create a new commit
        new_commit_resp = await client.post(
            f"{_API_BASE}/repos/{repo}/git/commits",
            headers=self._headers,
            json={
                "message": message,
                "tree": new_tree_sha,
                "parents": [head_sha],
            },
        )
        if new_commit_resp.status_code != 201:
            raise RuntimeError(
                f"Failed to create commit: {new_commit_resp.status_code}"
            )
        new_commit_sha = new_commit_resp.json()["sha"]
        commit_html_url = new_commit_resp.json().get("html_url", f"https://github.com/{repo}/commit/{new_commit_sha}")

        # 6. Update the branch reference
        update_ref_resp = await client.patch(
            f"{_API_BASE}/repos/{repo}/git/refs/heads/{branch}",
            headers=self._headers,
            json={"sha": new_commit_sha},
        )
        if update_ref_resp.status_code != 200:
            raise RuntimeError(
                f"Failed to update ref: {update_ref_resp.status_code}"
            )

        logger.info(
            "Atomic commit of %d files to %s@%s (SHA: %s)",
            len(files), repo, branch, new_commit_sha[:8],
        )
        return CommitResult(
            sha=new_commit_sha,
            url=commit_html_url,
            branch=branch,
            files_committed=len(files),
            file_paths=committed_paths,
        )

    # ------------------------------------------------------------------
    # Connection & Repository Discovery
    # ------------------------------------------------------------------

    async def verify_connection(self, repo: str | None = None) -> ConnectionTestResult:
        """Verify GitHub token validity and repository access."""
        if not self._token:
            return ConnectionTestResult(
                success=False,
                message="GITHUB_GIT_TOKEN is not configured. Set it in Settings or environment.",
                provider="github",
            )

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                # Verify token
                user_resp = await client.get(
                    f"{_API_BASE}/user",
                    headers=self._headers,
                )
                if user_resp.status_code != 200:
                    return ConnectionTestResult(
                        success=False,
                        message=f"GitHub authentication failed (HTTP {user_resp.status_code}). Verify your token.",
                        provider="github",
                    )

                username = user_resp.json().get("login", "")

                # If repo specified, check access
                resolved_repo = repo or self._default_repo
                if resolved_repo:
                    repo_resp = await client.get(
                        f"{_API_BASE}/repos/{resolved_repo}",
                        headers=self._headers,
                    )
                    if repo_resp.status_code != 200:
                        return ConnectionTestResult(
                            success=False,
                            message=f"Cannot access repository '{resolved_repo}' (HTTP {repo_resp.status_code}).",
                            provider="github",
                            repo=resolved_repo,
                        )
                    repo_data = repo_resp.json()
                    permissions = repo_data.get("permissions", {})
                    default_branch = repo_data.get("default_branch", "main")

                    if not permissions.get("push", False):
                        return ConnectionTestResult(
                            success=False,
                            message=f"Token for '{username}' lacks push access to '{resolved_repo}'.",
                            provider="github",
                            repo=resolved_repo,
                            default_branch=default_branch,
                            permissions=permissions,
                        )

                    return ConnectionTestResult(
                        success=True,
                        message=f"Connected as '{username}' with push access to '{resolved_repo}'.",
                        provider="github",
                        repo=resolved_repo,
                        default_branch=default_branch,
                        permissions=permissions,
                    )

                return ConnectionTestResult(
                    success=True,
                    message=f"Authenticated as '{username}'. No default repository configured.",
                    provider="github",
                )

        except httpx.ConnectError:
            return ConnectionTestResult(
                success=False,
                message="Cannot reach GitHub API. Check network connectivity.",
                provider="github",
            )
        except Exception as exc:
            return ConnectionTestResult(
                success=False,
                message=f"Unexpected error: {exc}",
                provider="github",
            )

    async def list_repos(self, page: int = 1, per_page: int = 30) -> list[RepoSummary]:
        """List repositories accessible to the authenticated user."""
        if not self._token:
            return []

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_API_BASE}/user/repos",
                headers=self._headers,
                params={
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": min(per_page, 100),
                    "page": page,
                    "type": "all",
                },
            )
            if resp.status_code != 200:
                logger.warning("Failed to list repos: %s", resp.status_code)
                return []

            repos: list[RepoSummary] = []
            for r in resp.json():
                repos.append(
                    RepoSummary(
                        full_name=r.get("full_name", ""),
                        default_branch=r.get("default_branch", "main"),
                        private=r.get("private", False),
                        html_url=r.get("html_url", ""),
                        description=r.get("description") or "",
                    )
                )
            return repos
