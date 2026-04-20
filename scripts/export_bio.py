"""Export benchmark gold annotations to HuggingFace BIO JSONL.

Reads a split from the benchmark HF Arrow dataset, converts each
document's gold citations to ``LawCitation`` / ``CaseCitation`` objects,
and runs them through ``refex.serializers.to_hf_bio`` so the emitted
labels match what ``TransformerExtractor`` expects at inference time.

Output format (one JSON object per line):
    {
      "doc_id": "...",
      "tokens": ["Die", "Klage", ...],
      "ner_tags": ["O", "O", "B-LAW_REF", ...]
    }

Usage:
    python scripts/export_bio.py --split train --output data/hf_bio/train.jsonl
    python scripts/export_bio.py --split validation --output data/hf_bio/validation.jsonl
    python scripts/export_bio.py --split test --output data/hf_bio/test.jsonl

Environment:
    BENCH_DATA_DIR  Override the default benchmark data directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from benchmarks.datasets import Citation as BenchCitation  # noqa: E402
from benchmarks.datasets import load_dataset  # noqa: E402

from refex.citations import CaseCitation, ExtractionResult, LawCitation  # noqa: E402
from refex.citations import Span as RefSpan  # noqa: E402
from refex.serializers import to_hf_bio  # noqa: E402


def _bench_to_refex(cit: BenchCitation) -> LawCitation | CaseCitation | None:
    span = RefSpan(start=cit.span.start, end=cit.span.end, text=cit.span.text)
    if cit.type == "law":
        return LawCitation(
            span=span,
            id=cit.id,
            kind="full",
            book=cit.book,
            number=cit.number,
            source="gold",
        )
    if cit.type == "case":
        return CaseCitation(
            span=span,
            id=cit.id,
            kind="full",
            court=cit.court,
            file_number=cit.file_number,
            date=cit.date,
            source="gold",
        )
    return None


def export(split: str, output: Path, data_dir: Path | None, limit: int | None) -> tuple[int, int, int]:
    """Export ``split`` to ``output`` as BIO JSONL.

    Returns (n_docs, n_citations, n_nonO_tokens) for reporting.
    """
    ds = load_dataset(data_dir=data_dir, split=split)
    output.parent.mkdir(parents=True, exist_ok=True)

    n_docs = 0
    n_cits = 0
    n_nonO = 0

    with open(output, "w", encoding="utf-8") as f:
        for doc in ds.documents:
            if limit is not None and n_docs >= limit:
                break

            ann = ds.annotations.get(doc.doc_id)
            gold = []
            if ann is not None:
                for c in ann.citations:
                    if c.type not in ("law", "case"):
                        continue
                    conv = _bench_to_refex(c)
                    if conv is not None:
                        gold.append(conv)

            result = ExtractionResult(citations=gold)
            record = to_hf_bio(result, doc.text)
            record["doc_id"] = doc.doc_id

            f.write(json.dumps(record, ensure_ascii=False) + "\n")

            n_docs += 1
            n_cits += len(gold)
            n_nonO += sum(1 for t in record["ner_tags"] if t != "O")

    return n_docs, n_cits, n_nonO


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=["train", "validation", "test"], required=True)
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL path")
    parser.add_argument("--data-dir", type=Path, default=None, help="Override benchmark data dir")
    parser.add_argument("--limit", type=int, default=None, help="Cap number of docs")
    args = parser.parse_args()

    n_docs, n_cits, n_nonO = export(args.split, args.output, args.data_dir, args.limit)

    total_bytes = args.output.stat().st_size if args.output.exists() else 0
    print(
        f"Exported split={args.split!r} docs={n_docs} citations={n_cits} "
        f"non-O tokens={n_nonO} bytes={total_bytes:,} -> {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
