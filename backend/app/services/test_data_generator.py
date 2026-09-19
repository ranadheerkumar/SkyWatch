"""Smart Test Data Generator Service for AI QA Engine.

Synthesizes realistic, type-safe, and privacy-compliant test datasets covering:
1. Valid scenarios (realistic business records, formatted identifiers).
2. Invalid scenarios (malformed inputs, schema violations, type mismatches).
3. Boundary value scenarios (min/max length, zeroes, date limits, edge values).
4. Edge/Security scenarios (special characters, whitespace padding, unicode, script escaping).
5. Self-learning adaptation (incorporates live harvested application entities).
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Any

from app.schemas.test_data import TestDatasetCreate
from app.services.ai_service import _load_provider_settings, _request_provider_json, AIServiceError
from app.services.self_learning import SelfLearningEngine

logger = logging.getLogger("ai-qa-engine.test_data_generator")


# Default generic seed datasets for standard entity types
DEFAULT_ENTITIES = {
    "first_name": ["John", "Jane", "Robert", "Emily", "Michael", "Sarah", "David", "Jessica", "James", "Amanda"],
    "last_name": ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Franklin"],
    "city": ["Springfield", "Austin", "Seattle", "Denver", "Boston", "San Jose", "Chicago", "Atlanta"],
    "state": ["CA", "TX", "WA", "NY", "IL", "FL", "CO", "MA"],
    "zip_code": ["90210", "73301", "98101", "10001", "60601", "30301", "80201"],
    "street": ["123 Main Street", "456 Oak Avenue", "789 Pine Road", "101 Maple Blvd", "202 Cedar Lane"],
    "barcode": ["1234567890", "9876543210", "1122334455", "5566778899", "8899001122"],
    "order_id": ["ORD-1001", "ORD-1002", "ORD-1003", "ORD-1004", "ORD-1005"],
    "status": ["Active", "Pending", "Completed", "Archived", "Approved", "In Review"],
}


class TestDataGeneratorService:
    """Intelligent adaptive test data generation service."""

    def __init__(self, application_id: int):
        self.application_id = application_id
        self.learner = SelfLearningEngine(application_id)

    async def generate_dataset(
        self,
        *,
        dataset_name: str,
        description: str | None = None,
        field_names: list[str] | None = None,
        scenario_types: list[str] | None = None,
        row_count: int = 10,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Synthesizes a structured test dataset with balanced coverage across
        valid, invalid, boundary, and edge scenarios.
        """
        scenario_types = scenario_types or ["valid", "invalid", "boundary", "edge"]
        fields = field_names or ["first_name", "last_name", "email", "phone", "status"]

        # 1. Query live learned entity memory for this application
        learned_context = {}
        for fld in fields:
            entities = self.learner.get_discovered_entities(fld, limit=5)
            if entities:
                learned_context[fld] = entities

        # 2. Attempt AI-driven synthesis with strict prompt contract
        try:
            ai_rows = await self._generate_with_ai(
                dataset_name=dataset_name,
                fields=fields,
                scenario_types=scenario_types,
                row_count=row_count,
                learned_context=learned_context,
                provider=provider,
                model=model,
            )
            if ai_rows and len(ai_rows) >= max(1, row_count // 2):
                logger.info("Generated %d AI test data rows for application %d", len(ai_rows), self.application_id)
                return ai_rows[:row_count]
        except Exception as err:
            logger.warning("AI test data generation fell back to rule-based engine: %s", err)

        # 3. Deterministic rule-based adaptive fallback
        return self._generate_with_rules(
            fields=fields,
            scenario_types=scenario_types,
            row_count=row_count,
            learned_context=learned_context,
        )

    async def _generate_with_ai(
        self,
        *,
        dataset_name: str,
        fields: list[str],
        scenario_types: list[str],
        row_count: int,
        learned_context: dict[str, list[str]],
        provider: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        learned_hint = ""
        if learned_context:
            lines = [f"- {k}: {', '.join(v)}" for k, v in learned_context.items()]
            learned_hint = "\nLive application entities discovered during execution (use or reference these where applicable):\n" + "\n".join(lines)

        prompt = (
            f"Generate a comprehensive QA test dataset for '{dataset_name}'.\n"
            f"Required Fields: {', '.join(fields)}\n"
            f"Target Row Count: {row_count}\n"
            f"Scenario Coverage: {', '.join(scenario_types)}\n"
            f"{learned_hint}\n\n"
            "Output JSON format only with shape:\n"
            "{\n"
            '  "rows": [\n'
            '    {"_scenario": "valid|invalid|boundary|edge", "field_name": "value", ...}\n'
            "  ]\n"
            "}\n"
            "Ensure realistic types, formatted dates, standard phone numbers, and valid/invalid variations."
        )

        system_content = (
            "You are the Test Data Generator Agent. You generate structured, realistic, "
            "privacy-compliant test datasets for automated QA testing."
        )

        for settings in _load_provider_settings(provider, model):
            try:
                parsed = await _request_provider_json(settings, prompt, system_content=system_content, agent_key="test_data_generator")
                rows = parsed.get("rows") if isinstance(parsed.get("rows"), list) else None
                if rows:
                    return [r for r in rows if isinstance(r, dict)]
            except AIServiceError:
                continue

        return []

    def _generate_with_rules(
        self,
        *,
        fields: list[str],
        scenario_types: list[str],
        row_count: int,
        learned_context: dict[str, list[str]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        for i in range(row_count):
            scenario = scenario_types[i % len(scenario_types)]
            row: dict[str, Any] = {"_scenario": scenario}

            for fld in fields:
                norm_fld = fld.lower().replace(" ", "_").replace("-", "_")
                # Check if we have learned live entities from previous runs
                learned_vals = learned_context.get(fld) or learned_context.get(norm_fld)

                if scenario == "valid":
                    if learned_vals:
                        row[fld] = random.choice(learned_vals)
                    else:
                        row[fld] = self._generate_valid_field(norm_fld, i)
                elif scenario == "invalid":
                    row[fld] = self._generate_invalid_field(norm_fld, i)
                elif scenario == "boundary":
                    row[fld] = self._generate_boundary_field(norm_fld, i)
                else:  # edge / security
                    row[fld] = self._generate_edge_field(norm_fld, i)

            rows.append(row)

        return rows

    def _generate_valid_field(self, norm_fld: str, index: int) -> str:
        clean_fld = re.sub(r"[^a-z0-9]", "", norm_fld.lower())

        if "zip" in clean_fld or "postal" in clean_fld:
            return random.choice(DEFAULT_ENTITIES["zip_code"])
        if "barcode" in clean_fld or "sku" in clean_fld:
            return random.choice(DEFAULT_ENTITIES["barcode"])
        if "order" in clean_fld:
            return f"ORD-{1001 + index}"
        if "last" in clean_fld:
            return random.choice(DEFAULT_ENTITIES["last_name"])
        if "first" in clean_fld or "name" in clean_fld:
            return random.choice(DEFAULT_ENTITIES["first_name"])
        if "location" in clean_fld or "city" in clean_fld:
            return random.choice(DEFAULT_ENTITIES["city"])
        if "state" in clean_fld:
            return random.choice(DEFAULT_ENTITIES["state"])
        if "street" in clean_fld or "address" in clean_fld:
            return random.choice(DEFAULT_ENTITIES["street"])
        if "search" in clean_fld or "query" in clean_fld or "term" in clean_fld or "keyword" in clean_fld:
            return random.choice(["test", "active", "general", "report", "sample"])
        if "status" in clean_fld:
            return random.choice(DEFAULT_ENTITIES["status"])

        for entity_key, samples in DEFAULT_ENTITIES.items():
            norm_key = re.sub(r"[^a-z0-9]", "", entity_key.lower())
            if norm_key in clean_fld or clean_fld in norm_key:
                return random.choice(samples)

        if "email" in clean_fld or "mail" in clean_fld:
            return f"qa.user{index + 1}@example.test"
        if "phone" in clean_fld or "mobile" in clean_fld:
            return f"555010{index:04d}"
        if "date" in clean_fld:
            return f"2026-09-{(index % 28) + 1:02d}"
        if "amount" in clean_fld or "price" in clean_fld or "cost" in clean_fld:
            return f"{((index + 1) * 24.50):.2f}"
        if "quantity" in clean_fld or "qty" in clean_fld or "count" in clean_fld:
            return str((index % 5) + 1)
        if "id" in clean_fld or "code" in clean_fld:
            return f"ID-{1000 + index}"

        return f"Sample {norm_fld.replace('_', ' ').title()} {index + 1}"

    def _generate_invalid_field(self, norm_fld: str, index: int) -> str:
        if "email" in norm_fld:
            return f"invalid-email-format-{index}"
        if "phone" in norm_fld or "mobile" in norm_fld:
            return "not-a-phone-number"
        if "date" in norm_fld:
            return "2026-99-99"
        if "amount" in norm_fld or "price" in norm_fld:
            return "-99.99"
        if "quantity" in norm_fld or "count" in norm_fld:
            return "-5"
        if "barcode" in norm_fld or "id" in norm_fld:
            return "NON_EXISTENT_ID_999999"

        return "INVALID_DATA_VALUE"

    def _generate_boundary_field(self, norm_fld: str, index: int) -> str:
        if "amount" in norm_fld or "price" in norm_fld:
            return "0.01" if index % 2 == 0 else "999999.99"
        if "quantity" in norm_fld or "count" in norm_fld:
            return "0" if index % 2 == 0 else "9999"
        if "email" in norm_fld:
            return "a" * 64 + "@example.com"
        if "name" in norm_fld:
            return "A" if index % 2 == 0 else "A" * 120

        return "0" if index % 2 == 0 else "A" * 100

    def _generate_edge_field(self, norm_fld: str, index: int) -> str:
        edge_values = [
            "  leading and trailing whitespace  ",
            "Special!@#$%^&*()_+=-`~",
            "Unicode ñöë 🚀 ✨",
            "O'Connor",
            "Smith-Jones & Co.",
            "test<script>alert(1)</script>",
        ]
        return edge_values[index % len(edge_values)]
