"""Git provider abstraction layer.

Provides a registry of Git hosting providers with a common interface for
committing generated test scripts to remote repositories.
"""

from __future__ import annotations

from .base import GitFile, GitProvider, CommitResult, ConnectionTestResult, RepoSummary
from .github_provider import GitHubProvider


GIT_PROVIDER_REGISTRY: dict[str, type[GitProvider]] = {
    "github": GitHubProvider,
}


def get_git_provider(system: str = "github") -> GitProvider:
    """Instantiate a GitProvider by system name."""
    cls = GIT_PROVIDER_REGISTRY.get(system.lower().strip())
    if cls is None:
        raise ValueError(
            f"Unsupported git provider '{system}'. "
            f"Supported: {', '.join(GIT_PROVIDER_REGISTRY.keys())}"
        )
    return cls()


__all__ = [
    "CommitResult",
    "ConnectionTestResult",
    "GIT_PROVIDER_REGISTRY",
    "GitFile",
    "GitProvider",
    "RepoSummary",
    "get_git_provider",
]
