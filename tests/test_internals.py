"""Direct unit tests for internal helpers added during the 0.7.0 refactor.

These cover pure-logic helpers that are exercised indirectly through
extraction tests; the unit tests here pin down the edge cases of each
helper so regressions surface at the right granularity.
"""

from __future__ import annotations

import pytest

from refex.engines.transformer import DEFAULT_MODEL
from refex.extractors.law import DivideAndConquerLawRefExtractorMixin, _apply_mask_intervals


def test_mask_empty_intervals_is_identity():
    assert _apply_mask_intervals("hello world", []) == "hello world"


def test_mask_single_interval():
    assert _apply_mask_intervals("hello world", [(6, 11)]) == "hello _____"


def test_mask_multiple_non_overlapping_intervals():
    assert _apply_mask_intervals("foo bar baz", [(0, 3), (8, 11)]) == "___ bar ___"


def test_mask_intervals_out_of_order_are_sorted():
    # Feed the intervals in reverse; expected output is the same as sorted input.
    assert _apply_mask_intervals("foo bar baz", [(8, 11), (0, 3)]) == "___ bar ___"


def test_mask_overlapping_intervals_merge():
    # (2, 6) and (4, 9) overlap → merged to (2, 9); 7 underscores cover "llo wo"... wait
    # length 0..11 = "hello world" -> masking 2..9 replaces "llo wor" (7 chars).
    assert _apply_mask_intervals("hello world", [(2, 6), (4, 9)]) == "he_______ld"


def test_mask_adjacent_intervals_merge():
    # (0, 3) followed immediately by (3, 6) — merged to (0, 6).
    assert _apply_mask_intervals("abcdefgh", [(0, 3), (3, 6)]) == "______gh"


def test_mask_full_content():
    assert _apply_mask_intervals("abc", [(0, 3)]) == "___"


def test_mask_preserves_length():
    content = "The quick brown fox jumps over the lazy dog"
    out = _apply_mask_intervals(content, [(4, 9), (16, 19)])
    assert len(out) == len(content)
    # Non-masked regions are untouched
    assert out[:4] == "The "
    assert out[9:16] == " brown "
    assert out[19:] == " jumps over the lazy dog"


def test_precise_regex_env_default_is_true(monkeypatch):
    monkeypatch.delenv("REFEX_PRECISE_BOOK_REGEX", raising=False)
    ext = DivideAndConquerLawRefExtractorMixin()
    assert ext.use_precise_book_regex is True


@pytest.mark.parametrize("falsy", ["0", "false", "False", ""])
def test_precise_regex_env_falsy_disables(monkeypatch, falsy):
    monkeypatch.setenv("REFEX_PRECISE_BOOK_REGEX", falsy)
    ext = DivideAndConquerLawRefExtractorMixin()
    assert ext.use_precise_book_regex is False


@pytest.mark.parametrize("truthy", ["1", "true", "yes", "on"])
def test_precise_regex_env_truthy_enables(monkeypatch, truthy):
    monkeypatch.setenv("REFEX_PRECISE_BOOK_REGEX", truthy)
    ext = DivideAndConquerLawRefExtractorMixin()
    assert ext.use_precise_book_regex is True


def test_default_transformer_model_points_at_openlegaldata_repo():
    assert DEFAULT_MODEL == "openlegaldata/legal-reference-extraction-base-de"


def test_default_model_is_accessible_from_public_engine_api():
    # The constant must be importable as a module attribute; downstream code
    # treats it as a stable name.
    from refex.engines import transformer

    assert transformer.DEFAULT_MODEL == DEFAULT_MODEL
    assert isinstance(transformer.DEFAULT_MODEL, str)
    assert "/" in transformer.DEFAULT_MODEL  # user/repo format
