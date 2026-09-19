"""File analysis tools wrapping the existing document_analysis service.

Provides tools for parsing and extracting structured information from
uploaded documents (PDF, DOCX, XLSX, CSV, JSON, etc.).
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.tool_base import AgentTool, ToolParameter, ToolSchema
from app.agent.types import ToolCategory

logger = logging.getLogger("ai-qa-engine.agent.tools.file")


class AnalyzeDocumentTool(AgentTool):
    """Analyze an uploaded document to extract requirements, features, and business rules."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="analyze_document",
            description=(
                "Analyze an uploaded document file to extract requirements, features, "
                "business rules, workflows, and modules. Supports PDF, DOCX, XLSX, CSV, "
                "JSON, TXT, Markdown, XML, YAML, and ZIP files. Returns structured "
                "extraction metrics and the full extracted text."
            ),
            category=ToolCategory.FILE,
            parameters=[
                ToolParameter(
                    name="file_path",
                    description="Absolute path to the uploaded file on disk.",
                    type="string",
                ),
                ToolParameter(
                    name="filename",
                    description="Original filename (used for extension detection).",
                    type="string",
                ),
            ],
        )

    async def _execute(self, file_path: str, filename: str, **_: Any) -> dict[str, Any]:
        from pathlib import Path
        from app.services.document_analysis import analyze_document_file

        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        content = path.read_bytes()
        result = analyze_document_file(content, filename)
        return {
            **result.response_dict(),
            "text": result.text[:50_000],  # Cap text for LLM context
        }


class ReadFileContentTool(AgentTool):
    """Read raw text content from a file."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="read_file",
            description=(
                "Read the raw text content of a file. Returns the first 50,000 characters. "
                "Use for plain text, Markdown, JSON, YAML, CSV, or code files."
            ),
            category=ToolCategory.FILE,
            parameters=[
                ToolParameter(
                    name="file_path",
                    description="Absolute path to the file.",
                    type="string",
                ),
                ToolParameter(
                    name="max_chars",
                    description="Maximum characters to return (default 50000).",
                    type="integer",
                    required=False,
                    default=50_000,
                ),
            ],
        )

    async def _execute(self, file_path: str, max_chars: int = 50_000, **_: Any) -> dict[str, Any]:
        from pathlib import Path

        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        text = path.read_text(encoding="utf-8", errors="replace")
        return {
            "file_path": file_path,
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "total_chars": len(text),
            "content": text[:max_chars],
            "truncated": len(text) > max_chars,
        }


def create_file_tools() -> list[AgentTool]:
    """Factory to create all file analysis tool instances."""
    return [
        AnalyzeDocumentTool(),
        ReadFileContentTool(),
    ]
