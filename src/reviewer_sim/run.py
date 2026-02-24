"""
Pipeline runner for reviewer simulation.

Reads input JSONL, generates reviews using configured provider, evaluates against
human reviews, and writes results to output JSONL.

The system prompt is customized per-paper based on the primary_area_llm field.
For best results, use an INPUT_JSONL enriched with primary_area_llm labels:

    1. Export review subset (creates base JSONL):
       python -m reviewer_sim.ingest.export_review_subset --db-path ... --out-path outputs/review_subset.jsonl

    2. Enrich with primary_area_llm classifications (adds domain expertise):
       export TOGETHER_API_KEY="your-key"
       python -m reviewer_sim.ingest.enrich_primary_area \\
         --in-path outputs/review_subset.jsonl \\
         --out-path outputs/review_subset_enriched.jsonl

    3. Run simulation with enriched data:
       python -m reviewer_sim.run

Environment variables:
    INPUT_JSONL: Input file path (default: outputs/review_subset.jsonl)
                 Should ideally be enriched with primary_area_llm field
    OUTPUT_JSONL: Output file path (default: outputs/results.jsonl)
    MODEL_PROVIDER: mock, llamacpp, or together (default: mock)
    MODEL_PATH: Path to GGUF model (llamacpp) or Together model ID (together)
    TOGETHER_API_KEY: Together AI API key (required for together provider)
"""

import json
import os
from pathlib import Path

from tqdm import tqdm

from reviewer_sim.ingest.load_jsonl import load_jsonl
from reviewer_sim.generate.providers import get_generator
from reviewer_sim.evaluate.metrics import evaluate
from reviewer_sim.utils.config import load_model_config


def main() -> None:
    config = load_model_config()
    generator = get_generator(config)

    print(f"Provider: {config.provider}")
    if config.model_path:
        print(f"Model path: {config.model_path}")

    input_path = Path(os.environ.get("INPUT_JSONL", "outputs/review_subset.jsonl"))
    output_path = Path(os.environ.get("OUTPUT_JSONL", "outputs/results.jsonl"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    examples = load_jsonl(input_path)
    print(f"Input path: {input_path}")
    print(f"Number of examples: {len(examples)}")
    print(f"Output path: {output_path}")

    with open(output_path, "w", encoding="utf-8") as f:
        for ex in tqdm(examples, desc="Simulating reviews"):
            try:
                generated = generator.generate(ex)
                metrics = evaluate(ex, generated)

                row = {
                    "paper_id": ex.get("paper_id"),
                    "generated_review": generated,
                    "metrics": metrics,
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            except Exception as exc:
                paper_id = ex.get("paper_id")
                print(f"Error processing paper_id={paper_id}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
