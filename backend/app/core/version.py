import json
from pathlib import Path


_VERSION_FALLBACK = "0.0.0-unknown"


def get_application_version() -> str:
    source_path = Path(__file__).resolve()
    candidates = (
        source_path.parents[3] / "frontend" / "package.json",
        source_path.parents[2] / "frontend-package.json",
    )
    for candidate in candidates:
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            continue
        version = payload.get("version") if isinstance(payload, dict) else None
        if isinstance(version, str) and version.strip():
            return version.strip()
    return _VERSION_FALLBACK
