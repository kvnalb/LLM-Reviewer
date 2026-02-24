from __future__ import annotations

import json
import os
import re
from typing import Dict, Protocol

import httpx

from reviewer_sim.utils.config import ModelConfig
from reviewer_sim.ingest.export_review_subset import SCORE_COLUMNS

# Re-exported for convenience; canonical source is export_review_subset.SCORE_COLUMNS.
SCORE_DIMENSIONS = SCORE_COLUMNS


class BaseGenerator(Protocol):
    def generate(self, example: Dict) -> Dict:
        """Return a dict with the five SCORE_DIMENSIONS keys and optional 'rationale'."""
        ...


class MockGenerator:
    """Deterministic mock reviewer that uses reviewer_profile if present.

    Returns all five score dimensions derived from the tone profile.
    """

    def generate(self, example: Dict) -> Dict:
        title = example.get("title", "Untitled")
        abstract = example.get("abstract", "") or ""

        profile = example.get("reviewer_profile", {}) or {}
        # Use primary_area_llm if available, otherwise fall back to profile expertise
        expertise = example.get("primary_area_llm") or profile.get("expertise", "general")
        seniority = profile.get("seniority", "unknown")
        tone = (profile.get("tone", "neutral") or "neutral").lower()

        tone_adjust = {"critical": -2, "neutral": 0, "positive": 2}
        adj = tone_adjust.get(tone, 0)

        rating = max(1, min(10, 6 + adj))
        confidence = max(1, min(5, 3 + (adj // 2)))
        correctness = max(1, min(4, 3 + (adj // 2)))
        tech_novelty = max(1, min(4, 3 + (adj // 2)))
        emp_novelty = max(1, min(4, 3 + (adj // 2)))

        tone_summary = {
            "critical": "The work has potential but significant issues limit confidence.",
            "neutral": "The work is clear and contributes in a modest, understandable way.",
            "positive": "The work is strong and well-motivated with promising results.",
        }.get(tone, "The work is clear and contributes in a modest, understandable way.")

        tone_strengths = {
            "critical": "There is a plausible idea, but the evidence is thin.",
            "neutral": "The motivation is sound and the framing is coherent.",
            "positive": "The motivation is compelling and the framing is strong.",
        }.get(tone, "The motivation is sound and the framing is coherent.")

        tone_weaknesses = {
            "critical": "Key {expertise} details are missing, which hurts credibility.",
            "neutral": "Some {expertise} details are missing from the abstract.",
            "positive": "A few {expertise} details could be clarified in the full paper.",
        }.get(tone, "Some {expertise} details are missing from the abstract.")

        review_text = f"""Summary:
This submission "{title}" is about: {abstract[:400]}
{tone_summary}

Reviewer context:
- Expertise: {expertise}
- Seniority: {seniority}
- Tone: {tone}

Strengths:
- {tone_strengths}
- The approach appears relevant to {expertise} based on the abstract.

Weaknesses:
- {tone_weaknesses.format(expertise=expertise)}
- Evaluation details are unclear or incomplete from the provided abstract.

Questions:
1) What are the main failure cases?
2) How does the method compare to the closest prior work?
3) What ablations support the key claims?

Recommendation:
Overall score: {rating}
"""
        return {
            "text": review_text,
            "rating": rating,
            "confidence": confidence,
            "correctness": correctness,
            "technical_novelty_and_significance": tech_novelty,
            "empirical_novelty_and_significance": emp_novelty,
        }


class LlamaCppGenerator:
    """Generator using llama-cpp-python with a local GGUF model.

    Model is loaded ONCE in __init__ and reused for all generate() calls.
    """

    def __init__(self, config: ModelConfig):
        self.config = config

        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError(
                "llama-cpp-python is not installed. "
                "Install with: pip install llama-cpp-python"
            ) from exc

        if not config.model_path:
            raise ValueError("MODEL_PATH must be set for llamacpp provider.")

        self.llm = Llama(
            model_path=config.model_path,
            n_ctx=config.n_ctx,
            n_gpu_layers=config.n_gpu_layers,
            verbose=False,
        )

    def _build_prompt(self, example: Dict) -> str:
        title = example.get("title", "Untitled")

        # Check for PDF content first, fallback to abstract
        pdf_content = example.get("pdf_content", {})
        if pdf_content and pdf_content.get("extraction_metadata", {}).get("success"):
            content = pdf_content.get("full_text", "")
            content_label = "Paper Content"
        else:
            content = example.get("abstract", "") or ""
            content_label = "Abstract"

        # Format system prompt with primary_area if available
        primary_area = example.get("primary_area_llm", "general")
        system_prompt = self.config.system_prompt.format(primary_area=primary_area)

        # Use explicit JSON formatting for base models (like Qwen)
        # This is more compatible with non-chat models
        prompt = f"""{system_prompt}

Title: {title}

{content_label}:
{content}

IMPORTANT: Your response MUST be ONLY a valid JSON object. Do not include any text before or after the JSON.

Example JSON format:
{{"rating": 8, "confidence": 4, "correctness": 3, "technical_novelty_and_significance": 3, "empirical_novelty_and_significance": 3, "rationale": "Brief summary here"}}

Now provide the JSON scores for the paper above:"""
        return prompt

    def _parse_json_response(self, content: str) -> Dict:
        content = content.strip()

        parsed = self._try_parse_json(content)
        if parsed is not None:
            return self._normalise_scores(parsed)

        result: Dict = {"text": content}
        for dim in SCORE_DIMENSIONS:
            result[dim] = None
        return result

    @staticmethod
    def _is_score_dict(data: object) -> bool:
        """Check if data is a dict containing at least one expected score key."""
        if not isinstance(data, dict):
            return False
        expected = {*SCORE_DIMENSIONS, "text", "rationale"}
        return bool(expected & data.keys())

    @staticmethod
    def _try_parse_json(content: str) -> Dict | None:
        try:
            data = json.loads(content)
            if LlamaCppGenerator._is_score_dict(data):
                return data
        except json.JSONDecodeError:
            pass

        # Try to find a JSON object containing "rating" (most reliable key)
        json_match = re.search(r'\{[^{}]*"rating"[^{}]*\}', content, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                if LlamaCppGenerator._is_score_dict(data):
                    return data
            except json.JSONDecodeError:
                pass

        # Fallback: extract outermost braces
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(content[start : end + 1])
                if LlamaCppGenerator._is_score_dict(data):
                    return data
            except json.JSONDecodeError:
                pass

        # Last resort: regex-extract individual integer score fields.
        # Handles models (e.g. Qwen3) that emit an unquoted rationale string,
        # making the whole JSON unparseable via standard json.loads.
        int_dims = [d for d in SCORE_DIMENSIONS]
        extracted: Dict = {}
        for dim in int_dims:
            m = re.search(rf'"{dim}"\s*:\s*(\d+)', content)
            if m:
                extracted[dim] = int(m.group(1))
        if extracted:
            # Also try to capture rationale/text as raw string (best-effort)
            rat_m = re.search(r'"rationale"\s*:\s*(.+?)(?=,\s*"|\s*\})', content, re.DOTALL)
            if rat_m:
                extracted["text"] = rat_m.group(1).strip().strip('"')
            return extracted

        return None

    @staticmethod
    def _normalise_scores(data: Dict) -> Dict:
        for dim in SCORE_DIMENSIONS:
            val = data.get(dim)
            if val is not None:
                try:
                    data[dim] = int(val)
                except (ValueError, TypeError):
                    data[dim] = None
            else:
                data[dim] = None
        # Normalise: accept both "rationale" and "text" for the free-text field
        if "rationale" in data and "text" not in data:
            data["text"] = data["rationale"]
        if "text" not in data:
            data["text"] = ""
        return data

    def generate(self, example: Dict) -> Dict:
        prompt = self._build_prompt(example)
        response = self.llm(
            prompt, temperature=self.config.temperature, top_p=self.config.top_p,
            max_tokens=self.config.max_tokens, stop=None,
        )
        content = response["choices"][0]["text"]
        return self._parse_json_response(content)


TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"


class TogetherGenerator:
    """Generator using Together AI chat completions API.

    Requires TOGETHER_API_KEY environment variable.
    Uses config.model_path as the Together model ID
    (e.g. "meta-llama/Llama-3-8b-chat-hf").

    Usage:
        MODEL_PROVIDER=together MODEL_PATH=meta-llama/Llama-3-8b-chat-hf \\
            TOGETHER_API_KEY=your-key python -m reviewer_sim.run
    """

    def __init__(self, config: ModelConfig):
        self.config = config
        self.api_key = os.environ.get("TOGETHER_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "TOGETHER_API_KEY environment variable is required for "
                "the 'together' provider."
            )
        if not config.model_path:
            raise ValueError(
                "MODEL_PATH must be set to a Together model ID "
                "(e.g. 'meta-llama/Llama-3-8b-chat-hf') for the 'together' provider."
            )
        self.model_id = config.model_path
        self.client = httpx.Client(timeout=60.0)

    def _build_messages(self, example: Dict) -> list[dict]:
        title = example.get("title", "Untitled")

        # Check for PDF content first, fallback to abstract
        pdf_content = example.get("pdf_content", {})
        if pdf_content and pdf_content.get("extraction_metadata", {}).get("success"):
            content = pdf_content.get("full_text", "")[:20000]  # Conservative char limit
            content_label = "Paper Content"
        else:
            content = (example.get("abstract", "") or "")[:3000]  # Keep old truncation
            content_label = "Abstract"

        # Format system prompt with primary_area if available
        primary_area = example.get("primary_area_llm", "general")
        system_prompt = self.config.system_prompt.format(primary_area=primary_area)

        user_content = (
            f"Title: {title}\n\n"
            f"{content_label}:\n{content}\n\n"
            "Predict the review scores as JSON."
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    def generate(self, example: Dict) -> Dict:
        messages = self._build_messages(example)

        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "top_p": self.config.top_p,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.post(
                    TOGETHER_API_URL, json=payload, headers=headers,
                )
                if response.status_code == 429:
                    import time
                    print(f"\n[429] Rate limited. Retrying in {2**attempt}s...")
                    time.sleep(2 ** attempt)
                    continue

                if response.status_code >= 400:
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        print(f"\n[API Error] {e}")
                        print(f"Server response provided: {response.text}")
                        # Don't retry client errors (4xx) except 429
                        if response.status_code < 500:
                            result: Dict = {"text": f"[API error: {response.status_code}]"}
                            for dim in SCORE_DIMENSIONS:
                                result[dim] = None
                            return result
                        raise e

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return self._parse_response(content)

            except (httpx.HTTPError, KeyError, json.JSONDecodeError):
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)
                    continue
                # Final failure — return empty scores
                result: Dict = {"text": f"[API error after {max_retries} retries]"}
                for dim in SCORE_DIMENSIONS:
                    result[dim] = None
                return result

        result = {"text": "[API error: exhausted retries]"}
        for dim in SCORE_DIMENSIONS:
            result[dim] = None
        return result

    def _parse_response(self, content: str) -> Dict:
        """Parse JSON from Together API response, reusing LlamaCpp logic."""
        content = content.strip()

        # Strip <think>...</think> blocks (DeepSeek-R1 and other reasoning models)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        parsed = LlamaCppGenerator._try_parse_json(content)
        if parsed is not None:
            return LlamaCppGenerator._normalise_scores(parsed)

        result: Dict = {"text": content}
        for dim in SCORE_DIMENSIONS:
            result[dim] = None
        return result


def get_generator(config: ModelConfig) -> BaseGenerator:
    """Factory function to create a generator based on config.provider."""
    provider = (config.provider or "mock").lower()
    if provider == "mock":
        return MockGenerator()
    if provider in ("llamacpp", "llama_cpp"):
        return LlamaCppGenerator(config=config)
    if provider in ("together", "together_ai", "togetherai"):
        return TogetherGenerator(config=config)
    raise ValueError(f"Unknown provider: {config.provider}")
