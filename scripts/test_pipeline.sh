#!/usr/bin/env bash
# test_pipeline.sh — smoke test the full pipeline on a small subset of papers
#
# Usage:
#   bash scripts/test_pipeline.sh                                   # mock generator (no API key needed)
#   TOGETHER_API_KEY=xxx bash scripts/test_pipeline.sh              # Together AI, default model
#   TOGETHER_API_KEY=xxx MODEL_PATH=deepseek-ai/deepseek-v3.1 bash scripts/test_pipeline.sh
#
# Options (environment variables):
#   N            Number of papers (default: 5)
#   SEED         Random seed (default: 42)
#   SKIP_PDF     Set to 1 to skip PDF extraction step
#   MODEL_PATH   Together AI model ID (default: openai/gpt-oss-20b)

set -euo pipefail

N="${N:-5}"
SEED="${SEED:-42}"
SKIP_PDF="${SKIP_PDF:-0}"
MODEL_PATH="${MODEL_PATH:-openai/gpt-oss-20b}"
OUTDIR="outputs/test_${N}papers"
PYTHONPATH="$(pwd)/src"

# Determine provider
if [ -n "${TOGETHER_API_KEY:-}" ]; then
    PROVIDER="together"
else
    PROVIDER="mock"
fi

echo "================================================"
echo "  Pipeline smoke test: n=$N papers"
echo "  Provider:  $PROVIDER"
[ "$PROVIDER" = "together" ] && echo "  Model:     $MODEL_PATH"
[ "$SKIP_PDF" = "1" ] && echo "  PDF:       skipped"
echo "  Output:    $OUTDIR"
echo "================================================"
echo

mkdir -p "$OUTDIR"

# ── Step 1: Export ──────────────────────────────────────────────────────────
echo "[1/4] Exporting $N papers from SQLite..."
PYTHONPATH="$PYTHONPATH" python -m reviewer_sim.ingest.export_review_subset \
    --db-path data/gen_review.db \
    --out-path "$OUTDIR/review_subset.jsonl" \
    --n "$N" \
    --seed "$SEED" \
    --year 2023 \
    --min-review-chars 50 \
    --exclude-decisions "Withdrawn,Desk Reject,Invite to Workshop"
echo "  Exported to $OUTDIR/review_subset.jsonl"
echo

# ── Step 2: Extract PDFs ────────────────────────────────────────────────────
if [ "$SKIP_PDF" = "1" ]; then
    echo "[2/4] Skipping PDF extraction (SKIP_PDF=1)"
    GENERATION_INPUT="$OUTDIR/review_subset.jsonl"
else
    echo "[2/4] Extracting PDF content (sections_optimized, 10k tokens)..."
    PYTHONPATH="$PYTHONPATH" python -m reviewer_sim.ingest.extract_pdf_content \
        --input "$OUTDIR/review_subset.jsonl" \
        --output "$OUTDIR/review_subset_with_pdf.jsonl" \
        --mode sections_optimized \
        --max-tokens 10000 \
        --cache data/pdf_cache
    echo "  Extracted to $OUTDIR/review_subset_with_pdf.jsonl"
    GENERATION_INPUT="$OUTDIR/review_subset_with_pdf.jsonl"
fi
echo

# ── Step 3: Generate reviews ────────────────────────────────────────────────
echo "[3/4] Generating reviews (provider=$PROVIDER)..."
GENERATION_OUTPUT="$OUTDIR/results.jsonl"

if [ "$PROVIDER" = "together" ]; then
    PYTHONPATH="$PYTHONPATH" \
    MODEL_PROVIDER=together \
    MODEL_PATH="$MODEL_PATH" \
    TOGETHER_API_KEY="$TOGETHER_API_KEY" \
    INPUT_JSONL="$GENERATION_INPUT" \
    OUTPUT_JSONL="$GENERATION_OUTPUT" \
    python -m reviewer_sim.run
else
    PYTHONPATH="$PYTHONPATH" \
    MODEL_PROVIDER=mock \
    INPUT_JSONL="$GENERATION_INPUT" \
    OUTPUT_JSONL="$GENERATION_OUTPUT" \
    python -m reviewer_sim.run
fi
echo "  Results written to $GENERATION_OUTPUT"
echo

# ── Step 4: Summarize ───────────────────────────────────────────────────────
echo "[4/4] Summary:"
echo "──────────────────────────────────────────────"
PYTHONPATH="$PYTHONPATH" python scripts/summarize_results.py "$GENERATION_OUTPUT"
echo "──────────────────────────────────────────────"
echo
echo "Done. Full results: $GENERATION_OUTPUT"
