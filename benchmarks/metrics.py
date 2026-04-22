"""Benchmark metrics: span detection F1, field-level accuracy, relation F1.

All metrics compare predicted citations (from the extractor) against gold
citations (from the benchmark dataset). Matching is done at the span level
first, then field accuracy is computed on matched pairs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from benchmarks.datasets import Citation, Relation


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

    # A2d — relation-edge F1.  Compared as (src_span, tgt_span, relation)
    # triples.  Stays empty for engines that don't emit relations (current
    # regex/CRF/transformer): both tp and fn will be accumulated on gold-
    # relation-heavy docs, pushing F1 toward 0 — which is the expected
    # baseline until an engine starts emitting resolves_to / i.V.m. links.
    relation_exact: PRF = field(default_factory=PRF)

    # Counts
    total_gold: int = 0
    total_pred: int = 0
    total_gold_relations: int = 0
    total_pred_relations: int = 0
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

        # A2d — relation-edge F1.  Only print when we actually scored at
        # least one gold or pred relation; a silent block would be noise on
        # the regex / CRF runs (which don't emit relations yet).
        if self.total_gold_relations > 0 or self.total_pred_relations > 0:
            lines.append("")
            lines.append("--- Relation Edges (exact span+type match) ---")
            lines.append(f"  Precision: {self.relation_exact.precision:.3f}")
            lines.append(f"  Recall:    {self.relation_exact.recall:.3f}")
            lines.append(f"  F1:        {self.relation_exact.f1:.3f}")
            lines.append(
                f"  (TP={self.relation_exact.tp}, FP={self.relation_exact.fp}, FN={self.relation_exact.fn}, "
                f"gold={self.total_gold_relations}, pred={self.total_pred_relations})"
            )

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
            "relation_exact": {
                "p": self.relation_exact.precision,
                "r": self.relation_exact.recall,
                "f1": self.relation_exact.f1,
                "tp": self.relation_exact.tp,
                "fp": self.relation_exact.fp,
                "fn": self.relation_exact.fn,
                "gold": self.total_gold_relations,
                "pred": self.total_pred_relations,
            },
        }


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

    matched_gold: set[tuple[int, int]] = set()
    matched_pred: set[tuple[int, int]] = set()

    for span_key in pred_spans:
        if span_key in gold_spans:
            result.span_exact.tp += 1
            matched_gold.add(span_key)
            matched_pred.add(span_key)

    result.span_exact.fp += len(pred_spans) - len(matched_pred)
    result.span_exact.fn += len(gold_spans) - len(matched_gold)

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

    _score_fields(gold_spans, pred_spans, matched_gold, result)

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
            # A2c — structure dict key-level accuracy (e.g. {"absatz": "1",
            # "satz": "2"}).  Each gold key is one unit of measurement: correct
            # if pred has the same value, incorrect if it has a different
            # value, missing_pred otherwise.  Pred-only keys count as
            # missing_gold so we can see over-emission later.
            _score_structure(gold.structure or {}, pred.structure or {}, result)
        elif gold.type == "case":
            for fname in case_fields:
                _score_field(fname, getattr(gold, fname), getattr(pred, fname), result)


def _score_structure(
    gold: dict[str, str],
    pred: dict[str, str],
    result: BenchmarkResult,
) -> None:
    """A2c — structure dict key-level accuracy on matched law citation pairs."""
    if "structure" not in result.field_accuracy:
        result.field_accuracy["structure"] = FieldAccuracy()
    fa = result.field_accuracy["structure"]

    # Score every gold key
    for k, gv in gold.items():
        pv = pred.get(k)
        if pv is None:
            fa.missing_pred += 1
        elif str(pv).strip().lower() == str(gv).strip().lower():
            fa.correct += 1
        else:
            fa.incorrect += 1

    # Score pred-only keys (over-emission)
    for k in pred:
        if k not in gold:
            fa.missing_gold += 1


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


def score_relations(
    gold_citations: list[Citation],
    gold_relations: list[Relation],
    pred_citations: list[Citation],
    pred_relations: list[Relation],
    result: BenchmarkResult,
) -> None:
    """A2d — relation-edge F1 on ``(source_span, target_span, relation)`` triples.

    Gold relations reference citations by id (e.g. ``c_003 → c_004``).  We
    resolve those to span tuples so the comparison is engine-independent.
    Predicted relations can use any id scheme — the scorer looks up each
    source/target id in the predicted citation list to get spans.
    """
    result.total_gold_relations += len(gold_relations)
    result.total_pred_relations += len(pred_relations)

    gold_id_to_span = {c.id: (c.span.start, c.span.end) for c in gold_citations}
    pred_id_to_span = {c.id: (c.span.start, c.span.end) for c in pred_citations}

    gold_triples: set[tuple[tuple[int, int], tuple[int, int], str]] = set()
    for r in gold_relations:
        s = gold_id_to_span.get(r.source_id)
        t = gold_id_to_span.get(r.target_id)
        if s and t:
            gold_triples.add((s, t, r.relation))

    pred_triples: set[tuple[tuple[int, int], tuple[int, int], str]] = set()
    for r in pred_relations:
        s = pred_id_to_span.get(r.source_id)
        t = pred_id_to_span.get(r.target_id)
        if s and t:
            pred_triples.add((s, t, r.relation))

    tp = len(gold_triples & pred_triples)
    result.relation_exact.tp += tp
    result.relation_exact.fp += len(pred_triples) - tp
    result.relation_exact.fn += len(gold_triples) - tp


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
