# AI Requirement Document Workflow

The AI Generator accepts bounded requirement context alongside its existing prompt. Document analysis happens before durable test-case generation and returns metrics that let a reviewer verify what the parser found before sending the context to an AI provider.

## Supported Inputs

| Extension | Extraction path | Page count |
| --- | --- | ---: |
| `.pdf` | `pypdf` text extraction | PDF page count |
| `.docx` | Standard-library ZIP/XML extraction | 1 |
| `.txt`, `.md`, `.markdown` | UTF-8 text decoding | 1 |
| `.csv`, `.tsv` | UTF-8 CSV/TSV row extraction | 1 |
| `.xlsx` | Standard-library ZIP/XML extraction of worksheet values | 1 |
| `.json`, `.yaml`, `.yml` | UTF-8 structured data parse and normalized serialization | 1 |
| `.zip` | Archive extraction of inner supported documents with metadata | Sum of inner files |

DOCX and XLSX parsing deliberately avoids a second document-library dependency. PDF parsing requires the pinned `pypdf` package in `backend/requirements.txt`. ZIP archives are automatically unpacked and parsed.

## Limits and Failure Behavior

- Up to 30 files or ZIP archives are accepted in one request.
- Each file is read up to 10 MB plus one byte so oversized input can be rejected before downstream work.
- Extracted text is capped at 60,000 characters per file and again at 60,000 characters for the combined provider context.
- Unsupported extensions, malformed archives, invalid JSON, and invalid CSV encoding return a bounded HTTP 400 error naming the affected file.
- Extraction warnings, such as a PDF page that could not be read or text that was capped, are returned as metadata and shown in the generator UI.
- Uploaded bytes are analyzed in memory and are not persisted as document records by this workflow.

## Analysis Metrics

The response includes file-level and aggregate values for:

- Files uploaded and pages parsed.
- Requirement signals and features identified.
- Modules identified from headings and module/feature labels.
- Business-rule signals.
- Workflow signals.
- Extracted character count and parser warnings.

The signal counters are intentionally heuristic. They are useful for review and context sizing, not a substitute for a formal requirements parser or human approval.

## API

```text
POST /api/v1/ai-generation/documents/analyze
Authorization: Bearer <session token>
Content-Type: multipart/form-data
files=<one or more supported files>
```

The response's `context_text` is sent as `document_context` when the user starts a generation job:

```text
POST /api/v1/ai-generation/jobs?application_id=<id>
{
  "prompt": "...",
  "document_context": "DOCUMENT: requirements.md\n...",
  "document_names": ["requirements.md"]
}
```

Prompt-only generation remains supported when `document_context` is absent.

## Validation

Focused parser coverage is in [backend/tests/test_document_analysis.py](../backend/tests/test_document_analysis.py). It covers DOCX extraction, unsupported and oversized files, malformed DOCX input, and the combined context cap. The API contract suite remains the right place for authenticated endpoint and ownership checks.

## Follow-up Hardening

The current implementation should be extended before enterprise rollout with malware scanning, content-type and archive-bomb defenses, encrypted object storage when retention is required, per-user upload quotas, asynchronous document processing for large files, OCR for scanned PDFs, structured requirement IDs, and requirement-to-test traceability.
