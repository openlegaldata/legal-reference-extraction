"""Benchmark metrics: span detection F1, field-level accuracy, relation F1.

All metrics compare predicted citations (from the extractor) against gold
citations (from the benchmark dataset). Matching is done at the span level
first, then field accuracy is computed on matched pairs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from benchmarks.datasets import Citation


@dataclass
class PRF:
    """Precision / Recall / F1 container."""

    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) > 0 else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


@dataclass
class FieldAccuracy:
    """Per-field accuracy on matched citation pairs."""

    correct: int = 0
    incorrect: int = 0
    missing_gold: int = 0  # gold has value, pred doesn't
    missing_pred: int = 0  # pred has value, gold doesn't

    @property
    def accuracy(self) -> float:
        total = self.correct + self.incorrect
        return self.correct / total if total > 0 else 0.0

    @property
    def total(self) -> int:
        return self.correct + self.incorrect + self.missing_gold + self.missing_pred


@dataclass
class BenchmarkResult:
    """Full benchmark result for one run."""

    # Span-level detection
    span_exact: PRF = field(default_factory=PRF)
    span_overlap: PRF = field(default_factory=PRF)

    # Per-type span detection
    span_by_type: dict[str, PRF] = field(default_factory=dict)

    # Field accuracy (on matched pairs only)
    field_accuracy: dict[str, FieldAccuracy] = field(default_factory=dict)

    # Counts
    total_gold: int = 0
    total_pred: int = 0
    total_docs: int = 0

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Documents: {self.total_docs}",
            f"Gold citations: {self.total_gold}",
            f"Predicted citations: {self.total_pred}",
            "",
            "--- Span Detection (exact match) ---",
            f"  Precision: {self.span_exact.precision:.3f}",
            f"  Recall:    {self.span_exact.recall:.3f}",
            f"  F1:        {self.span_exact.f1:.3f}",
            f"  (TP={self.span_exact.tp}, FP={self.span_exact.fp}, FN={self.span_exact.fn})",
            "",
            "--- Span Detection (overlap match) ---",
            f"  Precision: {self.span_overlap.precision:.3f}",
            f"  Recall:    {self.span_overlap.recall:.3f}",
            f"  F1:        {self.span_overlap.f1:.3f}",
            f"  (TP={self.span_overlap.tp}, FP={self.span_overlap.fp}, FN={self.span_overlap.fn})",
        ]

        if self.span_by_type:
            lines.append("")
            lines.append("--- Per-type F1 (exact) ---")
            for ctype, prf in sorted(self.span_by_type.items()):
                lines.append(f"  {ctype:12s}  P={prf.precision:.3f}  R={prf.recall:.3f}  F1={prf.f1:.3f}")

        if self.field_accuracy:
            lines.append("")
            lines.append("--- Field Accuracy (on matched pairs) ---")
            for fname, fa in sorted(self.field_accuracy.items()):
                if fa.total > 0:
                    lines.append(f"  {fname:15s}  {fa.accuracy:.3f}  ({fa.correct}/{fa.total})")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Machine-readable dict for JSON serialisation."""
        return {
            "total_docs": self.total_docs,
            "total_gold": self.total_gold,
            "total_pred": self.total_pred,
            "span_exact": {"p": self.span_exact.precision, "r": self.span_exact.recall, "f1": self.span_exact.f1},
            "span_overlap": {
                "p": self.span_overlap.precision,
                "r": self.span_overlap.recall,
                "f1": self.span_overlap.f1,
            },
            "span_by_type": {
                t: {"p": prf.precision, "r": prf.recall, "f1": prf.f1} for t, prf in self.span_by_type.items()
            },
            "field_accuracy": {
                f: {"accuracy": fa.accuracy, "correct": fa.correct, "total": fa.total}
                for f, fa in self.field_accuracy.items()
            },
        }


# --- Scoring functions ---


def score_document(
    gold_citations: list[Citation],
    pred_citations: list[Citation],
    result: BenchmarkResult,
) -> None:
    """Score one document's predictions against gold. Mutates *result* in place."""
    result.total_gold += len(gold_citations)
    result.total_pred += len(pred_citations)

    # Build span sets for exact matching
    gold_spans = {(c.span.start, c.span.end): c for c in gold_citations}
    pred_spans = {(c.span.start, c.span.end): c for c in pred_citations}

    # --- Exact span matching ---
    matched_gold: set[tuple[int, int]] = set()
    matched_pred: set[tuple[int, int]] = set()

    for span_key in pred_spans:
        if span_key in gold_spans:
            result.span_exact.tp += 1
            matched_gold.add(span_key)
            matched_pred.add(span_key)

    result.span_exact.fp += len(pred_spans) - len(matched_pred)
    result.span_exact.fn += len(gold_spans) - len(matched_gold)

    # --- Overlap span matching ---
    gold_list = sorted(gold_citations, key=lambda c: c.span.start)
    pred_list = sorted(pred_citations, key=lambda c: c.span.start)

    overlap_matched_gold: set[int] = set()
    overlap_matched_pred: set[int] = set()

    for pi, pc in enumerate(pred_list):
        for gi, gc in enumerate(gold_list):
            if gi in overlap_matched_gold:
                continue
            if _spans_overlap(pc.span.start, pc.span.end, gc.span.start, gc.span.end):
                result.span_overlap.tp += 1
                overlap_matched_gold.add(gi)
                overlap_matched_pred.add(pi)
                break

    result.span_overlap.fp += len(pred_list) - len(overlap_matched_pred)
    result.span_overlap.fn += len(gold_list) - len(overlap_matched_gold)

    # --- Per-type exact span matching ---
    for ctype in ("law", "case"):
        if ctype not in result.span_by_type:
            result.span_by_type[ctype] = PRF()
        prf = result.span_by_type[ctype]
        gold_t = {(c.span.start, c.span.end) for c in gold_citations if c.type == ctype}
        pred_t = {(c.span.start, c.span.end) for c in pred_citations if c.type == ctype}
        tp = len(gold_t & pred_t)
        prf.tp += tp
        prf.fp += len(pred_t) - tp
        prf.fn += len(gold_t) - tp

    # --- Per-type overlap span matching ---
    for ctype in ("law", "case"):
        key = f"{ctype}_overlap"
        if key not in result.span_by_type:
            result.span_by_type[key] = PRF()
        prf = result.span_by_type[key]
        gold_t = [c for c in gold_citations if c.type == ctype]
        pred_t = [c for c in pred_citations if c.type == ctype]
        gold_t.sort(key=lambda c: c.span.start)
        pred_t.sort(key=lambda c: c.span.start)
        omg: set[int] = set()
        omp: set[int] = set()
        for pi, pc in enumerate(pred_t):
            for gi, gc in enumerate(gold_t):
                if gi in omg:
                    continue
                if _spans_overlap(pc.span.start, pc.span.end, gc.span.start, gc.span.end):
                    prf.tp += 1
                    omg.add(gi)
                    omp.add(pi)
                    break
        prf.fp += len(pred_t) - len(omp)
        prf.fn += len(gold_t) - len(omg)

    # --- Field accuracy on exact-matched pairs ---
    _score_fields(gold_spans, pred_spans, matched_gold, result)

    # --- Field accuracy on overlap-matched pairs ---
    _score_fields_overlap(gold_citations, pred_citations, result)


def _spans_overlap(s1: int, e1: int, s2: int, e2: int) -> bool:
    return s1 < e2 and s2 < e1


def _score_fields(
    gold_spans: dict[tuple[int, int], Citation],
    pred_spans: dict[tuple[int, int], Citation],
    matched: set[tuple[int, int]],
    result: BenchmarkResult,
) -> None:
    """Score field-level accuracy on matched citation pairs."""
    law_fields = ("book", "number")
    case_fields = ("court", "file_number")

    for span_key in matched:
        gold = gold_spans[span_key]
        pred = pred_spans[span_key]

        if gold.type == "law":
            for fname in law_fields:
                _score_field(fname, getattr(gold, fname), getattr(pred, fname), result)
        elif gold.type == "case":
            for fname in case_fields:
                _score_field(fname, getattr(gold, fname), getattr(pred, fname), result)


def _score_fields_overlap(
    gold_citations: list[Citation],
    pred_citations: list[Citation],
    result: BenchmarkResult,
) -> None:
    """Score field accuracy on overlap-matched citation pairs."""
    gold_list = sorted(gold_citations, key=lambda c: c.span.start)
    pred_list = sorted(pred_citations, key=lambda c: c.span.start)

    matched_gold: set[int] = set()

    for pc in pred_list:
        for gi, gc in enumerate(gold_list):
            if gi in matched_gold:
                continue
            if gc.type != pc.type:
                continue
            if _spans_overlap(pc.span.start, pc.span.end, gc.span.start, gc.span.end):
                matched_gold.add(gi)
                # Score fields on this overlap-matched pair
                if gc.type == "law":
                    for fname in ("book", "number"):
                        _score_field(
                            f"{fname}_overlap",
                            getattr(gc, fname),
                            getattr(pc, fname),
                            result,
                        )
                elif gc.type == "case":
                    for fname in ("court", "file_number"):
                        _score_field(
                            f"{fname}_overlap",
                            getattr(gc, fname),
                            getattr(pc, fname),
                            result,
                        )
                break


def _score_field(
    name: str,
    gold_val: str | None,
    pred_val: str | None,
    result: BenchmarkResult,
) -> None:
    if name not in result.field_accuracy:
        result.field_accuracy[name] = FieldAccuracy()
    fa = result.field_accuracy[name]

    # Normalise empties to None
    gv = _normalize_field(name, gold_val)
    pv = _normalize_field(name, pred_val)

    if gv and pv:
        if gv == pv:
            fa.correct += 1
        else:
            fa.incorrect += 1
    elif gv and not pv:
        fa.missing_pred += 1
    elif pv and not gv:
        fa.missing_gold += 1
    # Both None: skip (nothing to measure)


_COURT_SENATE_RE = __import__("re").compile(
    r"\s+\d+\.\s*(Zivilsenat|Strafsenat|Senat|Kammer|Familiensenat|Revisionssenat|Kartellsenat)$",
    __import__("re").IGNORECASE,
)


def _normalize_field(name: str, val: str | None) -> str | None:
    """Normalize a field value for comparison."""
    if not val:
        return None
    v = val.strip().lower()
    if not v:
        return None
    # For court fields, strip senate info ("BAG 5. Senat" → "bag")
    if name in ("court", "court_overlap"):
        v = _COURT_SENATE_RE.sub("", v)
    return v
