import asyncio
import pytest

from app.services.vector_service import (
    VectorStoreService,
    _deterministic_hash_embedding,
    generate_embeddings,
)
from app.services.document_analysis import (
    DocumentFileAnalysis,
    chunk_document_analyses,
)


@pytest.mark.anyio
async def test_deterministic_hash_embedding() -> None:
    vec1 = _deterministic_hash_embedding("Login to user account with valid credentials")
    vec2 = _deterministic_hash_embedding("Login to user account with valid credentials")
    vec3 = _deterministic_hash_embedding("Unrelated search for clinics and doctors")

    assert len(vec1) == 384
    assert vec1 == vec2
    assert vec1 != vec3


@pytest.mark.anyio
async def test_generate_embeddings_tier_fallback() -> None:
    texts = ["Checkout payment processing", "Search orders by customer"]
    embeddings = await generate_embeddings(texts)

    assert len(embeddings) == 2
    assert len(embeddings[0]) > 0
    assert len(embeddings[1]) > 0


def test_document_semantic_chunking() -> None:
    doc1 = DocumentFileAnalysis(
        filename="auth_spec.md",
        extension=".md",
        size_bytes=500,
        pages_parsed=1,
        requirements_found=3,
        features_identified=2,
        modules_identified=["Auth"],
        business_rules_found=1,
        workflows_discovered=2,
        extracted_characters=350,
        warnings=[],
        text="Section 1: Authentication Requirements\n\nUsers must login with email and password.\n\nSection 2: Password Complexity\n\nPasswords must be at least 8 characters long.",
    )

    chunks = chunk_document_analyses([doc1], chunk_size=100, chunk_overlap=20)
    assert len(chunks) >= 2
    assert chunks[0]["filename"] == "auth_spec.md"
    assert "Section 1" in chunks[0]["text"]


@pytest.mark.anyio
async def test_vector_store_document_indexing_and_query() -> None:
    vstore = VectorStoreService(application_id=999)

    chunks = [
        {"filename": "billing.md", "index": 0, "text": "Billing system processes credit cards, refunds, and subscriptions."},
        {"filename": "auth.md", "index": 0, "text": "Users authenticate using email and password with MFA verification."},
        {"filename": "pets.md", "index": 0, "text": "Find pets by microchip number, breed, color, and owner contact details."},
    ]

    indexed_count = await vstore.index_document_chunks(chunks)
    assert indexed_count == 3

    # Query for authentication
    auth_results = await vstore.query_relevant_document_chunks("How do users sign in or authenticate with password?", top_k=1)
    assert len(auth_results) == 1
    assert "authenticate" in auth_results[0].lower() or "password" in auth_results[0].lower()

    # Query for pet search
    pet_results = await vstore.query_relevant_document_chunks("Search pet by microchip", top_k=1)
    assert len(pet_results) == 1
    assert "microchip" in pet_results[0].lower() or "pets" in pet_results[0].lower()


@pytest.mark.anyio
async def test_vector_store_test_case_deduplication() -> None:
    vstore = VectorStoreService(application_id=999)

    # Index existing test case
    await vstore.index_test_case(
        case_id=101,
        title="TC01 - User Login with Valid Credentials",
        steps="1. Open /login\n2. Enter email\n3. Enter password\n4. Click Submit",
        expected_result="Dashboard opens successfully",
        description="Verify successful authentication flow",
    )

    # Search with very similar scenario
    similar = await vstore.find_duplicate_or_similar_cases(
        title="User Login with Valid Email and Password",
        steps="1. Navigate to login page\n2. Type email and password\n3. Click Login",
        top_k=2,
    )

    assert len(similar) >= 1
    assert str(similar[0]["case_id"]) == "101"
    assert similar[0]["similarity_score"] > 0.5


@pytest.mark.anyio
async def test_vector_store_healing_memory() -> None:
    vstore = VectorStoreService(application_id=999)

    # Store successful repair
    success = await vstore.index_healing_repair(
        run_id="run-123456",
        step_index=3,
        action="click",
        failed_selector="button.old-submit-btn",
        healed_selector="button[type='submit']:has-text('Save')",
        failure_message="Locator timed out waiting for element",
        reason="Updated button class in new release",
    )
    assert success is True

    # Query healing memory for similar failure
    memories = await vstore.query_healing_memory(
        action="click",
        failed_selector="button.old-submit-btn",
        failure_message="Timeout waiting for button",
        top_k=1,
    )

    assert len(memories) >= 1
    assert memories[0]["healed_selector"] == "button[type='submit']:has-text('Save')"
