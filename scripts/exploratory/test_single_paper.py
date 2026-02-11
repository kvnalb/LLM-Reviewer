#!/usr/bin/env python3
"""Test a single paper to see the API error message."""

import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from reviewer_sim.generate.providers import get_generator
from reviewer_sim.utils.config import load_model_config

def main():
    # Load one example from the subset
    subset_path = Path("outputs/review_subset.jsonl")
    if not subset_path.exists():
        print(f"Error: {subset_path} not found. Run 'make export' first.")
        sys.exit(1)
    
    with open(subset_path, "r") as f:
        # Get first example
        example = json.loads(f.readline())
    
    print(f"Testing with paper_id: {example['paper_id']}")
    print(f"Title: {example['title'][:80]}...")
    print(f"Abstract length: {len(example['abstract'])} chars")
    print()
    
    # Set up environment
    os.environ["MODEL_PROVIDER"] = "together"
    os.environ["MODEL_PATH"] = "mistralai/Mistral-7B-Instruct-v0.3"
    
    config = load_model_config()
    generator = get_generator(config)
    
    print("Calling API...")
    result = generator.generate(example)
    
    print("\nResult:")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
