"""Validate a benchmark dataset against quality checks.

Runs integrity checks on documents and annotations to catch data errors
before they silently corrupt benchmark results.

Usage:
    python -m benchmarks.validate [OPTIONS]

Examples:
    python -m benchmarks.validate                         # test split, default data dir
    python -m benchmarks.validate --split validation      # check dev split
    python -m benchmarks.validate --data-dir /path/to/data --split train
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from benchmarks.datasets import BenchmarkDataset, get_data_dir, load_dataset

# --- Controlled vocabularies ---

VALID_CITATION_TYPES = {"law", "case"}
VALID_CITATION_KINDS = {"full", "short", "id", "ibid", "supra", "aao", "ebenda"}
VALID_RELATION_TYPES = {"ivm", "vgl", "aao", "ebenda", "siehe", "resolves_to", "parallel"}
VALID_STRUCTURE_KEYS = {
    "buch",
    "teil",
    "abschnitt",
    "unterabschnitt",
    "titel",
    "untertitel",
    "kapitel",
    "unterkapitel",
    "absatz",
    "satz",
    "halbsatz",
    "nummer",
    "buchstabe",
    "alternative",
    "variante",
}


def validate_dataset(data_dir: Path, split: str = "test") -> list[str]:
    """Run all checks, return list of error strings. Empty = all pass."""
    dataset = load_dataset(data_dir, split=split)

    errors: list[str] = []
    warnings: list[str] = []

    _check_doc_id_uniqueness(dataset, errors)
    _check_join_integrity(dataset, errors, warnings)
    _check_citation_id_uniqueness(dataset, errors)
    _check_span_integrity(dataset, errors)
    _check_controlled_vocabulary(dataset, errors)
    _check_resolves_to_integrity(dataset, errors)
    _check_relation_integrity(dataset, errors)

    # Print warnings to stderr (they are not errors)
    for w in warnings:
        print(f"  WARN: {w}", file=sys.stderr)

    return errors


def _check_doc_id_uniqueness(dataset: BenchmarkDataset, errors: list[str]) -> None:
    """doc_ids must be unique globally across all documents."""
    seen: dict[str, int] = {}
    for i, doc in enumerate(dataset.documents):
        if doc.doc_id in seen:
            errors.append(f"Duplicate doc_id {doc.doc_id!r}: appears at document indices {seen[doc.doc_id]} and {i}")
        else:
            seen[doc.doc_id] = i


def _check_join_integrity(dataset: BenchmarkDataset, errors: list[str], warnings: list[str]) -> None:
    """Every annotation doc_id must have a document; every document should have annotations."""
    doc_ids = {d.doc_id for d in dataset.documents}

    # Annotations referencing missing documents
    for ann_doc_id in dataset.annotations:
        if ann_doc_id not in doc_ids:
            errors.append(f"Annotation doc_id {ann_doc_id!r} has no matching document")

    # Documents without annotations (warning, not error)
    for doc in dataset.documents:
        if doc.doc_id not in dataset.annotations:
            warnings.append(f"Document {doc.doc_id!r} has no annotations")


def _check_citation_id_uniqueness(dataset: BenchmarkDataset, errors: list[str]) -> None:
    """Citation IDs must be unique within each document."""
    for doc_id, ann in dataset.annotations.items():
        seen: set[str] = set()
        for cit in ann.citations:
            if cit.id in seen:
                errors.append(f"[{doc_id}] Duplicate citation ID {cit.id!r}")
            seen.add(cit.id)


def _check_span_integrity(dataset: BenchmarkDataset, errors: list[str]) -> None:
    """For each citation, doc.text[span.start:span.end] must equal span.text."""
    doc_texts = {d.doc_id: d.text for d in dataset.documents}

    for doc_id, ann in dataset.annotations.items():
        text = doc_texts.get(doc_id)
        if text is None:
            # Already caught by join integrity check
            continue

        for cit in ann.citations:
            span = cit.span
            if span.start < 0 or span.end > len(text):
                errors.append(
                    f"[{doc_id}] Citation {cit.id!r}: span [{span.start}:{span.end}] "
                    f"out of bounds (text length {len(text)})"
                )
                continue

            actual = text[span.start : span.end]
            if actual != span.text:
                errors.append(
                    f"[{doc_id}] Citation {cit.id!r}: span text mismatch: "
                    f"expected {span.text!r}, got {actual!r} "
                    f"at [{span.start}:{span.end}]"
                )


def _check_controlled_vocabulary(dataset: BenchmarkDataset, errors: list[str]) -> None:
    """Validate citation.type, citation.kind, relation.relation, and law structure keys."""
    for doc_id, ann in dataset.annotations.items():
        for cit in ann.citations:
            if cit.type not in VALID_CITATION_TYPES:
                errors.append(
                    f"[{doc_id}] Citation {cit.id!r}: invalid type {cit.type!r}, "
                    f"expected one of {sorted(VALID_CITATION_TYPES)}"
                )
            if cit.kind not in VALID_CITATION_KINDS:
                errors.append(
                    f"[{doc_id}] Citation {cit.id!r}: invalid kind {cit.kind!r}, "
                    f"expected one of {sorted(VALID_CITATION_KINDS)}"
                )
            # Structure key check (only for law citations with structure)
            if cit.structure:
                for key in cit.structure:
                    if key not in VALID_STRUCTURE_KEYS:
                        errors.append(
                            f"[{doc_id}] Citation {cit.id!r}: invalid structure key {key!r}, "
                            f"expected one of {sorted(VALID_STRUCTURE_KEYS)}"
                        )

        for rel in ann.relations:
            if rel.relation not in VALID_RELATION_TYPES:
                errors.append(
                    f"[{doc_id}] Relation {rel.source_id!r}->{rel.target_id!r}: "
                    f"invalid relation type {rel.relation!r}, "
                    f"expected one of {sorted(VALID_RELATION_TYPES)}"
                )


def _check_resolves_to_integrity(dataset: BenchmarkDataset, errors: list[str]) -> None:
    """If a citation has resolves_to set, the target must exist in the same document."""
    for doc_id, ann in dataset.annotations.items():
        cit_ids = {c.id for c in ann.citations}
        for cit in ann.citations:
            if cit.resolves_to is not None and cit.resolves_to not in cit_ids:
                errors.append(
                    f"[{doc_id}] Citation {cit.id!r}: resolves_to target "
                    f"{cit.resolves_to!r} not found among citation IDs in this document"
                )


def _check_relation_integrity(dataset: BenchmarkDataset, errors: list[str]) -> None:
    """source_id and target_id in each relation must reference existing citation IDs."""
    for doc_id, ann in dataset.annotations.items():
        cit_ids = {c.id for c in ann.citations}
        for rel in ann.relations:
            if rel.source_id not in cit_ids:
                errors.append(f"[{doc_id}] Relation: source_id {rel.source_id!r} not found among citation IDs")
            if rel.target_id not in cit_ids:
                errors.append(f"[{doc_id}] Relation: target_id {rel.target_id!r} not found among citation IDs")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a benchmark dataset against quality checks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s                                    # test split, default data dir\n"
            "  %(prog)s --split validation                 # check dev split\n"
            "  %(prog)s --data-dir /path/to/data --split train\n"
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
        help="Which split to validate (default: test)",
    )
    args = parser.parse_args()

    data_dir = args.data_dir or get_data_dir()

    print(f"Validating dataset: {data_dir} (split: {args.split})")
    print()

    try:
        errors = validate_dataset(data_dir, split=args.split)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if errors:
        print(f"FAILED: {len(errors)} error(s) found:\n")
        for i, err in enumerate(errors, 1):
            print(f"  {i}. {err}")
        print()
        sys.exit(1)
    else:
        print("PASSED: All checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
