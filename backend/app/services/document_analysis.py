import csv
import io
import json
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


SUPPORTED_DOCUMENT_EXTENSIONS = frozenset({
    ".pdf", ".docx", ".txt", ".csv", ".xlsx", ".json", ".md", ".markdown", ".zip",
    ".yaml", ".yml", ".xml", ".html", ".htm", ".log", ".rst", ".tsv",
})


def _load_document_analysis_limits() -> tuple[int, int, int]:
    try:
        max_docs = max(1, int(os.getenv("AI_MAX_UPLOAD_DOCUMENTS", os.getenv("AI_QA_ENGINE_MAX_UPLOAD_DOCUMENTS", "50"))))
    except ValueError:
        max_docs = 50
    try:
        max_bytes = max(1024 * 1024, int(os.getenv("AI_MAX_DOCUMENT_BYTES", os.getenv("AI_QA_ENGINE_MAX_DOCUMENT_BYTES", str(30 * 1024 * 1024)))))
    except ValueError:
        max_bytes = 30 * 1024 * 1024
    try:
        max_chars = max(10_000, int(os.getenv("AI_MAX_DOCUMENT_CONTEXT_CHARS", os.getenv("AI_QA_ENGINE_MAX_DOCUMENT_CONTEXT_CHARS", "250000"))))
    except ValueError:
        max_chars = 250_000
    return max_docs, max_bytes, max_chars


MAX_UPLOAD_DOCUMENTS, MAX_DOCUMENT_BYTES, MAX_DOCUMENT_CONTEXT_CHARS = _load_document_analysis_limits()


class DocumentAnalysisError(ValueError):
    pass


@dataclass(frozen=True)
class DocumentFileAnalysis:
    filename: str
    extension: str
    size_bytes: int
    pages_parsed: int
    requirements_found: int
    features_identified: int
    modules_identified: list[str]
    business_rules_found: int
    workflows_discovered: int
    extracted_characters: int
    warnings: list[str]
    text: str

    def response_dict(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "pages_parsed": self.pages_parsed,
            "requirements_found": self.requirements_found,
            "features_identified": self.features_identified,
            "modules_identified": self.modules_identified,
            "business_rules_found": self.business_rules_found,
            "workflows_discovered": self.workflows_discovered,
            "extracted_characters": self.extracted_characters,
            "warnings": self.warnings,
        }


def _extract_docx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            document_xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as error:
        raise DocumentAnalysisError("The DOCX document could not be read.") from error

    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError as error:
        raise DocumentAnalysisError("The DOCX document contains invalid XML.") from error

    paragraphs: list[str] = []
    for paragraph in root.findall(".//{*}p"):
        text = "".join(node.text or "" for node in paragraph.findall(".//{*}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def _extract_xlsx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in names:
                shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                shared_strings = ["".join(node.itertext()) for node in shared_root.findall("{*}si")]
            rows: list[str] = []
            for sheet_name in sorted(name for name in names if name.startswith("xl/worksheets/") and name.endswith(".xml")):
                root = ElementTree.fromstring(archive.read(sheet_name))
                for row in root.findall(".//{*}sheetData/{*}row"):
                    values: list[str] = []
                    for cell in row.findall("{*}c"):
                        value = cell.find("{*}v")
                        text = "" if value is None else value.text or ""
                        if cell.attrib.get("t") == "s" and text:
                            try:
                                text = shared_strings[int(text)]
                            except (IndexError, ValueError):
                                text = ""
                        elif cell.attrib.get("t") == "inlineStr":
                            inline = cell.find("{*}is")
                            text = "".join(inline.itertext()) if inline is not None else ""
                        if text.strip():
                            values.append(text.strip())
                    if values:
                        rows.append(" | ".join(values))
            return "\n".join(rows)
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as error:
        raise DocumentAnalysisError("The XLSX document could not be read.") from error


def _extract_pdf_text(content: bytes) -> tuple[str, int, list[str]]:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise DocumentAnalysisError("PDF analysis requires the pypdf dependency.") from error

    try:
        reader = PdfReader(io.BytesIO(content))
        pages: list[str] = []
        warnings: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                pages.append(page.extract_text() or "")
            except Exception as error:
                warnings.append(f"Page {index} could not be extracted: {type(error).__name__}.")
        return "\n\n".join(page.strip() for page in pages if page.strip()), len(reader.pages), warnings
    except Exception as error:
        raise DocumentAnalysisError(f"The PDF document could not be read: {type(error).__name__}.") from error


def _extract_zip_text(content: bytes) -> tuple[str, int, list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = [
                info for info in archive.infolist()
                if not info.is_dir()
                and not Path(info.filename).name.startswith((".", "~$", "__MACOSX"))
                and not any(part.startswith((".", "__MACOSX")) for part in Path(info.filename).parts)
            ]
            if not entries:
                raise DocumentAnalysisError("The ZIP archive contains no readable document files.")

            combined_blocks: list[str] = []
            total_pages = 0
            warnings: list[str] = []

            for entry in entries[:50]:
                entry_name = entry.filename
                safe_name = Path(entry_name).name
                entry_ext = Path(safe_name).suffix.lower()
                if entry_ext in {".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".exe", ".bin", ".pyc", ".dll", ".so", ".class"}:
                    continue
                try:
                    entry_bytes = archive.read(entry_name)
                    if not entry_bytes:
                        continue
                    if len(entry_bytes) > MAX_DOCUMENT_BYTES:
                        warnings.append(f"{entry_name}: exceeds the {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB limit and was skipped.")
                        continue
                    if entry_ext in SUPPORTED_DOCUMENT_EXTENSIONS and entry_ext != ".zip":
                        text, pages, inner_warnings = _extract_text(safe_name, entry_bytes)
                    else:
                        try:
                            text = entry_bytes.decode("utf-8-sig", errors="replace")
                            pages = 1
                            inner_warnings = []
                        except Exception:
                            continue
                    if text.strip():
                        combined_blocks.append(f"=== Document: {entry_name} ===\n{text.strip()}")
                        total_pages += pages
                    warnings.extend(f"{entry_name}: {w}" for w in inner_warnings)
                except Exception as err:
                    warnings.append(f"{entry_name}: could not be extracted ({type(err).__name__}).")

            if not combined_blocks:
                raise DocumentAnalysisError("The ZIP archive contains no supported requirement document files.")

            return "\n\n".join(combined_blocks), max(1, total_pages), warnings
    except zipfile.BadZipFile as error:
        raise DocumentAnalysisError("The ZIP archive is corrupt or could not be read.") from error


def unpack_archive_documents(filename: str, content: bytes) -> list[tuple[str, bytes]]:
    """If filename is a .zip archive, extracts its inner supported documents as (inner_filename, inner_bytes) pairs."""
    extension = Path(filename).suffix.lower()
    if extension != ".zip":
        return [(filename, content)]
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = [
                info for info in archive.infolist()
                if not info.is_dir()
                and not Path(info.filename).name.startswith((".", "~$", "__MACOSX"))
                and not any(part.startswith((".", "__MACOSX")) for part in Path(info.filename).parts)
            ]
            extracted: list[tuple[str, bytes]] = []
            for entry in entries[:50]:
                inner_ext = Path(entry.filename).suffix.lower()
                if inner_ext in {".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".exe", ".bin", ".pyc", ".dll", ".so", ".class"}:
                    continue
                if inner_ext in SUPPORTED_DOCUMENT_EXTENSIONS or inner_ext in {".yaml", ".yml", ".xml", ".html", ".htm", ".log", ".rst", ".tsv", ".spec"}:
                    try:
                        data = archive.read(entry.filename)
                        if data and len(data) <= MAX_DOCUMENT_BYTES:
                            extracted.append((entry.filename, data))
                    except Exception:
                        continue
            if extracted:
                return extracted
    except Exception:
        pass
    return [(filename, content)]


def _extract_text(filename: str, content: bytes) -> tuple[str, int, list[str]]:
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        return _extract_pdf_text(content)
    if extension == ".docx":
        return _extract_docx_text(content), 1, []
    if extension == ".zip":
        return _extract_zip_text(content)
    if extension in {".xlsx"}:
        return _extract_xlsx_text(content), 1, []
    if extension == ".csv":
        try:
            rows = csv.reader(io.StringIO(content.decode("utf-8-sig")))
            return "\n".join(" | ".join(value.strip() for value in row if value.strip()) for row in rows), 1, []
        except UnicodeDecodeError as error:
            raise DocumentAnalysisError("The CSV document must be UTF-8 encoded.") from error
    if extension == ".json":
        try:
            value = json.loads(content.decode("utf-8-sig"))
            return json.dumps(value, indent=2, ensure_ascii=True), 1, []
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DocumentAnalysisError("The JSON document is invalid or not UTF-8 encoded.") from error
    try:
        return content.decode("utf-8-sig", errors="replace"), 1, []
    except UnicodeDecodeError as error:
        raise DocumentAnalysisError("The document text could not be decoded.") from error


def _unique(values: list[str], limit: int = 60) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = re.sub(r"\s+", " ", value).strip(" -:#*\t`\"'")
        if len(normalized) < 2:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized[:120])
        if len(result) >= limit:
            break
    return result


def _analyze_text(text: str) -> tuple[int, int, list[str], int, int]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    requirement_lines = [
        line for line in lines
        if re.search(r"\b(requirement|req|user story|acceptance criteria|shall|must|required|should|given|when|then|as a|i want|so that|validate|verify|ensure|test case|scenario|rule)\b", line, re.IGNORECASE)
    ]
    feature_lines = [
        line for line in lines
        if re.search(r"\b(feature|capability|screen|page|component|function|module|endpoint|service|form|dialog|table|modal|view|api|controller|flow)\b", line, re.IGNORECASE)
    ]
    module_candidates: list[str] = []
    for line in lines:
        heading = re.sub(r"^#+\s*", "", line).strip()
        match = re.match(r"(?:module|area|feature|component|screen|page|epic|service|controller|section|topic)\s*[:\-]\s*(.+)", heading, re.IGNORECASE)
        if match:
            module_candidates.append(match.group(1))
        elif line.startswith(("#", "===")):
            module_candidates.append(heading)
        elif re.match(r"^(?:GET|POST|PUT|DELETE|PATCH)\s+(/\S+)", line, re.IGNORECASE):
            module_candidates.append(line)
        elif re.match(r"^\*\*(.+?)\*\*$", line):
            bold_m = re.match(r"^\*\*(.+?)\*\*$", line)
            if bold_m and len(bold_m.group(1)) < 60:
                module_candidates.append(bold_m.group(1))
    business_rule_lines = [
        line for line in lines
        if re.search(r"\b(must|shall|required|only|unless|cannot|not allowed|if|when|mandatory|forbidden|unique|default|range|limit|timeout|prerequisite|condition)\b", line, re.IGNORECASE)
    ]
    workflow_lines = [
        line for line in lines
        if re.search(r"\b(navigate|login|sign in|click|select|submit|create|search|filter|checkout|workflow|open|save|update|delete|enter|fill|assert|check|upload|download|view|inspect|test|execute)\b", line, re.IGNORECASE)
    ]
    return max(len(requirement_lines), 1 if lines else 0), len(feature_lines), _unique(module_candidates), len(business_rule_lines), len(workflow_lines)


def analyze_document(filename: str, content: bytes) -> DocumentFileAnalysis:
    safe_filename = Path(filename or "").name
    extension = Path(safe_filename).suffix.lower()
    if not safe_filename or extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))
        raise DocumentAnalysisError(f"Unsupported document type. Supported extensions: {supported}.")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise DocumentAnalysisError(f"{safe_filename} exceeds the {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB document limit.")

    text, pages_parsed, warnings = _extract_text(safe_filename, content)
    bounded_text = text[:MAX_DOCUMENT_CONTEXT_CHARS]
    if len(text) > MAX_DOCUMENT_CONTEXT_CHARS:
        warnings = [*warnings, f"Extracted text was capped at {MAX_DOCUMENT_CONTEXT_CHARS:,} characters."]
    requirements, features, modules, rules, workflows = _analyze_text(bounded_text)
    return DocumentFileAnalysis(
        filename=safe_filename,
        extension=extension,
        size_bytes=len(content),
        pages_parsed=pages_parsed,
        requirements_found=requirements,
        features_identified=features,
        modules_identified=modules,
        business_rules_found=rules,
        workflows_discovered=workflows,
        extracted_characters=len(bounded_text),
        warnings=warnings,
        text=bounded_text,
    )


def build_document_context(analyses: list[DocumentFileAnalysis]) -> str:
    if not analyses:
        return ""
    non_empty = [a for a in analyses if a.text.strip()]
    if not non_empty:
        return ""

    total_chars = sum(len(a.text) for a in non_empty)
    if total_chars <= MAX_DOCUMENT_CONTEXT_CHARS:
        blocks = [f"DOCUMENT: {analysis.filename}\n{analysis.text}" for analysis in non_empty]
        return "\n\n".join(blocks)[:MAX_DOCUMENT_CONTEXT_CHARS]

    per_doc_budget = max(2000, MAX_DOCUMENT_CONTEXT_CHARS // len(non_empty))
    blocks = []
    for analysis in non_empty:
        snippet = analysis.text[:per_doc_budget].strip()
        blocks.append(f"DOCUMENT: {analysis.filename}\n{snippet}")
    return "\n\n".join(blocks)[:MAX_DOCUMENT_CONTEXT_CHARS]


def chunk_document_analyses(
    analyses: list[DocumentFileAnalysis],
    *,
    chunk_size: int = 900,
    chunk_overlap: int = 150,
) -> list[dict[str, Any]]:
    """Splits analyzed documents into overlapping semantic chunks ready for vector embeddings."""
    all_chunks: list[dict[str, Any]] = []
    for analysis in analyses:
        text = analysis.text.strip()
        if not text:
            continue
        paragraphs = re.split(r"\n\s*\n", text)
        current_chunk_parts: list[str] = []
        current_len = 0
        doc_chunk_idx = 0

        for p in paragraphs:
            p_clean = p.strip()
            if not p_clean:
                continue
            if current_len + len(p_clean) > chunk_size and current_chunk_parts:
                combined_text = "\n\n".join(current_chunk_parts)
                all_chunks.append({
                    "filename": analysis.filename,
                    "index": doc_chunk_idx,
                    "text": combined_text,
                })
                doc_chunk_idx += 1
                # Overlap: keep the last paragraph
                current_chunk_parts = current_chunk_parts[-1:]
                current_len = sum(len(x) for x in current_chunk_parts)

            current_chunk_parts.append(p_clean)
            current_len += len(p_clean)

        if current_chunk_parts:
            combined_text = "\n\n".join(current_chunk_parts)
            all_chunks.append({
                "filename": analysis.filename,
                "index": doc_chunk_idx,
                "text": combined_text,
            })

    return all_chunks
