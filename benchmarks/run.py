"""Run the benchmark: load data, extract, score, report.

Usage:
    python -m benchmarks.run [--data-dir PATH] [--limit N] [--json]

Environment:
    BENCH_DATA_DIR  Override the default data directory
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from benchmarks.adapter import refmarkers_to_citations
from benchmarks.datasets import load_dataset
from benchmarks.metrics import BenchmarkResult, score_document
from refex.extractor import RefExtractor

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    level=logging.WARNING,
)
logger = logging.getLogger(__name__)


def run_benchmark(
    data_dir: Path | None = None,
    limit: int | None = None,
    split: str = "test",
) -> BenchmarkResult:
    """Run the full benchmark pipeline.

    Args:
        data_dir: Path to the benchmark dataset directory.
        limit: Process at most this many documents (for quick testing).
        split: Which split to evaluate (train/validation/test).

    Returns:
        BenchmarkResult with all metrics.
    """
    dataset = load_dataset(data_dir, split=split)
    extractor = RefExtractor()

    result = BenchmarkResult()
    processed = 0
    errors = 0

    for doc in dataset.documents:
        if limit is not None and processed >= limit:
            break

        gold_ann = dataset.annotations.get(doc.doc_id)
        if not gold_ann:
            continue

        # Filter gold to law + case only (refex doesn't extract literature)
        gold_citations = [c for c in gold_ann.citations if c.type in ("law", "case")]

        try:
            # Call extractors directly to avoid replace_content overlap errors
            markers = []
            content = extractor.remove_markers(doc.text)
            if extractor.do_law_refs:
                markers.extend(extractor.extract_law_ref_markers(content, False))
            if extractor.do_case_refs:
                markers.extend(extractor.extract_case_ref_markers(content))
            pred_citations = refmarkers_to_citations(markers)
        except Exception:
            logger.exception("Failed to extract from %s", doc.doc_id)
            errors += 1
            continue

        score_document(gold_citations, pred_citations, result)
        processed += 1

    result.total_docs = processed
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run benchmark against gold annotations")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Path to dataset directory (default: auto-resolved from BENCH_DATA_DIR or sibling project)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N documents (for quick testing)",
    )
    parser.add_argument(
        "--split",
        type=str,
        default="test",
        help="Which split to evaluate (train/validation/test, default: test)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of human-readable summary",
    )
    args = parser.parse_args()

    t0 = time.time()
    result = run_benchmark(data_dir=args.data_dir, limit=args.limit, split=args.split)
    elapsed = time.time() - t0

    if args.json:
        out = result.to_dict()
        out["elapsed_seconds"] = round(elapsed, 2)
        json.dump(out, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(result.summary())
        print(f"\nCompleted in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
