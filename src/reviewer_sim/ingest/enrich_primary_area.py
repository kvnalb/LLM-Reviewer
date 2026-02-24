"""
Enrich processed JSONL with LLM-classified primary_area labels.

This script creates a DERIVED dataset - it does NOT modify the original JSONL.
Each record is enriched with:
  - primary_area_llm: one of the allowed labels
  - primary_area_llm_confidence: float 0.0-1.0
  - meta.llm_labeling: provider, model, prompt_version, temperature, timestamp

Environment variables:
  TOGETHER_API_KEY: Your Together AI API key (required)

Example usage:
  export TOGETHER_API_KEY="your-key-here"

  # Enrich all records
  python -m reviewer_sim.ingest.enrich_primary_area \\
    --in-path outputs/review_subset.jsonl \\
    --out-path outputs/review_subset_enriched.jsonl \\
    --model "meta-llama/Llama-3-8b-chat-hf"

  # Enrich first 10 records only
  python -m reviewer_sim.ingest.enrich_primary_area \\
    --in-path outputs/review_subset.jsonl \\
    --out-path outputs/review_subset_enriched.jsonl \\
    --limit 10

  # Resume interrupted run
  python -m reviewer_sim.ingest.enrich_primary_area \\
    --in-path outputs/review_subset.jsonl \\
    --out-path outputs/review_subset_enriched.jsonl \\
    --resume

Context: The primary_area_llm label is used to "assign a role" to the LLM Reviewer
for each paper — i.e. a domain expert reviewer persona is selected based on this label.
The original `primary_area` field from the database is often non-standard or missing;
this script provides a clean, consistent label from a fixed taxonomy.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx
from tqdm import tqdm


# ---------------------------------------------------------------------------
# Label taxonomy
# ---------------------------------------------------------------------------

ALLOWED_LABELS = frozenset([
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
])

# Matches the constant used in generate/providers.py
TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"

PROMPT_VERSION = "area-v1"

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a research paper classifier. Given a paper's title and abstract, classify it into exactly ONE primary research area.

You MUST respond with ONLY a JSON object in this exact format:
{"primary_area_llm": "<label>", "primary_area_llm_confidence": <float>}

Allowed labels (choose exactly one):
- "computer_vision" - image/video processing, object detection, segmentation, 3D vision
- "nlp" - natural language processing, text understanding, language models for text
- "ml" - general machine learning, optimization, learning theory, neural architectures
- "robotics" - robot control, planning, manipulation, autonomous systems
- "graphics" - rendering, animation, 3D modeling, visual synthesis
- "systems" - distributed systems, databases, networks, hardware/software systems
- "theory" - theoretical CS, algorithms, complexity, formal methods
- "hci" - human-computer interaction, user interfaces, accessibility
- "bio_medical" - bioinformatics, medical imaging, drug discovery, health AI
- "multi_modal" - combining vision+language, audio+text, cross-modal learning
- "other" - if none of the above fit or content is ambiguous

Confidence guidelines:
- 0.9-1.0: Very clear fit, obvious category
- 0.7-0.89: Good fit, minor ambiguity
- 0.5-0.69: Reasonable guess, multiple categories could apply
- 0.3-0.49: Low confidence, ambiguous content
- <0.3: Very uncertain, use "other"

If abstract is empty or too short to classify, return {"primary_area_llm": "other", "primary_area_llm_confidence": 0.3}"""

USER_PROMPT_TEMPLATE = """Classify this paper:

Title: {title}

Abstract: {abstract}

Respond with ONLY the JSON object, no other text."""

# Maximum abstract characters sent to the API
_ABSTRACT_MAX_CHARS = 3000


# ---------------------------------------------------------------------------
# LLM call + response parsing
# ---------------------------------------------------------------------------


def parse_llm_response(content: str) -> dict:
    """Parse and validate the JSON object returned by the LLM."""
    # Strip <think>...</think> blocks (DeepSeek-R1 and similar reasoning models)
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'\{[^{}]*"primary_area_llm"[^{}]*\}', content)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError:
                return {"primary_area_llm": "other", "primary_area_llm_confidence": 0.3}
        else:
            return {"primary_area_llm": "other", "primary_area_llm_confidence": 0.3}

    # Validate label
    label = result.get("primary_area_llm", "other")
    if label not in ALLOWED_LABELS:
        label = "other"

    # Validate confidence
    try:
        confidence = float(result.get("primary_area_llm_confidence", 0.3))
        confidence = max(0.0, min(1.0, confidence))
    except (ValueError, TypeError):
        confidence = 0.3

    return {"primary_area_llm": label, "primary_area_llm_confidence": confidence}


async def call_together_api(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    title: str,
    abstract: str,
    max_retries: int = 3,
) -> dict:
    """Call Together AI chat completions API to classify a single paper."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    abstract_truncated = (abstract or "")[:_ABSTRACT_MAX_CHARS]
    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=title or "Untitled",
        abstract=abstract_truncated or "[No abstract provided]",
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "max_tokens": 100,
    }

    for attempt in range(max_retries):
        try:
            response = await client.post(
                TOGETHER_API_URL,
                headers=headers,
                json=payload,
                timeout=30.0,
            )

            if response.status_code == 429:
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
                continue

            if response.status_code >= 500:
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
                continue

            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            return parse_llm_response(content)

        except (httpx.HTTPError, KeyError, json.JSONDecodeError):
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            return {"primary_area_llm": "other", "primary_area_llm_confidence": 0.3}

    return {"primary_area_llm": "other", "primary_area_llm_confidence": 0.3}


# ---------------------------------------------------------------------------
# Per-record enrichment
# ---------------------------------------------------------------------------


async def enrich_record(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    record: dict,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Enrich a single record with LLM classification (thread-safe via semaphore)."""
    async with semaphore:
        classification = await call_together_api(
            client=client,
            api_key=api_key,
            model=model,
            title=record.get("title", ""),
            abstract=record.get("abstract", ""),
        )

    enriched = dict(record)
    enriched["primary_area_llm"] = classification["primary_area_llm"]
    enriched["primary_area_llm_confidence"] = classification["primary_area_llm_confidence"]

    # Add labeling provenance under meta.llm_labeling (preserves existing meta keys)
    meta = dict(enriched.get("meta", {}))
    meta["llm_labeling"] = {
        "provider": "together",
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "temperature": 0,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    enriched["meta"] = meta

    return enriched


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------


async def process_batch(
    records: list[dict],
    api_key: str,
    model: str,
    max_concurrency: int,
    progress_bar: tqdm,
) -> list[dict]:
    """Process a list of records with bounded concurrency, updating tqdm as each completes."""
    semaphore = asyncio.Semaphore(max_concurrency)

    async with httpx.AsyncClient() as client:

        async def _enrich_and_tick(record: dict) -> dict:
            result = await enrich_record(client, api_key, model, record, semaphore)
            progress_bar.update(1)
            return result

        tasks = [_enrich_and_tick(r) for r in records]
        return await asyncio.gather(*tasks)


# ---------------------------------------------------------------------------
# Resume helper
# ---------------------------------------------------------------------------


def load_existing_paper_ids(out_path: Path) -> set[str]:
    """Return the set of paper_ids already written to the output file."""
    if not out_path.exists():
        return set()

    paper_ids: set[str] = set()
    with open(out_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    record = json.loads(line)
                    pid = record.get("paper_id")
                    if pid:
                        paper_ids.add(str(pid))
                except json.JSONDecodeError:
                    continue
    return paper_ids


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich JSONL with LLM-classified primary_area labels (derived dataset).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--in-path",
        type=Path,
        required=True,
        help="Input JSONL file path (produced by export_review_subset)",
    )
    parser.add_argument(
        "--out-path",
        type=Path,
        required=True,
        help="Output JSONL file path (enriched, never overwrites input)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="meta-llama/Llama-3-8b-chat-hf",
        help="Together AI model ID (default: meta-llama/Llama-3-8b-chat-hf)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process only the first N records (0 = all)",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=8,
        help="Maximum concurrent API requests (default: 8)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip paper_ids already present in --out-path (append mode)",
    )

    args = parser.parse_args()

    # Validate API key
    api_key = os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        raise ValueError(
            "TOGETHER_API_KEY environment variable is required.\n"
            "Set it with: export TOGETHER_API_KEY='your-key-here'"
        )

    if not args.in_path.exists():
        raise FileNotFoundError(f"Input file not found: {args.in_path}")

    # Safety guard: refuse to overwrite the source file
    if args.in_path.resolve() == args.out_path.resolve():
        raise ValueError(
            "--in-path and --out-path must be different files. "
            "This script creates a DERIVED dataset."
        )

    # Load input records
    records: list[dict] = []
    with open(args.in_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    print(f"Loaded {len(records)} records from {args.in_path}")

    # Handle resume mode
    existing_ids: set[str] = set()
    if args.resume:
        existing_ids = load_existing_paper_ids(args.out_path)
        if existing_ids:
            before = len(records)
            records = [r for r in records if str(r.get("paper_id", "")) not in existing_ids]
            print(f"Resume mode: {len(existing_ids)} already done, {len(records)} remaining (skipped {before - len(records)})")

    # Apply limit AFTER resume filtering so --limit N always means N new records
    if args.limit > 0:
        records = records[: args.limit]
        print(f"Limited to first {args.limit} records")

    if not records:
        print("No records to process. Exiting.")
        return

    print(f"Processing {len(records)} records")
    print(f"Model       : {args.model}")
    print(f"Concurrency : {args.max_concurrency}")

    # Process in batches so we write incrementally (crash-safe)
    batch_size = 50
    label_counts: Counter = Counter()
    fallback_count = 0
    start_time = time.time()

    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    write_mode = "a" if (args.resume and existing_ids) else "w"

    with open(args.out_path, write_mode, encoding="utf-8") as out_f:
        with tqdm(total=len(records), unit="rec", desc="Enriching") as pbar:
            for batch_start in range(0, len(records), batch_size):
                batch = records[batch_start : batch_start + batch_size]

                enriched_batch: list[dict] = asyncio.run(
                    process_batch(batch, api_key, args.model, args.max_concurrency, pbar)
                )

                for rec in enriched_batch:
                    label = rec.get("primary_area_llm", "other")
                    conf = rec.get("primary_area_llm_confidence", 0.0)
                    label_counts[label] += 1
                    if label == "other" and conf <= 0.3:
                        fallback_count += 1
                    out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")

                # Flush after each batch so partial results are safe on interrupt
                out_f.flush()

    # Summary
    elapsed = time.time() - start_time
    total_written = sum(label_counts.values())

    print("\n" + "=" * 52)
    print("ENRICHMENT SUMMARY")
    print("=" * 52)
    print(f"Records processed : {total_written}")
    print(f"Time elapsed      : {elapsed:.1f}s  ({total_written / elapsed:.1f} rec/s)")
    print(f"Fallbacks (other, confidence ≤ 0.3) : {fallback_count}")
    print("\nLabel distribution:")
    for label, count in label_counts.most_common():
        pct = count / total_written * 100 if total_written else 0
        print(f"  {label:<30} {count:>4}  ({pct:.1f}%)")
    print(f"\nOutput written to: {args.out_path}")


if __name__ == "__main__":
    main()
