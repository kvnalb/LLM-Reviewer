"""
Tests for the enrich_primary_area module.

Run with: pytest tests/test_enrich_primary_area.py -v
"""

import json
import pytest
from pathlib import Path

from reviewer_sim.ingest.enrich_primary_area import (
    parse_llm_response,
    ALLOWED_LABELS,
    load_existing_paper_ids,
)


class TestParseResponse:
    """Test LLM response parsing and validation."""

    def test_valid_json_response(self) -> None:
        """Parse a valid JSON response with valid label and confidence."""
        response = '{"primary_area_llm": "nlp", "primary_area_llm_confidence": 0.85}'
        result = parse_llm_response(response)
        assert result["primary_area_llm"] == "nlp"
        assert result["primary_area_llm_confidence"] == 0.85

    def test_invalid_label_defaults_to_other(self) -> None:
        """Invalid label should be coerced to 'other'."""
        response = '{"primary_area_llm": "invalid_area", "primary_area_llm_confidence": 0.9}'
        result = parse_llm_response(response)
        assert result["primary_area_llm"] == "other"
        assert result["primary_area_llm_confidence"] == 0.9

    def test_confidence_clamped_to_0_to_1(self) -> None:
        """Confidence values outside [0, 1] should be clamped."""
        response = '{"primary_area_llm": "ml", "primary_area_llm_confidence": 1.5}'
        result = parse_llm_response(response)
        assert result["primary_area_llm"] == "ml"
        assert result["primary_area_llm_confidence"] == 1.0

        response = '{"primary_area_llm": "ml", "primary_area_llm_confidence": -0.5}'
        result = parse_llm_response(response)
        assert result["primary_area_llm_confidence"] == 0.0

    def test_non_numeric_confidence_defaults_to_0_3(self) -> None:
        """Non-numeric confidence should default to 0.3."""
        response = '{"primary_area_llm": "ml", "primary_area_llm_confidence": "invalid"}'
        result = parse_llm_response(response)
        assert result["primary_area_llm"] == "ml"
        assert result["primary_area_llm_confidence"] == 0.3

    def test_missing_confidence_defaults_to_0_3(self) -> None:
        """Missing confidence should default to 0.3."""
        response = '{"primary_area_llm": "nlp"}'
        result = parse_llm_response(response)
        assert result["primary_area_llm"] == "nlp"
        assert result["primary_area_llm_confidence"] == 0.3

    def test_missing_label_defaults_to_other(self) -> None:
        """Missing label should default to 'other'."""
        response = '{"primary_area_llm_confidence": 0.5}'
        result = parse_llm_response(response)
        assert result["primary_area_llm"] == "other"
        assert result["primary_area_llm_confidence"] == 0.5

    def test_strips_think_blocks(self) -> None:
        """DeepSeek-R1 style <think> blocks should be stripped."""
        response = '<think>This is a reasoning paper about NLP</think>{"primary_area_llm": "nlp", "primary_area_llm_confidence": 0.9}'
        result = parse_llm_response(response)
        assert result["primary_area_llm"] == "nlp"
        assert result["primary_area_llm_confidence"] == 0.9

    def test_malformed_json_fallback_regex(self) -> None:
        """Should extract JSON object from malformed response via regex."""
        response = 'Some text before {"primary_area_llm": "computer_vision", "primary_area_llm_confidence": 0.75} some text after'
        result = parse_llm_response(response)
        assert result["primary_area_llm"] == "computer_vision"
        assert result["primary_area_llm_confidence"] == 0.75

    def test_completely_invalid_json_returns_fallback(self) -> None:
        """Completely invalid response should return fallback."""
        response = "This is just plain text with no JSON"
        result = parse_llm_response(response)
        assert result["primary_area_llm"] == "other"
        assert result["primary_area_llm_confidence"] == 0.3

    def test_all_valid_labels_accepted(self) -> None:
        """All labels in ALLOWED_LABELS should be accepted."""
        for label in ALLOWED_LABELS:
            response = f'{{"primary_area_llm": "{label}", "primary_area_llm_confidence": 0.8}}'
            result = parse_llm_response(response)
            assert result["primary_area_llm"] == label

    def test_confidence_boundaries(self) -> None:
        """Test confidence values at boundary conditions."""
        # Exactly 0.0
        response = '{"primary_area_llm": "ml", "primary_area_llm_confidence": 0.0}'
        result = parse_llm_response(response)
        assert result["primary_area_llm_confidence"] == 0.0

        # Exactly 1.0
        response = '{"primary_area_llm": "ml", "primary_area_llm_confidence": 1.0}'
        result = parse_llm_response(response)
        assert result["primary_area_llm_confidence"] == 1.0

    def test_empty_response_returns_fallback(self) -> None:
        """Empty response should return fallback."""
        result = parse_llm_response("")
        assert result["primary_area_llm"] == "other"
        assert result["primary_area_llm_confidence"] == 0.3

    def test_case_sensitivity_of_labels(self) -> None:
        """Labels should be case-sensitive (lowercase expected)."""
        response = '{"primary_area_llm": "NLP", "primary_area_llm_confidence": 0.8}'
        result = parse_llm_response(response)
        # NLP is uppercase, not in ALLOWED_LABELS (all lowercase), so should default to "other"
        assert result["primary_area_llm"] == "other"


class TestLoadExistingPaperIds:
    """Test resume functionality."""

    def test_load_existing_ids_from_file(self, tmp_path: Path) -> None:
        """Load paper_ids from existing enriched JSONL file."""
        out_file = tmp_path / "enriched.jsonl"
        records = [
            {"paper_id": "paper_1", "primary_area_llm": "nlp"},
            {"paper_id": "paper_2", "primary_area_llm": "ml"},
            {"paper_id": "paper_3", "primary_area_llm": "computer_vision"},
        ]
        with open(out_file, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        paper_ids = load_existing_paper_ids(out_file)
        assert paper_ids == {"paper_1", "paper_2", "paper_3"}

    def test_load_existing_ids_empty_file(self, tmp_path: Path) -> None:
        """Empty file should return empty set."""
        out_file = tmp_path / "empty.jsonl"
        out_file.write_text("")
        paper_ids = load_existing_paper_ids(out_file)
        assert paper_ids == set()

    def test_load_existing_ids_nonexistent_file(self, tmp_path: Path) -> None:
        """Nonexistent file should return empty set."""
        out_file = tmp_path / "nonexistent.jsonl"
        paper_ids = load_existing_paper_ids(out_file)
        assert paper_ids == set()

    def test_load_existing_ids_skips_malformed_lines(self, tmp_path: Path) -> None:
        """Malformed JSON lines should be skipped."""
        out_file = tmp_path / "mixed.jsonl"
        with open(out_file, "w") as f:
            f.write('{"paper_id": "paper_1", "primary_area_llm": "nlp"}\n')
            f.write('This is not valid JSON\n')
            f.write('{"paper_id": "paper_2", "primary_area_llm": "ml"}\n')
            f.write('{invalid json}\n')

        paper_ids = load_existing_paper_ids(out_file)
        assert paper_ids == {"paper_1", "paper_2"}

    def test_load_existing_ids_missing_paper_id_field(self, tmp_path: Path) -> None:
        """Records without paper_id field should be skipped."""
        out_file = tmp_path / "no_id.jsonl"
        with open(out_file, "w") as f:
            f.write('{"paper_id": "paper_1", "primary_area_llm": "nlp"}\n')
            f.write('{"primary_area_llm": "ml"}\n')  # No paper_id
            f.write('{"paper_id": "paper_3", "primary_area_llm": "computer_vision"}\n')

        paper_ids = load_existing_paper_ids(out_file)
        assert paper_ids == {"paper_1", "paper_3"}

    def test_load_existing_ids_numeric_paper_ids(self, tmp_path: Path) -> None:
        """Numeric paper_ids should be converted to strings."""
        out_file = tmp_path / "numeric.jsonl"
        with open(out_file, "w") as f:
            f.write('{"paper_id": 123, "primary_area_llm": "nlp"}\n')
            f.write('{"paper_id": "paper_2", "primary_area_llm": "ml"}\n')

        paper_ids = load_existing_paper_ids(out_file)
        assert "123" in paper_ids
        assert "paper_2" in paper_ids




class TestAllowedLabels:
    """Test that ALLOWED_LABELS is properly defined."""

    def test_allowed_labels_not_empty(self) -> None:
        """ALLOWED_LABELS should contain all expected areas."""
        assert len(ALLOWED_LABELS) > 0

    def test_allowed_labels_contains_expected_areas(self) -> None:
        """ALLOWED_LABELS should contain all expected research areas."""
        expected = {
            "computer_vision",
            "nlp",
            "ml",
            "robotics",
            "graphics",
            "systems",
            "theory",
            "hci",
            "bio_medical",
            "multi_modal",
            "other",
        }
        assert ALLOWED_LABELS == expected

    def test_allowed_labels_is_frozenset(self) -> None:
        """ALLOWED_LABELS should be immutable."""
        assert isinstance(ALLOWED_LABELS, frozenset)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
