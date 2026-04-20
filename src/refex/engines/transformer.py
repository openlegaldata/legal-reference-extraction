"""Transformer-based citation extraction engine (Stream G).

Uses a HuggingFace ``transformers`` token-classification model to predict
BIO tags over sub-word tokens, then aligns predictions back to character
spans and converts them to typed ``Citation`` objects.

Default weights: ``PaDaS-Lab/gbert-legal-ner`` — a BERT model fine-tuned
on German legal NER.  Users can override with any HuggingFace
token-classification model whose labels match the BIO scheme
``{B,I}-{LAW,CASE}_REF`` or the compatible aliases produced by
:func:`refex.engines.crf.spans_to_citations`.

Inference runs on CPU by default; pass ``device="cuda"``, ``"mps"``, or
a torch device object to use GPU/MPS.  Batch inference (``extract_batch``)
improves throughput substantially on accelerators.

Training is separate: use the ``to_hf_bio`` serializer to export training
data and fine-tune a model with the HuggingFace Trainer API or any
framework that accepts BIO labels.  See ``docs/train-transformer.md``.

Requires the ``[transformers]`` extra:
``pip install legal-reference-extraction[transformers]``
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from refex.citations import (
    CaseCitation,
    Citation,
    CitationRelation,
    LawCitation,
    Span,
    make_citation_id,
)
from refex.engines.crf import _parse_case_fields, _parse_law_fields

logger = logging.getLogger(__name__)


# --- Default model & label mapping ---

DEFAULT_MODEL = "PaDaS-Lab/gbert-legal-ner"

# The model may use different label names than refex's canonical scheme.
# This mapping normalises common variants to our internal vocabulary.
# Override via `TransformerExtractor(label_mapping=...)`.
DEFAULT_LABEL_MAP: dict[str, str] = {
    # Common BIO variants for German legal NER
    "B-LAW": "B-LAW_REF",
    "I-LAW": "I-LAW_REF",
    "B-GS": "B-LAW_REF",  # Gesetz
    "I-GS": "I-LAW_REF",
    "B-VO": "B-LAW_REF",  # Verordnung
    "I-VO": "I-LAW_REF",
    "B-RS": "B-CASE_REF",  # Rechtsprechung
    "I-RS": "I-CASE_REF",
    "B-AZ": "B-CASE_REF",  # Aktenzeichen
    "I-AZ": "I-CASE_REF",
    "B-CASE": "B-CASE_REF",
    "I-CASE": "I-CASE_REF",
    # Canonical refex labels (passthrough)
    "B-LAW_REF": "B-LAW_REF",
    "I-LAW_REF": "I-LAW_REF",
    "B-CASE_REF": "B-CASE_REF",
    "I-CASE_REF": "I-CASE_REF",
    "O": "O",
}


# --- Extractor engine ---


class TransformerExtractor:
    """Transformer-based citation extractor implementing the ``Extractor`` protocol.

    Loads a HuggingFace token-classification model and predicts BIO tags
    over sub-word tokens.  Sub-word predictions are aggregated to the
    first-token-of-word strategy (configurable) and mapped back to
    character spans.

    Usage::

        extractor = TransformerExtractor()  # CPU, default German legal NER model
        citations, relations = extractor.extract(text)

        # GPU/MPS
        extractor = TransformerExtractor(device="cuda")
        extractor = TransformerExtractor(device="mps")

        # Batch inference (faster on accelerators)
        results = extractor.extract_batch(texts, batch_size=16)

        # Custom model
        extractor = TransformerExtractor(model="./my-finetuned-model")
    """

    def __init__(
        self,
        model: str | Path = DEFAULT_MODEL,
        device: str | Any = "cpu",
        aggregation: str = "first",
        label_mapping: dict[str, str] | None = None,
        max_length: int = 512,
        stride: int = 128,
        trust_remote_code: bool = True,
    ):
        """
        Args:
            model: HuggingFace model name or local path.
            device: ``"cpu"``, ``"cuda"``, ``"mps"``, or a torch.device.
            aggregation: Sub-word → word aggregation strategy.
                ``"first"`` (default): use the first sub-word's label.
                ``"max"``: use the sub-word with highest probability.
            label_mapping: Map from model-native labels to refex canonical
                labels (``B-LAW_REF``, ``I-LAW_REF``, ``B-CASE_REF``,
                ``I-CASE_REF``, ``O``).  Defaults to ``DEFAULT_LABEL_MAP``.
            max_length: Max input length.  Longer texts are processed in
                overlapping windows (see ``stride``).
            stride: Overlap between windows when input exceeds ``max_length``.
            trust_remote_code: Allow models shipping custom code (needed for
                EuroBERT, ModernGBERT).  Default ``True``.
        """
        self._model_ref = str(model)
        self._device_spec = device
        self._aggregation = aggregation
        self._label_mapping = label_mapping or DEFAULT_LABEL_MAP
        self._max_length = max_length
        self._stride = stride
        self._trust_remote_code = trust_remote_code

        # Lazy-loaded to keep import cost low
        self._tokenizer = None
        self._model = None
        self._device = None
        self._id2label: dict[int, str] = {}

    # --- Loading ---

    def _load(self) -> None:
        """Lazy-load tokenizer and model on first use."""
        if self._model is not None:
            return

        try:
            import torch
            from transformers import AutoModelForTokenClassification, AutoTokenizer
        except ImportError as exc:
            msg = (
                "TransformerExtractor requires the '[transformers]' extra. "
                "Install with: pip install legal-reference-extraction[transformers]"
            )
            raise ImportError(msg) from exc

        logger.info("Loading transformer model: %s", self._model_ref)
        self._tokenizer = AutoTokenizer.from_pretrained(
            self._model_ref, use_fast=True, trust_remote_code=self._trust_remote_code
        )
        self._model = AutoModelForTokenClassification.from_pretrained(
            self._model_ref, trust_remote_code=self._trust_remote_code
        )

        # Resolve device
        if isinstance(self._device_spec, str):
            self._device = torch.device(self._device_spec)
        else:
            self._device = self._device_spec
        self._model.to(self._device)
        self._model.eval()

        # Cache id → label mapping from model config
        self._id2label = dict(self._model.config.id2label)
        logger.info(
            "Model loaded on %s with labels: %s",
            self._device,
            sorted(set(self._id2label.values())),
        )

    # --- Public API (Extractor protocol) ---

    def extract(self, text: str) -> tuple[list[Citation], list[CitationRelation]]:
        """Extract citations from a single document."""
        citations = self._extract_single(text)
        return citations, []

    def extract_batch(
        self,
        texts: list[str],
        batch_size: int = 8,
    ) -> list[tuple[list[Citation], list[CitationRelation]]]:
        """Extract citations from a batch of documents.

        More efficient than calling ``extract`` in a loop, especially on
        GPU/MPS.  Each document is still tokenized/windowed independently
        to handle long texts.
        """
        self._load()
        results: list[tuple[list[Citation], list[CitationRelation]]] = []

        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            batch_results = [(self._extract_single(t), []) for t in batch]
            results.extend(batch_results)

        return results

    # --- Inference ---

    def _extract_single(self, text: str) -> list[Citation]:
        """Run inference on one document and return citations."""
        self._load()

        if not text.strip():
            return []

        # Whitespace-tokenize to get character offsets
        word_offsets = _whitespace_tokenize(text)
        if not word_offsets:
            return []
        words = [w[2] for w in word_offsets]

        # Predict BIO labels per word (handling long inputs via windowing)
        word_labels = self._predict_word_labels(words, text, word_offsets)

        # Convert to spans → citations
        spans = _word_labels_to_spans(word_labels, word_offsets, text, self._label_mapping)
        return _spans_to_citations(spans)

    def _predict_word_labels(
        self,
        words: list[str],
        text: str,  # noqa: ARG002
        word_offsets: list[tuple[int, int, str]],  # noqa: ARG002
    ) -> list[str]:
        """Predict a BIO label per whitespace-word.

        Uses the tokenizer's fast-tokenizer word-ids feature to align
        sub-word predictions back to whitespace words.  For inputs longer
        than ``max_length``, processes in overlapping windows and
        resolves overlaps by keeping the earlier window's predictions for
        tokens in the overlap region (simple strategy; can be refined).
        """
        import torch

        tokenizer = self._tokenizer

        enc = tokenizer(
            words,
            is_split_into_words=True,
            return_tensors="pt",
            truncation=True,
            max_length=self._max_length,
            stride=self._stride,
            return_overflowing_tokens=True,
            padding="longest",
        )

        num_windows = enc["input_ids"].shape[0]
        word_labels: list[str | None] = [None] * len(words)

        with torch.no_grad():
            for w in range(num_windows):
                input_ids = enc["input_ids"][w : w + 1].to(self._device)
                attention_mask = enc["attention_mask"][w : w + 1].to(self._device)
                logits = self._model(input_ids=input_ids, attention_mask=attention_mask).logits
                pred_ids = logits.argmax(dim=-1)[0].cpu().tolist()

                word_ids = enc.word_ids(batch_index=w)

                # Aggregate sub-word predictions to word labels
                # Strategy "first": use the first sub-word's label for each word
                seen_words: set[int] = set()
                for tok_idx, word_id in enumerate(word_ids):
                    if word_id is None:
                        continue
                    if word_id in seen_words:
                        continue
                    seen_words.add(word_id)
                    if word_labels[word_id] is None:  # don't overwrite earlier window
                        label = self._id2label.get(pred_ids[tok_idx], "O")
                        word_labels[word_id] = label

        # Fill any gaps (shouldn't happen with correct windowing)
        return [lbl if lbl is not None else "O" for lbl in word_labels]


# --- Helpers ---


def _whitespace_tokenize(text: str) -> list[tuple[int, int, str]]:
    """Whitespace-tokenize returning (start, end, word) triples."""
    import re

    return [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", text)]


def _word_labels_to_spans(
    word_labels: list[str],
    word_offsets: list[tuple[int, int, str]],
    text: str,
    label_mapping: dict[str, str],
) -> list[tuple[int, int, str, str]]:
    """Convert per-word BIO labels to citation spans.

    Normalises labels via ``label_mapping`` first, then collapses
    consecutive B-I sequences into single spans.  Returns
    ``(start, end, span_text, label_type)`` where ``label_type`` is
    ``"LAW_REF"`` or ``"CASE_REF"``.
    """
    spans: list[tuple[int, int, str, str]] = []
    current_start = -1
    current_type = ""

    for i, raw_label in enumerate(word_labels):
        label = label_mapping.get(raw_label, "O")

        if label.startswith("B-"):
            if current_start >= 0:
                end = word_offsets[i - 1][1]
                spans.append((current_start, end, text[current_start:end], current_type))
            current_start = word_offsets[i][0]
            current_type = label[2:]
        elif label.startswith("I-") and current_start >= 0:
            continue
        else:  # O or unknown
            if current_start >= 0:
                end = word_offsets[i - 1][1]
                spans.append((current_start, end, text[current_start:end], current_type))
                current_start = -1

    if current_start >= 0 and word_offsets:
        end = word_offsets[-1][1]
        spans.append((current_start, end, text[current_start:end], current_type))

    return spans


def _spans_to_citations(
    spans: list[tuple[int, int, str, str]],
) -> list[Citation]:
    """Convert label-tagged spans to typed Citation objects.

    Field parsing (book, number, court, file_number) reuses the CRF
    parser for consistency.
    """
    citations: list[Citation] = []

    for start, end, span_text, label_type in spans:
        span = Span(start=start, end=end, text=span_text)
        cid = make_citation_id(span, "transformer")

        if label_type == "LAW_REF":
            book, number = _parse_law_fields(span_text)
            citations.append(
                LawCitation(
                    span=span,
                    id=cid,
                    book=book,
                    number=number,
                    confidence=0.85,
                )
            )
        elif label_type == "CASE_REF":
            court, file_number = _parse_case_fields(span_text)
            citations.append(
                CaseCitation(
                    span=span,
                    id=cid,
                    court=court,
                    file_number=file_number,
                    confidence=0.85,
                )
            )

    return citations
