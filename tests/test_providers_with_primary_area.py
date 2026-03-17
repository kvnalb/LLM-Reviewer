"""
Tests for generators with primary_area_llm integration.

Validates that generators correctly format system prompts with research areas
and handle both abstract-only and PDF content scenarios.

Run with: pytest tests/test_providers_with_primary_area.py -v
"""

from reviewer_sim.generate.providers import MockGenerator, LlamaCppGenerator
from reviewer_sim.utils.config import ModelConfig


class TestMockGeneratorWithPrimaryArea:
    """Test MockGenerator uses primary_area_llm when available."""

    def test_generate_uses_primary_area_llm(self) -> None:
        """MockGenerator should use primary_area_llm for expertise if available."""
        gen = MockGenerator()

        example = {
            "title": "Test Paper",
            "abstract": "Test abstract",
            "primary_area_llm": "nlp",
            "reviewer_profile": {"expertise": "general", "tone": "neutral"},
        }

        result = gen.generate(example)

        # Should generate valid review with all required fields
        assert "rating" in result
        assert "confidence" in result
        assert "correctness" in result
        assert "technical_novelty_and_significance" in result
        assert "empirical_novelty_and_significance" in result
        assert "text" in result

        # Review text should mention the paper content
        assert "Test Paper" in result["text"] or len(result["text"]) > 0

    def test_generate_fallback_to_profile_expertise(self) -> None:
        """MockGenerator should fallback to reviewer_profile.expertise if no primary_area_llm."""
        gen = MockGenerator()

        example = {
            "title": "Test Paper",
            "abstract": "Test abstract",
            "reviewer_profile": {"expertise": "computer_vision", "tone": "neutral"},
        }

        result = gen.generate(example)

        # Should generate valid review
        assert "rating" in result
        assert isinstance(result["rating"], int)
        assert 1 <= result["rating"] <= 10

    def test_generate_defaults_to_general(self) -> None:
        """MockGenerator should default to 'general' if no expertise specified."""
        gen = MockGenerator()

        example = {
            "title": "Test Paper",
            "abstract": "Test abstract",
        }

        result = gen.generate(example)

        # Should generate valid review with default expertise
        assert "rating" in result


class TestLlamaCppGeneratorPromptFormatting:
    """Test LlamaCppGenerator formats system prompt with primary_area."""

    def test_build_prompt_with_primary_area_llm(self) -> None:
        """_build_prompt should format system prompt with primary_area_llm."""
        config = ModelConfig(
            provider="llamacpp",
            model_path="/fake/path.gguf",
            temperature=0.2,
            max_tokens=800,
            top_p=0.95,
            n_ctx=16384,
            n_gpu_layers=-1,
            system_prompt="You are expert in {primary_area}.",
        )

        gen = LlamaCppGenerator.__new__(LlamaCppGenerator)
        gen.config = config

        example = {
            "title": "Test Paper",
            "abstract": "Test abstract",
            "primary_area_llm": "nlp",
        }

        prompt = gen._build_prompt(example)

        # Prompt should include the formatted primary_area
        assert "You are expert in nlp." in prompt
        assert "Test Paper" in prompt
        assert "Test abstract" in prompt

    def test_build_prompt_defaults_to_general(self) -> None:
        """_build_prompt should default to 'general' if primary_area_llm missing."""
        config = ModelConfig(
            provider="llamacpp",
            model_path="/fake/path.gguf",
            temperature=0.2,
            max_tokens=800,
            top_p=0.95,
            n_ctx=16384,
            n_gpu_layers=-1,
            system_prompt="You are expert in {primary_area}.",
        )

        gen = LlamaCppGenerator.__new__(LlamaCppGenerator)
        gen.config = config

        example = {
            "title": "Test Paper",
            "abstract": "Test abstract",
        }

        prompt = gen._build_prompt(example)

        # Should default to "general"
        assert "You are expert in general." in prompt

    def test_build_prompt_abstract_only(self) -> None:
        """_build_prompt should use abstract when pdf_content not available."""
        config = ModelConfig(
            provider="llamacpp",
            model_path="/fake/path.gguf",
            temperature=0.2,
            max_tokens=800,
            top_p=0.95,
            n_ctx=16384,
            n_gpu_layers=-1,
            system_prompt="Test prompt",
        )

        gen = LlamaCppGenerator.__new__(LlamaCppGenerator)
        gen.config = config

        example = {
            "title": "Test Paper",
            "abstract": "This is the abstract content",
        }

        prompt = gen._build_prompt(example)

        # Should use abstract
        assert "Abstract:" in prompt
        assert "This is the abstract content" in prompt

    def test_build_prompt_with_pdf_content(self) -> None:
        """_build_prompt should use pdf_content when available."""
        config = ModelConfig(
            provider="llamacpp",
            model_path="/fake/path.gguf",
            temperature=0.2,
            max_tokens=800,
            top_p=0.95,
            n_ctx=16384,
            n_gpu_layers=-1,
            system_prompt="Test prompt",
        )

        gen = LlamaCppGenerator.__new__(LlamaCppGenerator)
        gen.config = config

        example = {
            "title": "Test Paper",
            "abstract": "This is the abstract",
            "pdf_content": {
                "extraction_metadata": {"success": True},
                "full_text": "This is the full PDF content from the paper",
            },
        }

        prompt = gen._build_prompt(example)

        # Should use PDF content, not abstract
        assert "Paper Content:" in prompt
        assert "This is the full PDF content from the paper" in prompt
        assert "This is the abstract" not in prompt

    def test_build_prompt_ignores_pdf_without_success_flag(self) -> None:
        """_build_prompt should ignore pdf_content if extraction_metadata.success is False."""
        config = ModelConfig(
            provider="llamacpp",
            model_path="/fake/path.gguf",
            temperature=0.2,
            max_tokens=800,
            top_p=0.95,
            n_ctx=16384,
            n_gpu_layers=-1,
            system_prompt="Test prompt",
        )

        gen = LlamaCppGenerator.__new__(LlamaCppGenerator)
        gen.config = config

        example = {
            "title": "Test Paper",
            "abstract": "This is the abstract",
            "pdf_content": {
                "extraction_metadata": {"success": False},
                "full_text": "This is failed extraction",
            },
        }

        prompt = gen._build_prompt(example)

        # Should fallback to abstract
        assert "Abstract:" in prompt
        assert "This is the abstract" in prompt

    def test_build_prompt_includes_long_abstract(self) -> None:
        """_build_prompt includes full abstract (no truncation for llamacpp)."""
        config = ModelConfig(
            provider="llamacpp",
            model_path="/fake/path.gguf",
            temperature=0.2,
            max_tokens=800,
            top_p=0.95,
            n_ctx=16384,
            n_gpu_layers=-1,
            system_prompt="Test prompt",
        )

        gen = LlamaCppGenerator.__new__(LlamaCppGenerator)
        gen.config = config

        long_abstract = "x" * 5000

        example = {
            "title": "Test Paper",
            "abstract": long_abstract,
        }

        prompt = gen._build_prompt(example)

        # LlamaCppGenerator does NOT truncate (context managed at model level)
        assert long_abstract in prompt

    def test_build_prompt_includes_long_pdf(self) -> None:
        """_build_prompt includes full PDF content (no truncation for llamacpp)."""
        config = ModelConfig(
            provider="llamacpp",
            model_path="/fake/path.gguf",
            temperature=0.2,
            max_tokens=800,
            top_p=0.95,
            n_ctx=16384,
            n_gpu_layers=-1,
            system_prompt="Test prompt",
        )

        gen = LlamaCppGenerator.__new__(LlamaCppGenerator)
        gen.config = config

        long_pdf = "x" * 25000

        example = {
            "title": "Test Paper",
            "pdf_content": {
                "extraction_metadata": {"success": True},
                "full_text": long_pdf,
            },
        }

        prompt = gen._build_prompt(example)

        # LlamaCppGenerator does NOT truncate (context managed at model level)
        assert long_pdf in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
