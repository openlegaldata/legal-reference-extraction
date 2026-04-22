"""Tests for benchmark metrics — A2c (structure) and A2d (relation F1)."""

from __future__ import annotations

from benchmarks.datasets import Citation, Relation, Span
from benchmarks.metrics import BenchmarkResult, score_document, score_relations


def _cit(
    cid: str,
    ctype: str,
    start: int,
    end: int,
    *,
    book: str | None = None,
    number: str | None = None,
    structure: dict[str, str] | None = None,
    court: str | None = None,
    file_number: str | None = None,
) -> Citation:
    return Citation(
        id=cid,
        type=ctype,
        kind="full",
        span=Span(start=start, end=end, text="x"),
        book=book,
        number=number,
        structure=structure or {},
        court=court,
        file_number=file_number,
    )


def test_structure_all_correct():
    gold = [_cit("g1", "law", 0, 10, book="bgb", number="1", structure={"absatz": "1"})]
    pred = [_cit("p1", "law", 0, 10, book="bgb", number="1", structure={"absatz": "1"})]
    r = BenchmarkResult()
    score_document(gold, pred, r)
    fa = r.field_accuracy["structure"]
    assert fa.correct == 1
    assert fa.incorrect == 0
    assert fa.missing_pred == 0
    assert fa.accuracy == 1.0


def test_structure_missing_in_pred():
    gold = [_cit("g1", "law", 0, 10, book="bgb", structure={"absatz": "1", "satz": "2"})]
    pred = [_cit("p1", "law", 0, 10, book="bgb", structure={})]
    r = BenchmarkResult()
    score_document(gold, pred, r)
    fa = r.field_accuracy["structure"]
    assert fa.correct == 0
    assert fa.missing_pred == 2
    assert fa.accuracy == 0.0


def test_structure_wrong_value():
    gold = [_cit("g1", "law", 0, 10, book="bgb", structure={"absatz": "1"})]
    pred = [_cit("p1", "law", 0, 10, book="bgb", structure={"absatz": "2"})]
    r = BenchmarkResult()
    score_document(gold, pred, r)
    fa = r.field_accuracy["structure"]
    assert fa.correct == 0
    assert fa.incorrect == 1
    assert fa.accuracy == 0.0


def test_structure_pred_only_key_counted_as_missing_gold():
    gold = [_cit("g1", "law", 0, 10, structure={"absatz": "1"})]
    pred = [_cit("p1", "law", 0, 10, structure={"absatz": "1", "satz": "2"})]
    r = BenchmarkResult()
    score_document(gold, pred, r)
    fa = r.field_accuracy["structure"]
    assert fa.correct == 1
    assert fa.missing_gold == 1  # pred had "satz" but gold didn't


def test_structure_skipped_for_case_type():
    gold = [_cit("g1", "case", 0, 10, court="BGH", file_number="1 BvR 1/2020")]
    pred = [_cit("p1", "case", 0, 10, court="BGH", file_number="1 BvR 1/2020")]
    r = BenchmarkResult()
    score_document(gold, pred, r)
    assert "structure" not in r.field_accuracy


def test_relations_perfect_match():
    gold_c = [_cit("c_001", "law", 0, 10), _cit("c_002", "law", 20, 30)]
    gold_r = [Relation(source_id="c_001", target_id="c_002", relation="ivm")]
    pred_c = [_cit("p_001", "law", 0, 10), _cit("p_002", "law", 20, 30)]
    pred_r = [Relation(source_id="p_001", target_id="p_002", relation="ivm")]
    r = BenchmarkResult()
    score_relations(gold_c, gold_r, pred_c, pred_r, r)
    assert r.relation_exact.tp == 1
    assert r.relation_exact.fp == 0
    assert r.relation_exact.fn == 0
    assert r.relation_exact.f1 == 1.0


def test_relations_all_missed():
    gold_c = [_cit("c_001", "law", 0, 10), _cit("c_002", "law", 20, 30)]
    gold_r = [Relation(source_id="c_001", target_id="c_002", relation="ivm")]
    r = BenchmarkResult()
    score_relations(gold_c, gold_r, [], [], r)
    assert r.relation_exact.tp == 0
    assert r.relation_exact.fn == 1
    assert r.relation_exact.f1 == 0.0
    assert r.total_gold_relations == 1
    assert r.total_pred_relations == 0


def test_relations_wrong_type():
    gold_c = [_cit("c_001", "law", 0, 10), _cit("c_002", "law", 20, 30)]
    gold_r = [Relation(source_id="c_001", target_id="c_002", relation="ivm")]
    pred_c = [_cit("p_001", "law", 0, 10), _cit("p_002", "law", 20, 30)]
    # Same spans, different relation type — counts as FP + FN
    pred_r = [Relation(source_id="p_001", target_id="p_002", relation="vgl")]
    r = BenchmarkResult()
    score_relations(gold_c, gold_r, pred_c, pred_r, r)
    assert r.relation_exact.tp == 0
    assert r.relation_exact.fp == 1
    assert r.relation_exact.fn == 1


def test_relations_match_by_spans_not_ids():
    # Pred uses completely different ids — match should still work via spans
    gold_c = [_cit("c_001", "law", 0, 10), _cit("c_002", "law", 20, 30)]
    gold_r = [Relation(source_id="c_001", target_id="c_002", relation="ivm")]
    pred_c = [_cit("xyz-1", "law", 0, 10), _cit("xyz-2", "law", 20, 30)]
    pred_r = [Relation(source_id="xyz-1", target_id="xyz-2", relation="ivm")]
    r = BenchmarkResult()
    score_relations(gold_c, gold_r, pred_c, pred_r, r)
    assert r.relation_exact.tp == 1


def test_relations_unknown_id_skipped():
    gold_c = [_cit("c_001", "law", 0, 10)]
    gold_r = [Relation(source_id="c_001", target_id="c_missing", relation="ivm")]
    r = BenchmarkResult()
    score_relations(gold_c, gold_r, [], [], r)
    # Relation has a dangling target — dropped from gold set, no FN
    assert r.relation_exact.fn == 0
    assert r.total_gold_relations == 1  # still counted as raw


def test_benchmarkresult_to_dict_includes_relations():
    r = BenchmarkResult()
    r.relation_exact.tp = 5
    r.relation_exact.fn = 2
    r.total_gold_relations = 7
    d = r.to_dict()
    assert "relation_exact" in d
    assert d["relation_exact"]["tp"] == 5
    assert d["relation_exact"]["fn"] == 2
    assert d["relation_exact"]["gold"] == 7
