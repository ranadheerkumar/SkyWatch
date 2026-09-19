import re
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from pathlib import Path


class AgentDefinitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentDefinition:
    key: str
    title: str
    file_name: str
    version: str
    checksum_sha256: str
    content: str


AGENT_FILE_MAP: dict[str, str] = {
    "document_analysis": "document-analysis.agent.md",
    "discovery": "application-discovery.agent.md",
    "context_builder": "context-builder.agent.md",
    "planner": "playwright-test-planner.agent.md",
    "scenario": "test-scenario.agent.md",
    "generator": "playwright-test-generator.agent.md",
    "test_data": "test-data-generator.agent.md",
    "authoring": "low-code-authoring.agent.md",
    "selection": "test-selection.agent.md",
    "deduplication": "test-deduplication.agent.md",
    "validator": "test-case-validator.agent.md",
    "repository": "repository.agent.md",
    "healer": "playwright-test-healer.agent.md",
    "execution": "execution-agent.agent.md",
    "failure_analysis": "failure-analysis.agent.md",
    "maintenance": "test-maintenance.agent.md",
    "reporting": "reporting.agent.md",
}

def _resolve_agents_directory() -> Path:
    source_path = Path(__file__).resolve()
    candidates = (
        source_path.parents[3] / ".github" / "agents",
        source_path.parents[2] / ".github" / "agents",
    )
    return next((candidate for candidate in candidates if candidate.is_dir()), candidates[0])


AGENTS_DIRECTORY = _resolve_agents_directory()


def _extract_frontmatter_value(content: str, key: str) -> str:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for raw_line in lines[1:]:
        line = raw_line.strip()
        if line == "---":
            break
        if ":" not in line:
            continue
        left, right = line.split(":", 1)
        if left.strip().casefold() == key.casefold():
            return right.strip().strip("\"'")[:220]
    return ""


def _strip_frontmatter(content: str) -> str:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return content
    for index, raw_line in enumerate(lines[1:], start=1):
        if raw_line.strip() == "---":
            return "\n".join(lines[index + 1 :]).strip()
    return content


def _extract_title(content: str) -> str:
    frontmatter_name = _extract_frontmatter_value(content, "name")
    if frontmatter_name:
        return frontmatter_name
    frontmatter_description = _extract_frontmatter_value(content, "description")
    if frontmatter_description:
        return frontmatter_description
    for raw_line in _strip_frontmatter(content).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            return re.sub(r"^#+\s*", "", line).strip()[:140] or "Untitled Agent"
    return "Untitled Agent"


def _extract_guidance_lines(content: str, *, max_lines: int = 12) -> list[str]:
    body = _strip_frontmatter(content)
    real_app_guidance: list[str] = []
    in_real_app_section = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            heading = re.sub(r"^#+\s*", "", line).strip().casefold()
            if in_real_app_section:
                break
            in_real_app_section = heading.startswith("real-application")
            continue
        if not in_real_app_section:
            continue
        normalized = re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip()
        if not normalized:
            continue
        real_app_guidance.append(normalized[:220])
        if len(real_app_guidance) >= max_lines:
            return real_app_guidance
    if real_app_guidance:
        return real_app_guidance

    guidance: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("```") or line == "---":
            continue
        normalized = re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip()
        if not normalized:
            continue
        lowered = normalized.casefold()
        if lowered.startswith(("name:", "description:", "tools:", "model:", "mcp-servers:", "args:", "command:", "type:")):
            continue
        if "<example" in lowered or "</example" in lowered:
            continue
        if " tool" in lowered and ("playwright" in lowered or "`" in normalized):
            continue
        if any(
            token in lowered
            for token in {
                "generator_setup_page",
                "generator_read_log",
                "generator_write_test",
                "planner_setup_page",
                "planner_save_plan",
                "browser_",
                "test_run",
                "test_debug",
                "mcp-server",
                "invoke the",
            }
        ):
            continue
        if "`" in normalized and "_" in normalized:
            continue
        if not re.search(r"[a-zA-Z]{3,}", normalized):
            continue
        guidance.append(normalized[:220])
        if len(guidance) >= max_lines:
            break
    return guidance


@lru_cache(maxsize=len(AGENT_FILE_MAP))
def load_agent_definition(agent_key: str) -> AgentDefinition:
    normalized_key = (agent_key or "").strip().lower()
    file_name = AGENT_FILE_MAP.get(normalized_key)
    if not file_name:
        raise AgentDefinitionError(
            f"Unknown agent '{agent_key}'. Expected one of: {', '.join(sorted(AGENT_FILE_MAP))}."
        )

    file_path = AGENTS_DIRECTORY / file_name
    if not file_path.is_file():
        raise AgentDefinitionError(
            f"Required agent definition file is missing: {file_path}"
        )

    content = file_path.read_text(encoding="utf-8").strip()
    if not content:
        raise AgentDefinitionError(
            f"Agent definition file is empty: {file_path}"
        )

    checksum = sha256(content.encode("utf-8")).hexdigest()
    return AgentDefinition(
        key=normalized_key,
        title=_extract_title(content),
        file_name=file_name,
        version=checksum[:12],
        checksum_sha256=checksum,
        content=content,
    )


def get_agent_trace_metadata(agent_keys: list[str]) -> list[dict[str, str]]:
    metadata: list[dict[str, str]] = []
    for key in agent_keys:
        definition = load_agent_definition(key)
        metadata.append(
            {
                "key": definition.key,
                "title": definition.title,
                "file_name": definition.file_name,
                "version": definition.version,
                "checksum_sha256": definition.checksum_sha256,
            }
        )
    return metadata


def build_agent_guidance_block(agent_keys: list[str]) -> str:
    sections: list[str] = []
    for key in agent_keys:
        definition = load_agent_definition(key)
        guidance_lines = _extract_guidance_lines(definition.content)
        if not guidance_lines:
            continue
        bullet_lines = "\n".join(f"- {line}" for line in guidance_lines)
        sections.append(
            f"{definition.title} (version {definition.version}):\n{bullet_lines}"
        )
    if not sections:
        return ""
    return "Agent workflow guidance:\n" + "\n\n".join(sections)
