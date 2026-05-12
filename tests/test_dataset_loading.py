"""Tests for benchmark dataset loading: local + HuggingFace Hub fallback."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from benchmarks import datasets as datasets_mod
from benchmarks.datasets import (
    _DEFAULT_HF_REPO,
    BenchmarkDataset,
    get_hf_repo,
    load_dataset,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _make_jsonl_dataset(root: Path, split: str = "test") -> None:
    split_dir_map = {"train": "train", "validation": "dev", "test": "test"}
    split_dir = root / split_dir_map[split]
    _write_jsonl(
        split_dir / "documents.jsonl",
        [
            {
                "doc_id": "doc1",
                "text": "Hello world",
                "court": "BGH",
                "decision_date": "2024-01-01",
                "decision_type": "Urteil",
            }
        ],
    )
    _write_jsonl(
        split_dir / "annotations.jsonl",
        [
            {
                "doc_id": "doc1",
                "citations": [
                    {
                        "id": "c_001",
                        "type": "law",
                        "kind": "full",
                        "span": {"start": 0, "end": 5, "text": "Hello"},
                    }
                ],
                "relations": [],
            }
        ],
    )


def test_get_hf_repo_defaults_to_openlegaldata():
    with patch.dict("os.environ", {}, clear=False):
        # Strip env to be safe (BENCH_HF_REPO must NOT be set for this assertion).
        import os

        os.environ.pop("BENCH_HF_REPO", None)
        assert get_hf_repo() == _DEFAULT_HF_REPO


def test_get_hf_repo_respects_env(monkeypatch):
    monkeypatch.setenv("BENCH_HF_REPO", "someorg/custom-bench")
    assert get_hf_repo() == "someorg/custom-bench"


def test_load_dataset_uses_local_when_present(tmp_path):
    _make_jsonl_dataset(tmp_path, split="test")
    ds = load_dataset(tmp_path, split="test")
    assert isinstance(ds, BenchmarkDataset)
    assert ds.doc_ids == ["doc1"]
    assert ds.documents[0].court == "BGH"


def test_load_dataset_explicit_missing_path_raises(tmp_path):
    """Explicit --data-dir that doesn't exist must NOT silently go to HF Hub."""
    missing = tmp_path / "nope"
    with pytest.raises(FileNotFoundError, match="explicit"):
        load_dataset(missing, split="test")


def test_load_dataset_falls_back_to_hub_when_default_missing(monkeypatch, tmp_path):
    """When --data-dir is omitted and the default doesn't exist, fall back to HF."""
    monkeypatch.setenv("BENCH_DATA_DIR", str(tmp_path / "absent"))
    monkeypatch.setenv("BENCH_HF_REPO", "fakeorg/fake-benchmark")

    captured: dict[str, object] = {}

    def fake_load(repo, split):
        captured["repo"] = repo
        captured["split"] = split
        return [
            {
                "doc_id": "hub-doc-1",
                "text": "from hub",
                "court": "BVerfG",
                "decision_date": "2025-01-01",
                "decision_type": "Beschluss",
                "citations": "[]",
                "relations": "[]",
            }
        ]

    # Inject a tiny stub for the 'datasets' module so we don't depend on it.
    fake_module = type(sys)("datasets")
    fake_module.load_dataset = fake_load  # type: ignore[attr-defined]
    fake_module.load_from_disk = lambda path: {}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "datasets", fake_module)

    ds = load_dataset(data_dir=None, split="validation")

    assert captured["repo"] == "fakeorg/fake-benchmark"
    assert captured["split"] == "validation"
    assert ds.doc_ids == ["hub-doc-1"]
    assert ds.documents[0].court == "BVerfG"


def test_load_dataset_hub_repo_arg_overrides_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BENCH_DATA_DIR", str(tmp_path / "absent"))
    monkeypatch.setenv("BENCH_HF_REPO", "fromenv/repo")

    captured: dict[str, object] = {}

    def fake_load(repo, split):
        captured["repo"] = repo
        return []

    fake_module = type(sys)("datasets")
    fake_module.load_dataset = fake_load  # type: ignore[attr-defined]
    fake_module.load_from_disk = lambda path: {}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "datasets", fake_module)

    load_dataset(data_dir=None, split="test", hf_repo="explicit/override")

    assert captured["repo"] == "explicit/override"


def test_load_dataset_hub_failure_surfaces_helpful_error(monkeypatch, tmp_path):
    monkeypatch.setenv("BENCH_DATA_DIR", str(tmp_path / "absent"))

    def fake_load(repo, split):
        raise RuntimeError("403 Forbidden")

    fake_module = type(sys)("datasets")
    fake_module.load_dataset = fake_load  # type: ignore[attr-defined]
    fake_module.load_from_disk = lambda path: {}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "datasets", fake_module)

    with pytest.raises(FileNotFoundError) as exc_info:
        load_dataset(data_dir=None, split="test")

    msg = str(exc_info.value)
    assert "hf auth login" in msg.lower() or "hf_token" in msg.lower()
    assert "403" in msg


def test_local_dataset_exists_helper(tmp_path):
    assert not datasets_mod._local_dataset_exists(tmp_path / "absent")

    _make_jsonl_dataset(tmp_path / "with_jsonl", split="test")
    assert datasets_mod._local_dataset_exists(tmp_path / "with_jsonl")

    hf_marker = tmp_path / "with_hf"
    hf_marker.mkdir()
    (hf_marker / "dataset_dict.json").write_text("{}", encoding="utf-8")
    assert datasets_mod._local_dataset_exists(hf_marker)
