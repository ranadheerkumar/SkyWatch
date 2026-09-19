import io
import zipfile

import pytest

from app.services.document_analysis import (
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENT_CONTEXT_CHARS,
    MAX_UPLOAD_DOCUMENTS,
    DocumentAnalysisError,
    analyze_document,
    build_document_context,
    unpack_archive_documents,
)


def _docx_bytes(paragraphs: list[str]) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs)
    document = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
        f"<w:body>{body}</w:body></w:document>"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", document)
    return output.getvalue()


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return output.getvalue()


def test_analyze_document_extracts_docx_requirements_and_workflows() -> None:
    analysis = analyze_document(
        "requirements.docx",
        _docx_bytes([
            "# Checkout module",
            "The user must submit a valid order.",
            "When the user clicks Pay, the workflow should show confirmation.",
        ]),
    )

    assert analysis.extension == ".docx"
    assert analysis.pages_parsed == 1
    assert analysis.requirements_found == 2
    assert analysis.features_identified == 1
    assert analysis.modules_identified == ["Checkout module"]
    assert analysis.workflows_discovered == 3
    assert "submit a valid order" in analysis.text


def test_analyze_document_rejects_unsupported_and_oversized_files() -> None:
    with pytest.raises(DocumentAnalysisError, match="Unsupported document type"):
        analyze_document("requirements.exe", b"not a document")

    with pytest.raises(DocumentAnalysisError, match="document limit"):
        analyze_document("requirements.txt", b"x" * (MAX_DOCUMENT_BYTES + 1))


def test_analyze_document_reports_malformed_docx() -> None:
    with pytest.raises(DocumentAnalysisError, match="DOCX document could not be read"):
        analyze_document("requirements.docx", b"not a zip archive")


def test_build_document_context_is_bounded() -> None:
    analysis = analyze_document("requirements.txt", ("must validate checkout\n" * MAX_DOCUMENT_CONTEXT_CHARS).encode())

    context = build_document_context([analysis])

    assert len(context) == MAX_DOCUMENT_CONTEXT_CHARS
    assert context.startswith("DOCUMENT: requirements.txt")


def test_analyze_document_extracts_zip_archive_with_multiple_specs() -> None:
    zip_content = _zip_bytes({
        "auth_spec.md": b"# Authentication\nThe user must sign in with valid credentials.\nWhen login fails, show error message.",
        "orders_spec.txt": b"# Orders Module\nThe user must submit order details.\nClick checkout to confirm payment.",
    })

    analysis = analyze_document("specs_bundle.zip", zip_content)

    assert analysis.extension == ".zip"
    assert analysis.requirements_found >= 2
    assert "Authentication" in analysis.modules_identified or "Orders Module" in analysis.modules_identified
    assert "sign in with valid credentials" in analysis.text
    assert "submit order details" in analysis.text


def test_unpack_archive_documents_expands_inner_files() -> None:
    zip_content = _zip_bytes({
        "specs/checkout.md": b"# Checkout\nMust process payment.",
        "specs/billing.json": b'{"module": "billing", "rule": "user must provide billing address"}',
        "__MACOSX/._checkout.md": b"binary junk",
    })

    unpacked = unpack_archive_documents("archive.zip", zip_content)

    names = [name for name, _ in unpacked]
    assert "specs/checkout.md" in names
    assert "specs/billing.json" in names
    assert not any("__MACOSX" in name for name in names)
    assert len(unpacked) == 2


def test_analyze_document_reports_empty_or_corrupt_zip() -> None:
    empty_zip = _zip_bytes({})
    with pytest.raises(DocumentAnalysisError, match="contains no readable document files"):
        analyze_document("empty.zip", empty_zip)

    with pytest.raises(DocumentAnalysisError, match="corrupt or could not be read"):
        analyze_document("corrupted.zip", b"not a zip stream")


def test_max_upload_documents_constant_is_generous() -> None:
    assert MAX_UPLOAD_DOCUMENTS >= 30
