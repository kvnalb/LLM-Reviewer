from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SYSTEM_PROMPT = (
    "You are an ICLR peer reviewer assessing papers based on methods, results, and empirical validation.\n\n"
    "EVALUATION CRITERIA:\n"
    "1. Methods: Is the approach technically sound, novel, and well-motivated?\n"
    "2. Results: Are experiments comprehensive, rigorous, and properly compared to baselines?\n"
    "3. Scope: Are results generalizable or limited to narrow settings?\n"
    "4. Clarity: Is the paper well-written and easy to follow?\n\n"
    "IMPORTANT: Base your assessment primarily on the methods and results sections. "
    "Your scores should reflect the actual quality of the work, not marketing language.\n\n"
    "Return ONLY a valid JSON object with these keys:\n"
    '  "rating": int 1-10 '
    "(1: strong reject, 3: clear reject, 5: borderline reject, "
    "6: weak accept, 8: top 50% of accepted, 10: top 5%),\n"
    '  "confidence": int 1-5 '
    "(1: educated guess, 3: fairly confident, 5: absolutely certain),\n"
    '  "correctness": int 1-4 '
    "(1: major errors, 2: several errors, 3: minor issues, 4: correct),\n"
    '  "technical_novelty_and_significance": int 1-4 '
    "(1: no novelty, 2: incremental, 3: significant, 4: groundbreaking),\n"
    '  "empirical_novelty_and_significance": int 1-4 '
    "(1: no novelty, 2: incremental, 3: significant, 4: groundbreaking),\n"
    '  "rationale": string (MUST be 3 sentences or fewer. Focus on methods/results quality).\n'
    "No markdown, no extra text. JSON only."
)


@dataclass
class ModelConfig:
    provider: str
    model_path: str | None
    temperature: float
    max_tokens: int
    top_p: float
    n_ctx: int
    n_gpu_layers: int
    system_prompt: str


def load_model_config() -> ModelConfig:
    provider = os.environ.get("MODEL_PROVIDER", "mock").lower()
    model_path = os.environ.get("MODEL_PATH")
    temperature = float(os.environ.get("TEMPERATURE", "0.2"))
    max_tokens = int(os.environ.get("MAX_TOKENS", "200"))
    top_p = float(os.environ.get("TOP_P", "0.95"))
    n_ctx = int(os.environ.get("N_CTX", "16384"))
    n_gpu_layers = int(os.environ.get("N_GPU_LAYERS", "-1"))
    system_prompt = os.environ.get("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)

    if provider == "llamacpp":
        if not model_path:
            raise ValueError("MODEL_PATH env var is required when MODEL_PROVIDER=llamacpp")
        if not Path(model_path).exists():
            raise FileNotFoundError(f"MODEL_PATH does not exist: {model_path}")

    return ModelConfig(
        provider=provider,
        model_path=model_path,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        n_ctx=n_ctx,
        n_gpu_layers=n_gpu_layers,
        system_prompt=system_prompt,
    )
