#!/bin/bash

###############################################################################
# Test Pipeline with 5 Papers
#
# Complete end-to-end test of the full pipeline:
# 1. Export 5 papers from database
# 2. Extract PDF content (10k tokens, optimized for review)
# 3. Generate reviews with Together AI
# 4. Verify results and copy to test_verification folder
#
# Usage:
#   bash scripts/test_pipeline_5papers.sh
#
# Environment variables (optional):
#   MODEL_PATH              (default: meta-llama/Llama-3-8b-chat-hf)
#   TOGETHER_API_KEY        (required for Together AI)
#   OUTPUT_DIR              (default: outputs/test_5papers)
#
###############################################################################

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

# Configuration
export PYTHONPATH="$SCRIPT_DIR/src"
MODEL_PATH="${MODEL_PATH:-openai/gpt-oss-20b}"
OUTPUT_DIR="${OUTPUT_DIR:-outputs/test_5papers}"
TEST_VERIFY_DIR="outputs/test_verification_5papers"
EXPORT_FILE="$OUTPUT_DIR/review_subset_5.jsonl"
PDF_FILE="$OUTPUT_DIR/review_subset_5_with_pdf.jsonl"
RESULTS_FILE="$OUTPUT_DIR/results_5.jsonl"

echo ""
echo "================================"
echo "🧪 Full Pipeline Test (5 Papers)"
echo "================================"
echo ""
echo "Configuration:"
echo "  Model: $MODEL_PATH"
echo "  Output dir: $OUTPUT_DIR"
echo "  Test verify dir: $TEST_VERIFY_DIR"
echo ""

# Check API key
if [ -z "$TOGETHER_API_KEY" ]; then
    echo "❌ ERROR: TOGETHER_API_KEY environment variable is required"
    echo "   Set it with: export TOGETHER_API_KEY='your-key-here'"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"
mkdir -p "$TEST_VERIFY_DIR"

# Step 1: Export 5 papers
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Export 5 papers"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

PYTHONPATH="$PYTHONPATH" python -m reviewer_sim.ingest.export_review_subset \
    --db-path data/gen_review.db \
    --out-path "$EXPORT_FILE" \
    --n 5 \
    --seed 42 \
    --min-review-chars 50 \
    --year 2023 \
    --exclude-decisions "Withdrawn,Desk Reject,Invite to Workshop"

export_lines=$(wc -l < "$EXPORT_FILE")
echo ""
echo "✅ Exported $export_lines papers to: $EXPORT_FILE"
echo "   Sample:"
head -1 "$EXPORT_FILE" | python -m json.tool | head -20

# Step 2: Extract PDF content
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Extract PDF content (10k tokens, optimized)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

PYTHONPATH="$PYTHONPATH" python -m reviewer_sim.ingest.extract_pdf_content \
    --input "$EXPORT_FILE" \
    --output "$PDF_FILE" \
    --mode sections_optimized \
    --max-tokens 10000 \
    --cache data/pdf_cache

pdf_lines=$(wc -l < "$PDF_FILE")
echo ""
echo "✅ Extracted PDFs for $pdf_lines papers to: $PDF_FILE"
echo ""
echo "   Token counts:"
python << 'EOF'
import json
import sys
with open(sys.argv[1]) as f:
    for i, line in enumerate(f, 1):
        p = json.loads(line)
        tokens = p['pdf_content']['token_count']
        success = p['pdf_content']['extraction_metadata']['success']
        source = p['pdf_content']['extraction_metadata'].get('source', 'unknown')
        status = "✓" if success else "✗"
        print(f"   {status} Paper {i}: {tokens:5d} tokens (source: {source})")
EOF
"$PDF_FILE"

# Step 3: Generate reviews with Together AI
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Generate reviews with Together AI"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Model: $MODEL_PATH"
echo "Processing..."
echo ""

PYTHONPATH="$PYTHONPATH" \
    MODEL_PROVIDER=together \
    MODEL_PATH="$MODEL_PATH" \
    TOGETHER_API_KEY="$TOGETHER_API_KEY" \
    INPUT_JSONL="$PDF_FILE" \
    OUTPUT_JSONL="$RESULTS_FILE" \
    python -m reviewer_sim.run

results_lines=$(wc -l < "$RESULTS_FILE")
echo ""
echo "✅ Generated reviews for $results_lines papers to: $RESULTS_FILE"

# Step 4: Show results
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4: Review Results Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python << 'EOF'
import json
import sys
from statistics import mean

results_file = sys.argv[1]

ratings = []
confidences = []
correctness = []
tech_novelty = []
emp_novelty = []
nmae_values = []
decision_agrees = []

with open(results_file) as f:
    for i, line in enumerate(f, 1):
        result = json.loads(line)
        gen = result['generated_review']
        metrics = result.get('metrics', {})

        ratings.append(gen['rating'])
        confidences.append(gen['confidence'])
        correctness.append(gen['correctness'])
        tech_novelty.append(gen['technical_novelty_and_significance'])
        emp_novelty.append(gen['empirical_novelty_and_significance'])

        if metrics.get('nmae') is not None:
            nmae_values.append(metrics['nmae'])
        if metrics.get('decision_agree') is not None:
            decision_agrees.append(metrics['decision_agree'])

        print(f"Paper {i}:")
        print(f"  Rating: {gen['rating']}/10 (confidence: {gen['confidence']}/5)")
        print(f"  Scores: correctness={gen['correctness']}/4, "
              f"tech_novelty={gen['technical_novelty_and_significance']}/4, "
              f"emp_novelty={gen['empirical_novelty_and_significance']}/4")
        print(f"  NMAE: {metrics.get('nmae', 'N/A'):.3f}" if metrics.get('nmae') else "  NMAE: N/A")
        print(f"  Decision agree: {metrics.get('decision_agree', 'N/A')}")
        print()

print("AGGREGATE STATISTICS:")
print(f"  Avg Rating: {mean(ratings):.2f}/10")
print(f"  Avg Confidence: {mean(confidences):.2f}/5")
print(f"  Avg Correctness: {mean(correctness):.2f}/4")
print(f"  Avg Tech Novelty: {mean(tech_novelty):.2f}/4")
print(f"  Avg Emp Novelty: {mean(emp_novelty):.2f}/4")
if nmae_values:
    print(f"  Avg NMAE: {mean(nmae_values):.3f}")
if decision_agrees:
    agree_pct = sum(decision_agrees) / len(decision_agrees) * 100
    print(f"  Decision Agreement: {agree_pct:.1f}%")
EOF
"$RESULTS_FILE"

# Step 5: Copy to test_verification folder
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 5: Archive test files"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cp "$EXPORT_FILE" "$TEST_VERIFY_DIR/"
cp "$PDF_FILE" "$TEST_VERIFY_DIR/"
cp "$RESULTS_FILE" "$TEST_VERIFY_DIR/"
cp -r data/pdf_cache "$TEST_VERIFY_DIR/pdf_cache_5papers" 2>/dev/null || true

echo "✅ Test files archived to: $TEST_VERIFY_DIR"
echo ""
echo "Files for manual inspection:"
ls -lh "$TEST_VERIFY_DIR"/ | grep -E "\.(jsonl|db)$"
echo ""

# Step 6: Verification checklist
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "VERIFICATION CHECKLIST"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check export
export_ok=$(python -c "
import json
count = 0
with open('$EXPORT_FILE') as f:
    for line in f:
        p = json.loads(line)
        if 'pdf_url' in p and 'title' in p and 'abstract' in p:
            count += 1
print('✓' if count == 5 else '✗', count)
")
echo "  [$export_ok] 5 papers exported with pdf_url, title, abstract"

# Check PDF extraction
pdf_ok=$(python -c "
import json
count = 0
with open('$PDF_FILE') as f:
    for line in f:
        p = json.loads(line)
        if p.get('pdf_content', {}).get('extraction_metadata', {}).get('success'):
            count += 1
print('✓' if count == 5 else '✗', count)
")
echo "  [$pdf_ok] 5 PDFs extracted successfully"

# Check token counts
echo -n "  [✓] Token counts (should be 3k-10k): "
python -c "
import json
with open('$PDF_FILE') as f:
    for line in f:
        p = json.loads(line)
        tokens = p['pdf_content']['token_count']
        print(f'{tokens}', end=' ')
print()
"

# Check review generation
results_ok=$(python -c "
import json
count = 0
with open('$RESULTS_FILE') as f:
    for line in f:
        r = json.loads(line)
        gen = r.get('generated_review', {})
        if all(k in gen for k in ['rating', 'confidence', 'correctness']):
            count += 1
print('✓' if count == 5 else '✗', count)
")
echo "  [$results_ok] 5 reviews generated with all scores"

# Check metrics
metrics_ok=$(python -c "
import json
count = 0
with open('$RESULTS_FILE') as f:
    for line in f:
        r = json.loads(line)
        if 'nmae' in r.get('metrics', {}):
            count += 1
print('✓' if count == 5 else '✗', count)
")
echo "  [$metrics_ok] 5 results have NMAE metrics"

echo ""
echo "✅ TEST PIPELINE COMPLETE"
echo ""
echo "Next steps:"
echo "  1. Review the test files in: $TEST_VERIFY_DIR"
echo "  2. Inspect JSON files: head -1 $TEST_VERIFY_DIR/*.jsonl | python -m json.tool"
echo "  3. Run full pipeline with: make full-pipeline"
echo ""
