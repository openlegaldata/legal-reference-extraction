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
from benchmarks.datasets import Citation as BenchmarkCitation
from benchmarks.datasets import Relation as BenchmarkRelation
from benchmarks.datasets import get_data_dir, load_dataset
from benchmarks.metrics import BenchmarkResult, score_document, score_relations

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    level=logging.WARNING,
)
logger = logging.getLogger(__name__)


def _crf_citation_to_benchmark(cit) -> BenchmarkCitation:
    """Convert a refex CRF Citation to the benchmark's Citation format."""
    from benchmarks.datasets import Span as BSpan

    span = BSpan(start=cit.span.start, end=cit.span.end, text=cit.span.text)
    kwargs = {"id": cit.id, "type": cit.type, "kind": "full", "span": span}
    if cit.type == "law":
        kwargs["book"] = getattr(cit, "book", None)
        kwargs["number"] = getattr(cit, "number", None)
    elif cit.type == "case":
        kwargs["court"] = getattr(cit, "court", None)
        kwargs["file_number"] = getattr(cit, "file_number", None)
        kwargs["date"] = getattr(cit, "date", None)
    return BenchmarkCitation(**kwargs)


def _build_extract_fn(engine: str):
    """Build a `text -> list[Citation]` function for the chosen engine.

    Returns benchmark-format Citations (benchmarks.datasets.Citation).
    """
    if engine == "regex":
        from refex.extractor import RefExtractor

        extractor = RefExtractor()

        def extract(text: str):
            markers = []
            content = extractor.remove_markers(text)
            if extractor.do_law_refs:
                markers.extend(extractor.extract_law_ref_markers(content, False))
            if extractor.do_case_refs:
                markers.extend(extractor.extract_case_ref_markers(content))
            return refmarkers_to_citations(markers, content)

        return extract

    if engine == "crf":
        from refex.engines.crf import CRFExtractor

        crf = CRFExtractor()

        def extract(text: str):
            cits, _ = crf.extract(text)
            return [_crf_citation_to_benchmark(c) for c in cits]

        return extract

    if engine == "regex+crf":
        from refex.engines.crf import CRFExtractor
        from refex.extractor import RefExtractor

        regex_ext = RefExtractor()
        crf = CRFExtractor()

        def extract(text: str):
            content = regex_ext.remove_markers(text)
            markers = []
            if regex_ext.do_law_refs:
                markers.extend(regex_ext.extract_law_ref_markers(content, False))
            if regex_ext.do_case_refs:
                markers.extend(regex_ext.extract_case_ref_markers(content))
            regex_cits = refmarkers_to_citations(markers, content)

            crf_cits_raw, _ = crf.extract(content)
            crf_cits = [_crf_citation_to_benchmark(c) for c in crf_cits_raw]

            # Merge: drop CRF citations that overlap with regex (regex = higher precision)
            regex_spans = [(c.span.start, c.span.end) for c in regex_cits]
            merged = list(regex_cits)
            for c in crf_cits:
                cs, ce = c.span.start, c.span.end
                overlaps = any(cs < re_end and re_start < ce for re_start, re_end in regex_spans)
                if not overlaps:
                    merged.append(c)
            return merged

        return extract

    if engine == "transformer":
        import os

        from refex.engines.transformer import TransformerExtractor

        model = os.environ.get("REFEX_TRANSFORMER_MODEL")
        device = os.environ.get("REFEX_TRANSFORMER_DEVICE")
        kwargs = {}
        if model:
            kwargs["model"] = model
        if device:
            kwargs["device"] = device
        tx = TransformerExtractor(**kwargs)

        def extract(text: str):
            cits, _ = tx.extract(text)
            return [_crf_citation_to_benchmark(c) for c in cits]

        return extract

    if engine == "regex+transformer":
        import os

        from refex.engines.transformer import TransformerExtractor
        from refex.extractor import RefExtractor

        regex_ext = RefExtractor()
        model = os.environ.get("REFEX_TRANSFORMER_MODEL")
        device = os.environ.get("REFEX_TRANSFORMER_DEVICE")
        kwargs = {}
        if model:
            kwargs["model"] = model
        if device:
            kwargs["device"] = device
        tx = TransformerExtractor(**kwargs)

        def extract(text: str):
            content = regex_ext.remove_markers(text)
            markers = []
            if regex_ext.do_law_refs:
                markers.extend(regex_ext.extract_law_ref_markers(content, False))
            if regex_ext.do_case_refs:
                markers.extend(regex_ext.extract_case_ref_markers(content))
            regex_cits = refmarkers_to_citations(markers, content)

            tx_cits_raw, _ = tx.extract(content)
            tx_cits = [_crf_citation_to_benchmark(c) for c in tx_cits_raw]

            # Merge: drop transformer citations that overlap with regex
            regex_spans = [(c.span.start, c.span.end) for c in regex_cits]
            merged = list(regex_cits)
            for c in tx_cits:
                cs, ce = c.span.start, c.span.end
                overlaps = any(cs < re_end and re_start < ce for re_start, re_end in regex_spans)
                if not overlaps:
                    merged.append(c)
            return merged

        return extract

    msg = f"Unknown engine: {engine!r}. Expected one of: regex, crf, regex+crf, transformer, regex+transformer"
    raise ValueError(msg)


def run_benchmark(
    data_dir: Path | None = None,
    limit: int | None = None,
    split: str = "test",
    engine: str = "regex",
    profile: bool = False,
    profile_output: Path | None = None,
) -> tuple[BenchmarkResult, dict]:
    """Run the full benchmark pipeline.

    Args:
        data_dir: Path to the benchmark dataset directory.
        limit: Process at most this many documents (for quick testing).
        split: Which split to evaluate (train/validation/test).
        engine: Which engine to use. One of:
            - "regex" (default): legacy regex extractors with span optimizations
            - "crf": CRF-only
            - "regex+crf": both, merged via orchestrator
        profile: If True, wrap the extraction loop in a cProfile context
            and print the top-20 callers by cumulative time on stderr
            (and to ``profile_output`` when provided). Off by default.
        profile_output: Optional path to write the full cProfile stats
            (human-readable text). Ignored when ``profile`` is False.

    Returns:
        (BenchmarkResult, timing_stats) tuple.
    """
    t_load_start = time.perf_counter()
    dataset = load_dataset(data_dir, split=split)
    t_load = time.perf_counter() - t_load_start

    t_init_start = time.perf_counter()
    extract_fn = _build_extract_fn(engine)
    t_init = time.perf_counter() - t_init_start
    logger.info("Using engine: %s (init %.3fs)", engine, t_init)

    result = BenchmarkResult()
    processed = 0
    errors = 0
    doc_times: list[float] = []
    doc_chars: list[int] = []

    t_extract_start = time.perf_counter()

    total_docs = len(dataset.documents) if limit is None else min(limit, len(dataset.documents))

    profiler = None
    if profile:
        import cProfile

        profiler = cProfile.Profile()
        profiler.enable()

    for doc in dataset.documents:
        if limit is not None and processed >= limit:
            break

        gold_ann = dataset.annotations.get(doc.doc_id)
        if not gold_ann:
            continue

        # Filter gold to law + case only (refex doesn't extract literature)
        gold_citations = [c for c in gold_ann.citations if c.type in ("law", "case")]
        gold_relations: list[BenchmarkRelation] = list(gold_ann.relations)

        try:
            t_doc_start = time.perf_counter()
            pred = extract_fn(doc.text)
            t_doc = time.perf_counter() - t_doc_start
            doc_times.append(t_doc)
            doc_chars.append(len(doc.text))
        except Exception:
            logger.exception("Failed to extract from %s", doc.doc_id)
            errors += 1
            continue

        # A2d — extract_fn may return either a plain ``list[Citation]``
        # (legacy) or a ``(citations, relations)`` tuple (for engines that
        # emit relations).  Normalise here so the scorer sees both.
        if isinstance(pred, tuple):
            pred_citations, pred_relations = pred
        else:
            pred_citations = pred
            pred_relations = []

        score_document(gold_citations, pred_citations, result)
        score_relations(gold_citations, gold_relations, pred_citations, pred_relations, result)
        processed += 1

        # Progress logging
        if processed % 100 == 0 or t_doc > 1.0:
            elapsed = time.perf_counter() - t_extract_start
            rate = processed / elapsed if elapsed > 0 else 0
            slow_tag = f" [SLOW {t_doc * 1000:.0f}ms len={len(doc.text)}]" if t_doc > 1.0 else ""
            print(
                f"\r  {processed}/{total_docs} docs  ({rate:.0f} docs/s, {elapsed:.1f}s elapsed){slow_tag}",
                end="",
                flush=True,
                file=sys.stderr,
            )

    if processed > 100:
        print(file=sys.stderr)  # newline after progress

    t_extract = time.perf_counter() - t_extract_start

    if profiler is not None:
        import io
        import pstats

        profiler.disable()
        buf = io.StringIO()
        stats = pstats.Stats(profiler, stream=buf).sort_stats("cumulative")
        stats.print_stats(20)
        top = buf.getvalue()
        sys.stderr.write("\n=== cProfile (top 20 by cumulative time) ===\n")
        sys.stderr.write(top)
        if profile_output is not None:
            profile_output.parent.mkdir(parents=True, exist_ok=True)
            with profile_output.open("w", encoding="utf-8") as f:
                full = io.StringIO()
                pstats.Stats(profiler, stream=full).sort_stats("cumulative").print_stats(60)
                pstats.Stats(profiler, stream=full).sort_stats("tottime").print_stats(60)
                f.write(full.getvalue())
            sys.stderr.write(f"Full profile written to {profile_output}\n")

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


def format_summary(result: BenchmarkResult, timing: dict, split: str, data_dir: Path, engine: str = "regex") -> str:
    """Format a human-readable summary with metrics and timing."""
    lines = [
        f"Dataset: {data_dir}",
        f"Split: {split}",
        f"Engine: {engine}",
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
        lines.extend(
            [
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
            ]
        )
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
        "-d",
        "--data-dir",
        type=Path,
        default=None,
        help=f"Path to HF dataset or JSONL directory (default: {get_data_dir()})",
    )
    parser.add_argument(
        "-s",
        "--split",
        choices=["train", "validation", "test"],
        default="test",
        help="Which split to evaluate (default: test)",
    )
    parser.add_argument(
        "-n",
        "--limit",
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
        "-o",
        "--output",
        type=Path,
        default=None,
        metavar="FILE",
        help="Write output to file instead of stdout",
    )
    parser.add_argument(
        "-e",
        "--engine",
        choices=["regex", "crf", "regex+crf", "transformer", "regex+transformer"],
        default="regex",
        help="Which extraction engine to use (default: regex)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show per-document extraction errors",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Wrap the extract loop in cProfile; print top-20 to stderr on exit.",
    )
    parser.add_argument(
        "--profile-output",
        type=Path,
        default=None,
        metavar="FILE",
        help="With --profile, also write the full cProfile stats (top 60 by cumulative + tottime) to this file.",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    data_dir = args.data_dir or get_data_dir()

    result, timing = run_benchmark(
        data_dir=data_dir,
        limit=args.limit,
        split=args.split,
        engine=args.engine,
        profile=args.profile,
        profile_output=args.profile_output,
    )

    if args.json:
        out = result.to_dict()
        out["timing"] = timing
        out["split"] = args.split
        out["engine"] = args.engine
        out["data_dir"] = str(data_dir)
        text = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    else:
        text = format_summary(result, timing, args.split, data_dir, args.engine) + "\n"

    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
