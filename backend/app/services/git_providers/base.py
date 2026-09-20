"""Abstract base class for Git hosting provider integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GitFile:
    """A file to be committed to a Git repository."""

    path: str
    content: str


@dataclass(frozen=True)
class CommitResult:
    """Result of a successful commit operation."""

    sha: str
    url: str
    branch: str
    files_committed: int
    file_paths: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConnectionTestResult:
    """Result of a Git provider connectivity test."""

    success: bool
    message: str
    provider: str
    repo: str = ""
    default_branch: str = ""
    permissions: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class RepoSummary:
    """Summary of a repository accessible to the authenticated user."""

    full_name: str
    default_branch: str
    private: bool
    html_url: str
    description: str = ""


class GitProvider(ABC):
    """Abstract interface for Git hosting provider integrations."""

    @abstractmethod
    async def commit_files(
        self,
        repo: str,
        branch: str | None,
        files: list[GitFile],
        message: str,
    ) -> CommitResult:
        """Commit one or more files to a remote repository.

        If *branch* is ``None``, the provider should resolve to the repo's
        default branch using a smart branch selection strategy.
        """

    @abstractmethod
    async def verify_connection(self, repo: str | None = None) -> ConnectionTestResult:
        """Verify that the provider credentials are valid and can access
        the specified repository (or any repo if *repo* is None)."""

    @abstractmethod
    async def list_repos(self, page: int = 1, per_page: int = 30) -> list[RepoSummary]:
        """List repositories accessible to the authenticated user."""

    @abstractmethod
    async def resolve_branch(self, repo: str, requested_branch: str | None) -> str:
        """Smart branch resolution strategy.

        Implements the enhanced branch selection logic:
        1. If ``requested_branch`` is explicitly provided, use it.
        2. Otherwise, detect the repo's default branch via API.
        3. Apply organizational naming conventions when creating new branches.
        """
