"""Run the benchmark: load data, extract, score, report.

Usage:
    python -m benchmarks.run [OPTIONS]

Examples:
    python -m benchmarks.run                          # test split, default data dir
    python -m benchmarks.run --split validation       # dev loop
    python -m benchmarks.run --limit 50 --split validation  # quick dev check
    python -m benchmarks.run --json --output results.json   # machine-readable
    python -m benchmarks.run --data-dir /path/to/hf_dataset --split test

Environment:
    BENCH_DATA_DIR  Override the default data directory
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from pathlib import Path

from benchmarks.adapter import refmarkers_to_citations
from benchmarks.datasets import get_data_dir, load_dataset
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
) -> tuple[BenchmarkResult, dict]:
    """Run the full benchmark pipeline.

    Args:
        data_dir: Path to the benchmark dataset directory.
        limit: Process at most this many documents (for quick testing).
        split: Which split to evaluate (train/validation/test).

    Returns:
        (BenchmarkResult, timing_stats) tuple.
    """
    t_load_start = time.perf_counter()
    dataset = load_dataset(data_dir, split=split)
    t_load = time.perf_counter() - t_load_start

    t_init_start = time.perf_counter()
    extractor = RefExtractor()
    t_init = time.perf_counter() - t_init_start

    result = BenchmarkResult()
    processed = 0
    errors = 0
    doc_times: list[float] = []
    doc_chars: list[int] = []

    t_extract_start = time.perf_counter()

    for doc in dataset.documents:
        if limit is not None and processed >= limit:
            break

        gold_ann = dataset.annotations.get(doc.doc_id)
        if not gold_ann:
            continue

        # Filter gold to law + case only (refex doesn't extract literature)
        gold_citations = [c for c in gold_ann.citations if c.type in ("law", "case")]

        try:
            t_doc_start = time.perf_counter()
            # Call extractors directly to avoid replace_content overlap errors
            markers = []
            content = extractor.remove_markers(doc.text)
            if extractor.do_law_refs:
                markers.extend(extractor.extract_law_ref_markers(content, False))
            if extractor.do_case_refs:
                markers.extend(extractor.extract_case_ref_markers(content))
            pred_citations = refmarkers_to_citations(markers)
            t_doc = time.perf_counter() - t_doc_start
            doc_times.append(t_doc)
            doc_chars.append(len(doc.text))
        except Exception:
            logger.exception("Failed to extract from %s", doc.doc_id)
            errors += 1
            continue

        score_document(gold_citations, pred_citations, result)
        processed += 1

    t_extract = time.perf_counter() - t_extract_start

    # Compute timing stats
    timing: dict = {
        "load_seconds": round(t_load, 3),
        "init_seconds": round(t_init, 3),
        "extract_seconds": round(t_extract, 3),
        "total_seconds": round(t_load + t_init + t_extract, 3),
        "docs_processed": processed,
        "docs_errored": errors,
    }
    if doc_times:
        timing["per_doc_ms"] = {
            "mean": round(statistics.mean(doc_times) * 1000, 1),
            "median": round(statistics.median(doc_times) * 1000, 1),
            "p95": round(sorted(doc_times)[int(0.95 * len(doc_times))] * 1000, 1),
            "p99": round(sorted(doc_times)[min(int(0.99 * len(doc_times)), len(doc_times) - 1)] * 1000, 1),
            "max": round(max(doc_times) * 1000, 1),
        }
        total_chars = sum(doc_chars)
        timing["throughput"] = {
            "docs_per_second": round(processed / t_extract, 1),
            "chars_per_second": round(total_chars / t_extract, 0),
            "total_chars": total_chars,
        }

    result.total_docs = processed
    return result, timing


def format_summary(result: BenchmarkResult, timing: dict, split: str, data_dir: Path) -> str:
    """Format a human-readable summary with metrics and timing."""
    lines = [
        f"Dataset: {data_dir}",
        f"Split: {split}",
        "",
        result.summary(),
        "",
        "--- Speed ---",
        f"  Data load:    {timing['load_seconds']:.1f}s",
        f"  Extractor init: {timing['init_seconds']:.3f}s",
        f"  Extraction:   {timing['extract_seconds']:.1f}s",
        f"  Total:        {timing['total_seconds']:.1f}s",
        f"  Errors:       {timing['docs_errored']}",
    ]
    if "per_doc_ms" in timing:
        pd = timing["per_doc_ms"]
        tp = timing["throughput"]
        lines.extend([
            "",
            "--- Per-document timing ---",
            f"  Mean:   {pd['mean']:.1f} ms",
            f"  Median: {pd['median']:.1f} ms",
            f"  P95:    {pd['p95']:.1f} ms",
            f"  P99:    {pd['p99']:.1f} ms",
            f"  Max:    {pd['max']:.1f} ms",
            "",
            "--- Throughput ---",
            f"  {tp['docs_per_second']:.1f} docs/s",
            f"  {tp['chars_per_second']:.0f} chars/s",
        ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark the citation extractor against gold annotations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --split validation              # dev loop\n"
            "  %(prog)s --split validation --limit 50   # quick check\n"
            "  %(prog)s --split test                    # final eval\n"
            "  %(prog)s --json -o results.json          # machine output\n"
        ),
    )
    parser.add_argument(
        "-d", "--data-dir",
        type=Path,
        default=None,
        help=f"Path to HF dataset or JSONL directory (default: {get_data_dir()})",
    )
    parser.add_argument(
        "-s", "--split",
        choices=["train", "validation", "test"],
        default="test",
        help="Which split to evaluate (default: test)",
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process at most N documents",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        metavar="FILE",
        help="Write output to file instead of stdout",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show per-document extraction errors",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    data_dir = args.data_dir or get_data_dir()

    result, timing = run_benchmark(data_dir=data_dir, limit=args.limit, split=args.split)

    if args.json:
        out = result.to_dict()
        out["timing"] = timing
        out["split"] = args.split
        out["data_dir"] = str(data_dir)
        text = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    else:
        text = format_summary(result, timing, args.split, data_dir) + "\n"

    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
