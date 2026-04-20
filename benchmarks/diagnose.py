"""Diagnostic analysis of benchmark errors.

Usage:
    python -m benchmarks.diagnose [--data-dir PATH] [--split test] [--limit N]
"""

from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from pathlib import Path

os.environ.setdefault("HF_DATASETS_CACHE", "/tmp/hf-cache")
os.environ.setdefault("HF_HOME", "/tmp/hf-home")

from benchmarks.adapter import refmarkers_to_citations
from benchmarks.datasets import load_dataset

from refex.extractor import RefExtractor


def diagnose(data_dir=None, split="validation", limit=None):
    dataset = load_dataset(data_dir, split=split)
    extractor = RefExtractor()

    # Counters
    fn_by_type = Counter()  # False negatives by type
    fp_by_type = Counter()  # False positives by type
    fn_examples = {"law": [], "case": []}
    fp_examples = {"law": [], "case": []}
    missing_books = Counter()  # Law books not found
    gold_books = Counter()
    pred_books = Counter()
    fn_file_number_patterns = []
    overlap_mismatches = []
    errors = 0

    processed = 0
    for doc in dataset.documents:
        if limit and processed >= limit:
            break
        gold_ann = dataset.annotations.get(doc.doc_id)
        if not gold_ann:
            continue

        gold_cits = [c for c in gold_ann.citations if c.type in ("law", "case")]

        try:
            content = extractor.remove_markers(doc.text)
            markers = []
            if extractor.do_law_refs:
                markers.extend(extractor.extract_law_ref_markers(content, False))
            if extractor.do_case_refs:
                markers.extend(extractor.extract_case_ref_markers(content))
            pred_cits = refmarkers_to_citations(markers, content)
        except Exception:
            errors += 1
            continue

        gold_spans = {(c.span.start, c.span.end): c for c in gold_cits}
        pred_spans = {(c.span.start, c.span.end): c for c in pred_cits}

        # False negatives (gold not in predicted)
        for key, gc in gold_spans.items():
            if key not in pred_spans:
                fn_by_type[gc.type] += 1
                if gc.type == "law" and gc.book:
                    missing_books[gc.book] += 1
                if gc.type == "law":
                    gold_books[gc.book or "None"] += 1
                if gc.type in fn_examples and len(fn_examples[gc.type]) < 30:
                    fn_examples[gc.type].append(
                        {
                            "doc_id": doc.doc_id,
                            "text": gc.span.text,
                            "book": gc.book,
                            "court": gc.court,
                            "file_number": gc.file_number,
                        }
                    )
                if gc.type == "case" and gc.file_number:
                    fn_file_number_patterns.append(gc.file_number)

        # False positives (predicted not in gold)
        for key, pc in pred_spans.items():
            if key not in gold_spans:
                fp_by_type[pc.type] += 1
                if pc.type == "law" and pc.book:
                    pred_books[pc.book] += 1
                if pc.type in fp_examples and len(fp_examples[pc.type]) < 20:
                    fp_examples[pc.type].append(
                        {
                            "doc_id": doc.doc_id,
                            "text": pc.span.text,
                            "book": pc.book,
                            "court": pc.court,
                            "file_number": pc.file_number,
                        }
                    )

        # Overlap-only matches (partial span match)
        for gkey, gc in gold_spans.items():
            if gkey in pred_spans:
                continue
            for pkey, pc in pred_spans.items():
                if pkey in gold_spans:
                    continue
                gs, ge = gkey
                ps, pe = pkey
                if gs < pe and ps < ge and gc.type == pc.type:
                    if len(overlap_mismatches) < 30:
                        overlap_mismatches.append(
                            {
                                "doc_id": doc.doc_id,
                                "type": gc.type,
                                "gold_span": gc.span.text,
                                "gold_range": f"{gs}-{ge}",
                                "pred_span": pc.span.text,
                                "pred_range": f"{ps}-{pe}",
                            }
                        )

        processed += 1

    # Report
    print(f"=== Error Diagnosis ({processed} docs, {errors} extraction errors) ===\n")

    print("--- False Negatives by Type ---")
    for t, c in fn_by_type.most_common():
        print(f"  {t}: {c}")

    print("\n--- False Positives by Type ---")
    for t, c in fp_by_type.most_common():
        print(f"  {t}: {c}")

    print("\n--- Top 20 Missing Law Book Codes (FN) ---")
    for book, cnt in missing_books.most_common(20):
        print(f"  {book}: {cnt}")

    print("\n--- Top 20 False Positive Law Books ---")
    for book, cnt in pred_books.most_common(20):
        print(f"  {book}: {cnt}")

    print("\n--- Case FN Examples (first 15) ---")
    for ex in fn_examples["case"][:15]:
        print(f"  [{ex['doc_id'][:30]}] text={ex['text'][:60]!r} court={ex['court']} fn={ex['file_number']}")

    print("\n--- Case FP Examples (first 15) ---")
    for ex in fp_examples["case"][:15]:
        print(f"  [{ex['doc_id'][:30]}] text={ex['text'][:60]!r} court={ex['court']} fn={ex['file_number']}")

    print("\n--- Law FN Examples (first 15) ---")
    for ex in fn_examples["law"][:15]:
        print(f"  [{ex['doc_id'][:30]}] text={ex['text'][:60]!r} book={ex['book']}")

    print("\n--- Law FP Examples (first 10) ---")
    for ex in fp_examples["law"][:10]:
        print(f"  [{ex['doc_id'][:30]}] text={ex['text'][:60]!r} book={ex['book']}")

    print("\n--- Overlap Mismatches (first 15) ---")
    for m in overlap_mismatches[:15]:
        g = m["gold_span"][:50]
        p = m["pred_span"][:50]
        print(f"  [{m['doc_id'][:30]}] {m['type']}: gold={g!r} ({m['gold_range']}) pred={p!r} ({m['pred_range']})")

    # Analyze case file number patterns
    if fn_file_number_patterns:
        print("\n--- Case FN File Number Pattern Analysis ---")
        has_slash = sum(1 for fn in fn_file_number_patterns if "/" in fn)
        has_dot = sum(1 for fn in fn_file_number_patterns if "." in fn and "/" not in fn)
        has_hyphen = sum(1 for fn in fn_file_number_patterns if "-" in fn and "/" not in fn and "." not in fn)
        reporter_like = sum(1 for fn in fn_file_number_patterns if re.match(r"[A-Z]{2,}", fn))
        print(f"  Total missed case file numbers: {len(fn_file_number_patterns)}")
        print(f"  With /: {has_slash}")
        print(f"  With . only: {has_dot}")
        print(f"  With - only: {has_hyphen}")
        print(f"  Reporter-like (uppercase start): {reporter_like}")
        # Sample
        print(f"  First 20 missed: {fn_file_number_patterns[:20]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument(
        "--split",
        default="validation",
        help="Split to analyze (default: validation; avoid test for development)",
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    diagnose(args.data_dir, args.split, args.limit)
