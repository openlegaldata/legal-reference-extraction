"""Load benchmark datasets from configurable paths.

The benchmark data is NOT committed to this repo. It lives in a sibling
project (german-legal-references-benchmark) or any directory you point to.

Supports two formats:

1. **HF Arrow dataset** (preferred): A ``DatasetDict`` saved to disk via
   ``datasets.save_to_disk()``. Has train/validation/test splits with
   merged document + annotation data per row.

2. **JSONL files** (legacy): A flat directory with ``documents.jsonl`` +
   ``annotations.jsonl``, or split subdirectories (train/dev/test).

Default data path: ``../german-legal-references-benchmark/data/benchmark_10k_hf``
Override via: ``BENCH_DATA_DIR`` environment variable or ``--data-dir`` CLI flag.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# Default: sibling project's 10k HF dataset
_DEFAULT_DATA_DIR = (
    Path(__file__).resolve().parent.parent.parent / "german-legal-references-benchmark" / "data" / "benchmark_10k_hf"
)


def get_data_dir() -> Path:
    """Resolve the benchmark data directory from env or default."""
    env = os.environ.get("BENCH_DATA_DIR")
    if env:
        return Path(env)
    return _DEFAULT_DATA_DIR


@dataclass
class Span:
    start: int
    end: int
    text: str


@dataclass
class Citation:
    id: str
    type: str  # "law", "case", "literature"
    kind: str
    span: Span
    # Law fields
    unit: str | None = None
    delimiter: str | None = None
    book: str | None = None
    number: str | None = None
    structure: dict[str, str] = field(default_factory=dict)
    # Case fields
    court: str | None = None
    file_number: str | None = None
    date: str | None = None
    reporter: str | None = None
    reporter_volume: str | None = None
    reporter_page: str | None = None
    # Common
    resolves_to: str | None = None
    confidence: float = 1.0


@dataclass
class Relation:
    source_id: str
    target_id: str
    relation: str
    span: Span | None = None


@dataclass
class Document:
    doc_id: str
    text: str
    raw: str = ""
    court: str | None = None
    decision_date: str | None = None
    decision_type: str | None = None


@dataclass
class AnnotationSet:
    doc_id: str
    citations: list[Citation] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)


@dataclass
class BenchmarkDataset:
    """A loaded benchmark dataset with documents and gold annotations."""

    documents: list[Document]
    annotations: dict[str, AnnotationSet]  # keyed by doc_id

    @property
    def doc_ids(self) -> list[str]:
        return [d.doc_id for d in self.documents]

    def __len__(self) -> int:
        return len(self.documents)


def load_dataset(
    data_dir: Path | None = None,
    split: str = "test",
) -> BenchmarkDataset:
    """Load a benchmark dataset from HF Arrow format or JSONL.

    Auto-detects format: if a ``dataset_dict.json`` exists, loads as HF
    dataset; otherwise falls back to JSONL.

    Args:
        data_dir: Path to the dataset directory. If None, uses the default
                  resolved via ``get_data_dir()``.
        split: Which split to load (train/validation/test). Only used for
               HF datasets and split JSONL directories.

    Raises:
        FileNotFoundError: If the data directory or required files don't exist.
    """
    if data_dir is None:
        data_dir = get_data_dir()

    data_dir = Path(data_dir)

    # Auto-detect format
    if (data_dir / "dataset_dict.json").exists():
        return _load_hf_dataset(data_dir, split)

    # Check for split JSONL directories (train/dev/test)
    split_dir_map = {"train": "train", "validation": "dev", "test": "test"}
    dir_name = split_dir_map.get(split, split)
    split_dir = data_dir / dir_name
    if split_dir.exists() and (split_dir / "documents.jsonl").exists():
        return _load_jsonl_dataset(split_dir)

    # Legacy flat JSONL
    if (data_dir / "documents.jsonl").exists():
        return _load_jsonl_dataset(data_dir)

    msg = (
        f"Benchmark data not found at {data_dir}\n"
        f"Set BENCH_DATA_DIR or use --data-dir to point to a dataset directory.\n"
        f"Supported formats: HF Arrow (dataset_dict.json) or JSONL (documents.jsonl)"
    )
    raise FileNotFoundError(msg)


def _load_hf_dataset(data_dir: Path, split: str) -> BenchmarkDataset:
    """Load from HF Arrow format saved via datasets.save_to_disk()."""
    hf_cache = os.environ.get("HF_DATASETS_CACHE", "/tmp/hf-cache")
    os.environ.setdefault("HF_DATASETS_CACHE", hf_cache)
    os.environ.setdefault("HF_HOME", os.environ.get("HF_HOME", "/tmp/hf-home"))

    from datasets import load_from_disk

    ds_dict = load_from_disk(str(data_dir))

    if split not in ds_dict:
        available = list(ds_dict.keys())
        msg = f"Split '{split}' not found. Available: {available}"
        raise ValueError(msg)

    ds = ds_dict[split]

    documents = []
    annotations = {}

    for row in ds:
        doc_id = row["doc_id"]
        documents.append(
            Document(
                doc_id=doc_id,
                text=row["text"],
                raw=row.get("raw", ""),
                court=row.get("court"),
                decision_date=row.get("decision_date"),
                decision_type=row.get("decision_type"),
            )
        )

        cit_data = json.loads(row.get("citations", "[]"))
        rel_data = json.loads(row.get("relations", "[]"))

        citations = [_parse_citation(c) for c in cit_data]
        rels = [_parse_relation(r) for r in rel_data]

        annotations[doc_id] = AnnotationSet(doc_id=doc_id, citations=citations, relations=rels)

    return BenchmarkDataset(documents=documents, annotations=annotations)


def _parse_citation(c: dict) -> Citation:
    """Parse a citation dict from JSON."""
    return Citation(
        id=c["id"],
        type=c["type"],
        kind=c.get("kind", "full"),
        span=Span(**c["span"]),
        unit=c.get("unit"),
        delimiter=c.get("delimiter"),
        book=c.get("book"),
        number=c.get("number"),
        structure=c.get("structure", {}),
        court=c.get("court"),
        file_number=c.get("file_number"),
        date=c.get("date"),
        reporter=c.get("reporter"),
        reporter_volume=c.get("reporter_volume"),
        reporter_page=c.get("reporter_page"),
        resolves_to=c.get("resolves_to"),
        confidence=c.get("confidence", 1.0),
    )


def _parse_relation(r: dict) -> Relation:
    """Parse a relation dict from JSON."""
    return Relation(
        source_id=r["source_id"],
        target_id=r["target_id"],
        relation=r["relation"],
        span=Span(**r["span"]) if r.get("span") else None,
    )


def _load_jsonl_dataset(data_dir: Path) -> BenchmarkDataset:
    """Load from a directory with documents.jsonl + annotations.jsonl."""
    docs_file = data_dir / "documents.jsonl"
    anns_file = data_dir / "annotations.jsonl"

    documents = []
    with open(docs_file, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            documents.append(
                Document(
                    doc_id=d["doc_id"],
                    text=d["text"],
                    raw=d.get("raw", ""),
                    court=d.get("court"),
                    decision_date=d.get("decision_date"),
                    decision_type=d.get("decision_type"),
                )
            )

    annotations = {}
    if anns_file.exists():
        with open(anns_file, encoding="utf-8") as f:
            for line in f:
                a = json.loads(line)
                citations = [_parse_citation(c) for c in a.get("citations", [])]
                rels = [_parse_relation(r) for r in a.get("relations", [])]
                annotations[a["doc_id"]] = AnnotationSet(doc_id=a["doc_id"], citations=citations, relations=rels)

    return BenchmarkDataset(documents=documents, annotations=annotations)
