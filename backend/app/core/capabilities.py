"""SkyWatch Enterprise Platform Capabilities Registry.

Codifies the platform capability taxonomy as defined in Section 6 of the Master Architecture.
Decouples testing intent, requirements, and agent planning from specific libraries or vendors.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("skywatch.core.capabilities")


class PlatformCapability(str, Enum):
    """Canonical enterprise testing and quality capabilities."""
    UI_BROWSER_AUTOMATION = "UI_BROWSER_AUTOMATION"
    API_AUTOMATION = "API_AUTOMATION"
    MOBILE_AUTOMATION = "MOBILE_AUTOMATION"
    DATABASE_VALIDATION = "DATABASE_VALIDATION"
    PERFORMANCE_TESTING = "PERFORMANCE_TESTING"
    ACCESSIBILITY_TESTING = "ACCESSIBILITY_TESTING"
    SECURITY_TESTING = "SECURITY_TESTING"
    VISUAL_TESTING = "VISUAL_TESTING"
    TEST_DATA_GENERATION = "TEST_DATA_GENERATION"
    REQUIREMENT_ANALYSIS = "REQUIREMENT_ANALYSIS"
    TEST_GENERATION = "TEST_GENERATION"
    TEST_EXECUTION = "TEST_EXECUTION"
    FAILURE_ANALYSIS = "FAILURE_ANALYSIS"
    REPORTING = "REPORTING"
    DEFECT_CREATION = "DEFECT_CREATION"
    SOURCE_CONTROL = "SOURCE_CONTROL"
    CI_CD = "CI_CD"
    CLOUD_STORAGE = "CLOUD_STORAGE"
    SECRET_MANAGEMENT = "SECRET_MANAGEMENT"


class CapabilityCategory(str, Enum):
    """Categorical taxonomy for platform capabilities."""
    DESIGN = "design"
    EXECUTION = "execution"
    ANALYSIS = "analysis"
    GOVERNANCE = "governance"
    INFRASTRUCTURE = "infrastructure"


@dataclass
class CapabilityDescriptor:
    """Detailed metadata descriptor for a registered platform capability."""
    capability: PlatformCapability
    name: str
    category: CapabilityCategory
    description: str
    supported_environments: list[str] = field(default_factory=lambda: ["web", "api", "mobile", "cloud"])
    is_available: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["capability"] = self.capability.value
        data["category"] = self.category.value
        return data


class CapabilityRegistry:
    """Central registry of all discoverable platform capabilities."""

    def __init__(self) -> None:
        self._capabilities: dict[PlatformCapability, CapabilityDescriptor] = {}
        self._initialize_default_capabilities()

    def register(self, descriptor: CapabilityDescriptor) -> None:
        """Register or update a platform capability descriptor."""
        self._capabilities[descriptor.capability] = descriptor
        logger.debug("Registered platform capability: %s (%s)", descriptor.capability.value, descriptor.category.value)

    def get(self, capability: PlatformCapability | str) -> CapabilityDescriptor | None:
        """Retrieve a capability descriptor by enum or string key."""
        if isinstance(capability, str):
            try:
                cap_enum = PlatformCapability(capability)
            except ValueError:
                return None
        else:
            cap_enum = capability
        return self._capabilities.get(cap_enum)

    def is_available(self, capability: PlatformCapability | str) -> bool:
        """Check if a capability is currently registered and available."""
        descriptor = self.get(capability)
        return descriptor.is_available if descriptor else False

    def list_capabilities(
        self,
        category: CapabilityCategory | None = None,
        available_only: bool = False,
    ) -> list[CapabilityDescriptor]:
        """List registered capabilities, optionally filtered by category and availability."""
        caps = list(self._capabilities.values())
        if category is not None:
            caps = [c for c in caps if c.category == category]
        if available_only:
            caps = [c for c in caps if c.is_available]
        return sorted(caps, key=lambda c: c.capability.value)

    def to_dict(self, available_only: bool = False) -> list[dict[str, Any]]:
        """Export capabilities as serialized dictionaries."""
        return [cap.to_dict() for cap in self.list_capabilities(available_only=available_only)]

    def _initialize_default_capabilities(self) -> None:
        """Populate the registry with SkyWatch canonical capabilities."""
        defaults = [
            CapabilityDescriptor(
                capability=PlatformCapability.UI_BROWSER_AUTOMATION,
                name="UI Browser Automation",
                category=CapabilityCategory.EXECUTION,
                description="Cross-browser automated test execution via Playwright, Selenium, and Cypress engines.",
                supported_environments=["web", "cloud"],
                is_available=True,
                metadata={"engines": ["playwright", "selenium", "cypress", "robot", "jest_puppeteer"]},
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.API_AUTOMATION,
                name="API & Microservices Automation",
                category=CapabilityCategory.EXECUTION,
                description="Automated contract verification, schema conformance, and negative payload testing for REST/GraphQL APIs.",
                supported_environments=["api", "cloud"],
                is_available=True,
                metadata={"protocols": ["http", "https", "rest", "graphql", "openapi"]},
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.MOBILE_AUTOMATION,
                name="Mobile App Automation",
                category=CapabilityCategory.EXECUTION,
                description="Cross-platform native, hybrid, and mobile web test execution across iOS, Android, and iPad devices.",
                supported_environments=["mobile", "cloud"],
                is_available=True,
                metadata={"frameworks": ["appium", "xcuitest", "espresso"]},
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.DATABASE_VALIDATION,
                name="Database & State Validation",
                category=CapabilityCategory.EXECUTION,
                description="Automated SQL query assertions, transactional consistency validation, and database state verification.",
                supported_environments=["database", "cloud", "on_prem"],
                is_available=True,
                metadata={"types": ["sql", "nosql"]},
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.PERFORMANCE_TESTING,
                name="Performance & Latency Profiling",
                category=CapabilityCategory.EXECUTION,
                description="HTTP benchmark response timing, throughput analysis, and SLA latency threshold enforcement.",
                supported_environments=["web", "api", "cloud"],
                is_available=True,
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.ACCESSIBILITY_TESTING,
                name="Accessibility Scanning",
                category=CapabilityCategory.EXECUTION,
                description="Automated WCAG 2.1 / 2.2 AA and Section 508 contrast, ARIA, and screen-reader audit checks.",
                supported_environments=["web", "mobile"],
                is_available=True,
                metadata={"standards": ["wcag21aa", "wcag22aa", "section508"]},
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.SECURITY_TESTING,
                name="Security & Vulnerability Testing",
                category=CapabilityCategory.EXECUTION,
                description="Automated OWASP Top 10 boundary injection, header posture verification, and token leakage analysis.",
                supported_environments=["web", "api", "cloud"],
                is_available=True,
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.VISUAL_TESTING,
                name="Visual Regression & Pixel Diffing",
                category=CapabilityCategory.EXECUTION,
                description="Multi-viewport screenshot baseline comparisons, DOM tree hashing, and pixel perceptual diff classification.",
                supported_environments=["web", "mobile"],
                is_available=True,
                metadata={"viewports": ["desktop", "tablet", "mobile"]},
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.TEST_DATA_GENERATION,
                name="Smart Test Data Generation",
                category=CapabilityCategory.DESIGN,
                description="AI-driven and rule-based synthesis of type-safe valid, invalid, boundary, and edge test datasets.",
                supported_environments=["web", "api", "mobile", "database"],
                is_available=True,
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.REQUIREMENT_ANALYSIS,
                name="Requirement & Specification Analysis",
                category=CapabilityCategory.DESIGN,
                description="Ingestion and structural parsing of user stories, PRDs, Word/PDF documents, Excel sheets, and OpenAPI schemas.",
                supported_environments=["all"],
                is_available=True,
                metadata={"formats": ["pdf", "docx", "xlsx", "csv", "json", "yaml", "md"]},
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.TEST_GENERATION,
                name="AI Test Case Design & Synthesis",
                category=CapabilityCategory.DESIGN,
                description="Context-anchored generation of comprehensive positive, negative, boundary, security, and accessibility test scenarios.",
                supported_environments=["all"],
                is_available=True,
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.TEST_EXECUTION,
                name="Distributed Test Execution",
                category=CapabilityCategory.EXECUTION,
                description="Parallel worker execution queue with isolated browser contexts, dynamic rate limiting, and cancellation support.",
                supported_environments=["all"],
                is_available=True,
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.FAILURE_ANALYSIS,
                name="Root Cause Failure Analysis & Triage",
                category=CapabilityCategory.ANALYSIS,
                description="Multi-modal evidence diagnosis (DOM, console, network, screenshots, traces) distinguishing app vs. test defects.",
                supported_environments=["all"],
                is_available=True,
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.REPORTING,
                name="Quality Intelligence & Reporting",
                category=CapabilityCategory.GOVERNANCE,
                description="Allure 2 execution reports, release quality scorecards, flakiness tracking, and executive analytics dashboards.",
                supported_environments=["all"],
                is_available=True,
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.DEFECT_CREATION,
                name="ALM Defect Synchronization",
                category=CapabilityCategory.GOVERNANCE,
                description="Bi-directional defect creation, status synchronization, and test cycle linking with Jira, qTest, and external trackers.",
                supported_environments=["all"],
                is_available=True,
                metadata={"adapters": ["jira", "qtest"]},
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.SOURCE_CONTROL,
                name="Source Control & Git Provider Integration",
                category=CapabilityCategory.INFRASTRUCTURE,
                description="Remote branch auto-resolution, change traceability, single-file commits, and atomic multi-file test suite pushes.",
                supported_environments=["all"],
                is_available=True,
                metadata={"providers": ["github", "gitlab", "azure_repos", "bitbucket"]},
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.CI_CD,
                name="CI/CD Orchestration & Webhooks",
                category=CapabilityCategory.INFRASTRUCTURE,
                description="Automated execution triggers via webhooks, GitHub Actions, Jenkins, Azure DevOps, and GitLab CI/CD pipelines.",
                supported_environments=["all"],
                is_available=True,
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.CLOUD_STORAGE,
                name="Cloud & Object Storage",
                category=CapabilityCategory.INFRASTRUCTURE,
                description="Multi-cloud artifact storage for traces, videos, logs, and screenshots across Azure Blob, GCS, AWS S3, and Local Disk.",
                supported_environments=["all"],
                is_available=True,
                metadata={"adapters": ["local", "azure_blob", "gcp_storage", "aws_s3"]},
            ),
            CapabilityDescriptor(
                capability=PlatformCapability.SECRET_MANAGEMENT,
                name="Secret & Credential Management",
                category=CapabilityCategory.INFRASTRUCTURE,
                description="Role-scoped secret resolution across Azure Key Vault, GCP Secret Manager, AWS Secrets Manager, and local environments.",
                supported_environments=["all"],
                is_available=True,
                metadata={"adapters": ["local_env", "azure_keyvault", "gcp_secrets", "aws_secrets"]},
            ),
        ]
        for cap in defaults:
            self.register(cap)


# Global singleton capability registry instance
default_capability_registry = CapabilityRegistry()
