"""Load benchmark datasets from local paths or the HuggingFace Hub.

The benchmark data is NOT committed to this repo. It lives in a sibling
project (german-legal-references-benchmark) or on the HuggingFace Hub.

Supports three sources, resolved in order:

1. **Explicit local path** via ``--data-dir`` / ``BENCH_DATA_DIR``. Either
   an HF Arrow ``DatasetDict`` (saved via ``datasets.save_to_disk()``) or
   a JSONL directory with ``documents.jsonl`` + ``annotations.jsonl``.

2. **Default local path** at
   ``../german-legal-references-benchmark/data/benchmark_10k_hf`` (sibling
   checkout), used when neither ``--data-dir`` nor ``BENCH_DATA_DIR`` is
   set.

3. **HuggingFace Hub fallback**: if no local path resolves, load from
   the private Hub repo
   ``openlegaldata/german-legal-references-benchmark`` via
   ``datasets.load_dataset()``. Override the repo with ``--hf-repo`` or
   ``BENCH_HF_REPO``.

The Hub fallback requires the ``datasets`` library and a valid HF token
with access to the (private) dataset.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Default: sibling project's 10k HF dataset
_DEFAULT_DATA_DIR = (
    Path(__file__).resolve().parent.parent.parent / "german-legal-references-benchmark" / "data" / "benchmark_10k_hf"
)

# Default: private HF Hub repo for the German legal references benchmark.
_DEFAULT_HF_REPO = "openlegaldata/german-legal-references-benchmark"


def get_data_dir() -> Path:
    """Resolve the benchmark data directory from env or default."""
    env = os.environ.get("BENCH_DATA_DIR")
    if env:
        return Path(env)
    return _DEFAULT_DATA_DIR


def get_hf_repo() -> str:
    """Resolve the HuggingFace Hub repo id from env or default."""
    return os.environ.get("BENCH_HF_REPO", _DEFAULT_HF_REPO)


def _local_dataset_exists(data_dir: Path) -> bool:
    """Return True if ``data_dir`` contains a recognisable dataset."""
    if not data_dir.exists():
        return False
    if (data_dir / "dataset_dict.json").exists():
        return True
    if (data_dir / "documents.jsonl").exists():
        return True
    for sub in ("train", "validation", "test", "dev"):
        if (data_dir / sub / "documents.jsonl").exists():
            return True
    return False


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
    hf_repo: str | None = None,
) -> BenchmarkDataset:
    """Load a benchmark dataset from a local path or the HuggingFace Hub.

    Resolution order:

    1. If ``data_dir`` (or ``BENCH_DATA_DIR``) points to an existing
       dataset, load it locally. Auto-detects HF Arrow vs JSONL.
    2. Otherwise fall back to ``datasets.load_dataset(hf_repo, ...)``
       against the HuggingFace Hub. ``hf_repo`` defaults to
       ``BENCH_HF_REPO`` or
       ``openlegaldata/german-legal-references-benchmark``.

    Args:
        data_dir: Path to a local dataset directory. If None, resolves
                  via ``get_data_dir()``. When the resolved path does
                  not contain a recognisable dataset the Hub fallback
                  is used.
        split: Which split to load (train/validation/test).
        hf_repo: HuggingFace Hub repo id used for the fallback. If None,
                 resolves via ``get_hf_repo()``.

    Raises:
        FileNotFoundError: If neither a local dataset nor the Hub repo
            can be loaded.
    """
    explicit_local = data_dir is not None
    if data_dir is None:
        data_dir = get_data_dir()
    data_dir = Path(data_dir)

    if _local_dataset_exists(data_dir):
        return _load_local_dataset(data_dir, split)

    # Local path was explicitly given but doesn't exist — surface the
    # error rather than silently going to the Hub. Callers can pass an
    # empty path or unset --data-dir to opt into the fallback.
    if explicit_local:
        msg = (
            f"Benchmark data not found at {data_dir} (--data-dir was explicit).\n"
            f"Either point --data-dir at a valid dataset or omit it to fall back "
            f"to the HuggingFace Hub repo {hf_repo or get_hf_repo()!r}."
        )
        raise FileNotFoundError(msg)

    repo = hf_repo or get_hf_repo()
    logger.info(
        "Local dataset not found at %s — falling back to HuggingFace Hub repo %r",
        data_dir,
        repo,
    )
    return _load_hf_hub_dataset(repo, split)


def _load_local_dataset(data_dir: Path, split: str) -> BenchmarkDataset:
    """Dispatch to the right local loader based on directory contents."""
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
        f"Supported formats: HF Arrow (dataset_dict.json) or JSONL (documents.jsonl)"
    )
    raise FileNotFoundError(msg)


def _ensure_hf_cache_env() -> None:
    """Default HF cache locations to writable tmpdirs when unset."""
    os.environ.setdefault("HF_DATASETS_CACHE", "/tmp/hf-cache")
    os.environ.setdefault("HF_HOME", "/tmp/hf-home")


def _load_hf_dataset(data_dir: Path, split: str) -> BenchmarkDataset:
    """Load from HF Arrow format saved via datasets.save_to_disk()."""
    _ensure_hf_cache_env()
    from datasets import load_from_disk

    ds_dict = load_from_disk(str(data_dir))

    if split not in ds_dict:
        available = list(ds_dict.keys())
        msg = f"Split '{split}' not found. Available: {available}"
        raise ValueError(msg)

    return _benchmark_from_hf_split(ds_dict[split])


def _load_hf_hub_dataset(repo: str, split: str) -> BenchmarkDataset:
    """Load a split from the HuggingFace Hub.

    Requires a valid HF token for private repos. Set via ``hf auth login``
    or the ``HF_TOKEN`` / ``HUGGING_FACE_HUB_TOKEN`` env var.
    """
    _ensure_hf_cache_env()
    try:
        from datasets import load_dataset as hf_load_dataset
    except ImportError as exc:  # pragma: no cover - import guard
        msg = (
            "The 'datasets' package is required to load from the HuggingFace Hub. "
            "Install it via 'pip install datasets' or use --data-dir to load a local dataset."
        )
        raise ImportError(msg) from exc

    try:
        ds = hf_load_dataset(repo, split=split)
    except Exception as exc:
        msg = (
            f"Failed to load benchmark from HuggingFace Hub repo {repo!r} (split={split!r}). "
            f"The dataset may be private — run 'hf auth login' or set HF_TOKEN. "
            f"Alternatively pass --data-dir to use a local copy. Original error: {exc}"
        )
        raise FileNotFoundError(msg) from exc

    return _benchmark_from_hf_split(ds)


def _benchmark_from_hf_split(ds) -> BenchmarkDataset:
    """Convert a HuggingFace ``Dataset`` split into a ``BenchmarkDataset``."""
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

        cit_raw = row.get("citations", "[]")
        rel_raw = row.get("relations", "[]")
        cit_data = json.loads(cit_raw) if isinstance(cit_raw, str) else (cit_raw or [])
        rel_data = json.loads(rel_raw) if isinstance(rel_raw, str) else (rel_raw or [])

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
