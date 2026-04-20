"""CRF-based citation extraction engine (Stream F).

Uses ``sklearn-crfsuite`` to predict BIO tags over whitespace tokens,
then converts predicted spans to typed ``Citation`` objects.  Field
parsing (book, number, court, file_number) is delegated to the regex
parser for precision.

The CRF is trained on the benchmark's train split and complements the
regex engine by catching citation patterns the regex misses.

Requires the ``[ml]`` extra: ``pip install legal-reference-extraction[ml]``
"""

from __future__ import annotations

import importlib.resources
import logging
import pickle
import re
from pathlib import Path

from refex.citations import (
    CaseCitation,
    Citation,
    CitationRelation,
    LawCitation,
    Span,
    make_citation_id,
)

logger = logging.getLogger(__name__)

# --- Feature extraction ---

# Known court register codes (from file_number_codes.csv)
_REGISTER_CODES: set[str] | None = None


def _get_register_codes() -> set[str]:
    global _REGISTER_CODES
    if _REGISTER_CODES is not None:
        return _REGISTER_CODES
    try:
        data_files = importlib.resources.files("refex") / "data"
        code_path = data_files / "file_number_codes.csv"
        with importlib.resources.as_file(code_path) as path:
            codes = set()
            with open(path) as f:
                for line in f:
                    code = line.strip().split(",", 1)[0].strip()
                    code = re.sub(r"\s*\(.*?\)", "", code)
                    if code:
                        codes.add(code)
            _REGISTER_CODES = codes
    except Exception:
        _REGISTER_CODES = set()
    return _REGISTER_CODES


def _word_shape(word: str) -> str:
    """Map word to a shape string (Xx for mixed, XX for upper, etc.)."""
    if word.isdigit():
        return "d" * min(len(word), 4)
    if word.isupper():
        return "XX"
    if word.islower():
        return "xx"
    if word[0].isupper():
        return "Xx"
    return "other"


def extract_features(tokens: list[str], i: int) -> dict[str, str | bool]:
    """Extract features for a single token at position i."""
    word = tokens[i]
    features: dict[str, str | bool] = {
        "bias": True,
        "word.lower": word.lower(),
        "word.shape": _word_shape(word),
        "word.len": str(min(len(word), 10)),
        "word.isdigit": word.isdigit(),
        "word.isupper": word.isupper(),
        "word.istitle": word.istitle(),
        "word.has_slash": "/" in word,
        "word.has_dot": "." in word,
        "word.has_hyphen": "-" in word,
        "word.prefix2": word[:2].lower(),
        "word.suffix2": word[-2:].lower() if len(word) >= 2 else word.lower(),
        "word.suffix3": word[-3:].lower() if len(word) >= 3 else word.lower(),
        # Legal-specific features
        "word.is_section": word in ("§", "§§"),
        "word.is_art": word.lower().startswith("art"),
        "word.is_abs": word.lower() in ("abs.", "abs"),
        "word.is_nr": word.lower() in ("nr.", "nr"),
        "word.is_satz": word.lower() in ("satz", "s."),
        "word.is_ivm": word.lower() in ("i.v.m.", "ivm"),
        "word.is_register": word in _get_register_codes(),
        "word.looks_like_year": bool(re.match(r"^\d{2,4}$", word)),
        "word.looks_like_fn": bool(re.match(r"^\d+/\d{2}$", word)),
    }

    # Context: previous token
    if i > 0:
        prev = tokens[i - 1]
        features["prev.lower"] = prev.lower()
        features["prev.is_section"] = prev in ("§", "§§")
        features["prev.isdigit"] = prev.isdigit()
        features["prev.isupper"] = prev.isupper()
        features["prev.shape"] = _word_shape(prev)
    else:
        features["BOS"] = True

    # Context: next token
    if i < len(tokens) - 1:
        nxt = tokens[i + 1]
        features["next.lower"] = nxt.lower()
        features["next.is_section"] = nxt in ("§", "§§")
        features["next.isdigit"] = nxt.isdigit()
        features["next.isupper"] = nxt.isupper()
        features["next.shape"] = _word_shape(nxt)
    else:
        features["EOS"] = True

    # Wider context (2 tokens)
    if i > 1:
        features["prev2.lower"] = tokens[i - 2].lower()
    if i < len(tokens) - 2:
        features["next2.lower"] = tokens[i + 2].lower()

    return features


def tokenize(text: str) -> list[tuple[int, int, str]]:
    """Whitespace-tokenize text, returning (start, end, token) triples."""
    return [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", text)]


def text_to_features(text: str) -> tuple[list[dict], list[tuple[int, int, str]]]:
    """Tokenize and extract features for all tokens."""
    token_spans = tokenize(text)
    tokens = [t[2] for t in token_spans]
    features = [extract_features(tokens, i) for i in range(len(tokens))]
    return features, token_spans


# --- BIO → Citation conversion ---


def bio_to_spans(
    labels: list[str],
    token_spans: list[tuple[int, int, str]],
    text: str,
) -> list[tuple[int, int, str, str]]:
    """Convert BIO labels to (start, end, span_text, label_type) tuples."""
    spans: list[tuple[int, int, str, str]] = []
    current_start = -1
    current_type = ""

    for i, label in enumerate(labels):
        if label.startswith("B-"):
            if current_start >= 0:
                end = token_spans[i - 1][1]
                spans.append((current_start, end, text[current_start:end], current_type))
            current_start = token_spans[i][0]
            current_type = label[2:]  # e.g., "LAW_REF"
        elif label.startswith("I-") and current_start >= 0:
            pass  # continue current span
        else:
            if current_start >= 0:
                end = token_spans[i - 1][1]
                spans.append((current_start, end, text[current_start:end], current_type))
                current_start = -1

    # Handle span at end of sequence
    if current_start >= 0:
        end = token_spans[-1][1]
        spans.append((current_start, end, text[current_start:end], current_type))

    return spans


def spans_to_citations(
    spans: list[tuple[int, int, str, str]],
) -> list[Citation]:
    """Convert BIO-detected spans to typed Citation objects.

    The CRF only detects span boundaries — field parsing (book, number,
    court, file_number) is done with simple heuristics here.
    """
    citations: list[Citation] = []

    for start, end, span_text, label_type in spans:
        span = Span(start=start, end=end, text=span_text)
        cid = make_citation_id(span, "crf")

        if label_type == "LAW_REF":
            book, number = _parse_law_fields(span_text)
            citations.append(
                LawCitation(
                    span=span,
                    id=cid,
                    book=book,
                    number=number,
                    confidence=0.8,
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
                    confidence=0.8,
                )
            )

    return citations


def _parse_law_fields(text: str) -> tuple[str | None, str | None]:
    """Extract book and number from a law citation span."""
    # Try: "§ 433 Abs. 1 BGB" → book=bgb, number=433
    m = re.match(r"§§?\s*(\d+\s?[a-z]?)", text)
    number = m.group(1).strip() if m else None

    # Book is typically the last word if it looks like an abbreviation
    words = text.split()
    book = None
    if words:
        last = words[-1]
        if re.match(r"^[A-ZÄÖÜ]", last) and not last.isdigit() and last not in ("§", "§§", "Abs.", "Nr.", "S."):
            book = last.lower()

    return book, number


def _parse_case_fields(text: str) -> tuple[str | None, str | None]:
    """Extract court and file_number from a case citation span."""
    # File number pattern: "VIII ZR 295/01" or "10 C 23.12" — chamber is
    # either Roman numerals (I-X) or digits, followed by code + number/year.
    fn_match = re.search(r"(?:[IVX]+|\d+)\s+[A-Z][A-Za-z]{0,4}\s+\d+[/.]\d{2,4}", text)
    file_number = fn_match.group(0) if fn_match else None

    # Court is usually at the beginning before "Urteil"/"Beschluss"/date
    court = None
    court_match = re.match(r"^([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\s-]+?)(?:,|\s+(?:Urteil|Beschl|vom|\d))", text)
    if court_match:
        court = court_match.group(1).strip()

    return court, file_number


# --- Training ---


def build_training_data(
    data_dir: Path | None = None,
    split: str = "train",
    limit: int | None = None,
    skip_empty: bool = True,
) -> tuple[list[list[dict]], list[list[str]]]:
    """Build CRF training data from the benchmark dataset.

    Args:
        data_dir: Benchmark dataset directory.
        split: Which split to load.
        limit: Process at most this many documents.
        skip_empty: Skip documents with no citations (reduces noise + size).

    Returns (X, y) where X is a list of feature-dict sequences and
    y is a list of BIO label sequences.
    """
    from benchmarks.datasets import load_dataset

    ds = load_dataset(data_dir, split=split)

    X: list[list[dict]] = []
    y: list[list[str]] = []

    total_docs = len(ds.documents)
    logger.info("Scanning %d documents (skip_empty=%s)", total_docs, skip_empty)

    for doc_idx, doc in enumerate(ds.documents):
        if limit is not None and len(X) >= limit:
            break

        ann = ds.annotations.get(doc.doc_id)
        if not ann:
            continue

        citations = [c for c in ann.citations if c.type in ("law", "case")]
        if skip_empty and not citations:
            continue

        text = doc.text
        token_spans = tokenize(text)
        if not token_spans:
            continue

        tokens = [t[2] for t in token_spans]
        features = [extract_features(tokens, i) for i in range(len(tokens))]

        # Build gold labels
        labels = ["O"] * len(token_spans)
        for cit in citations:
            label = cit.type.upper() + "_REF"
            first = True
            for i, (ts, te, _) in enumerate(token_spans):
                if te <= cit.span.start:
                    continue
                if ts >= cit.span.end:
                    break
                labels[i] = f"B-{label}" if first else f"I-{label}"
                first = False

        X.append(features)
        y.append(labels)

        if len(X) % 100 == 0:
            logger.info(
                "Collected %d/%s docs (scanned %d/%d)",
                len(X),
                limit or "all",
                doc_idx + 1,
                total_docs,
            )

    logger.info("Training data ready: %d docs, %d total tokens", len(X), sum(len(x) for x in X))
    return X, y


def train_crf(
    data_dir: Path | None = None,
    output_path: Path | None = None,
    c1: float = 0.1,
    c2: float = 0.1,
    max_iterations: int = 50,
    limit: int | None = None,
    algorithm: str = "lbfgs",
) -> Path:
    """Train a CRF model and save it to disk.

    Uses ``pycrfsuite.Trainer`` directly with streaming ``append()``
    so the full training set doesn't need to fit in Python memory —
    features are flushed to the C-side CRFsuite buffer per document.

    Args:
        data_dir: Benchmark dataset directory.
        output_path: Where to save the model. Defaults to
            ``src/refex/data/crf_model.pkl``.
        c1: L1 regularization coefficient (lbfgs only).
        c2: L2 regularization coefficient.
        max_iterations: Maximum training iterations.
        limit: Train on at most this many documents (None = all).
        algorithm: Training algorithm: "lbfgs" (default, best F1 but
            memory-hungry) or "l2sgd" (stochastic gradient descent,
            much less memory, scales to larger datasets).

    Returns:
        Path to the saved model file.
    """
    import pycrfsuite
    from benchmarks.datasets import load_dataset

    if output_path is None:
        output_path = Path(__file__).parent.parent / "data" / "crf_model.pkl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # CRFsuite saves in its own binary format; we write a pickle wrapper
    # around the file path so CRFExtractor can load it.
    crfsuite_path = str(output_path.with_suffix(".crfsuite"))

    params = {
        "c2": c2,
        "max_iterations": max_iterations,
        "feature.possible_transitions": 1,
    }
    if algorithm == "lbfgs":
        params["c1"] = c1

    logger.info("Streaming training data to CRFsuite (algorithm=%s, limit=%s)", algorithm, limit)
    trainer = pycrfsuite.Trainer(algorithm=algorithm, params=params, verbose=True)

    ds = load_dataset(data_dir, split="train")
    total_docs = len(ds.documents)
    logger.info("Scanning %d documents (skip_empty=True)", total_docs)

    appended = 0
    total_tokens = 0
    for doc_idx, doc in enumerate(ds.documents):
        if limit is not None and appended >= limit:
            break

        ann = ds.annotations.get(doc.doc_id)
        if not ann:
            continue

        citations = [c for c in ann.citations if c.type in ("law", "case")]
        if not citations:
            continue

        text = doc.text
        token_spans = tokenize(text)
        if not token_spans:
            continue

        tokens = [t[2] for t in token_spans]
        features = [extract_features(tokens, i) for i in range(len(tokens))]

        labels = ["O"] * len(token_spans)
        for cit in citations:
            label = cit.type.upper() + "_REF"
            first = True
            for i, (ts, te, _) in enumerate(token_spans):
                if te <= cit.span.start:
                    continue
                if ts >= cit.span.end:
                    break
                labels[i] = f"B-{label}" if first else f"I-{label}"
                first = False

        # Convert feature dicts to pycrfsuite's string format
        # (each feature is either "key" for boolean or "key=value" for string)
        crf_features = [_dict_to_crfsuite_features(f) for f in features]
        trainer.append(crf_features, labels)

        # Free local refs immediately after append — the data is now
        # in the C-side buffer.
        del features, crf_features, labels
        appended += 1
        total_tokens += len(token_spans)

        if appended % 200 == 0:
            logger.info(
                "Streamed %d/%s docs (scanned %d/%d, %d tokens)",
                appended,
                limit or "all",
                doc_idx + 1,
                total_docs,
                total_tokens,
            )

    logger.info("Training data ready: %d docs, %d tokens. Fitting...", appended, total_tokens)
    logger.info("Fitting CRF: algorithm=%s c1=%.3f c2=%.3f max_iter=%d", algorithm, c1, c2, max_iterations)
    trainer.train(crfsuite_path)

    # Wrap the path in a pickle for CRFExtractor's loader
    with open(output_path, "wb") as f:
        pickle.dump({"format": "crfsuite", "path": crfsuite_path}, f)

    size_kb = Path(crfsuite_path).stat().st_size / 1024
    logger.info("Model saved to %s (%.1f KB)", crfsuite_path, size_kb)
    return output_path


def _dict_to_crfsuite_features(d: dict) -> list[str]:
    """Convert a feature dict to pycrfsuite's list-of-strings format."""
    out = []
    for k, v in d.items():
        if v is True:
            out.append(k)
        elif v is False:
            continue
        else:
            out.append(f"{k}={v}")
    return out


# --- Extractor engine ---


class CRFExtractor:
    """CRF-based citation extractor implementing the ``Extractor`` protocol.

    Loads a pre-trained CRF model and predicts BIO tags over whitespace
    tokens.  Detected spans are converted to ``LawCitation`` or
    ``CaseCitation`` objects.

    Usage::

        extractor = CRFExtractor()  # loads default bundled model
        citations, relations = extractor.extract(text)
    """

    def __init__(self, model_path: Path | str | None = None):
        if model_path is None:
            model_path = Path(__file__).parent.parent / "data" / "crf_model.pkl"
        self._model_path = Path(model_path)
        self._tagger = None  # pycrfsuite.Tagger or sklearn_crfsuite.CRF
        self._backend = None  # "crfsuite" or "sklearn"

    def _load_model(self):
        if self._tagger is not None:
            return
        if not self._model_path.exists():
            raise FileNotFoundError(
                f"CRF model not found at {self._model_path}. Train it first: python -m refex.engines.crf --train"
            )
        with open(self._model_path, "rb") as f:
            obj = pickle.load(f)

        # New format: dict with path to .crfsuite file (from pycrfsuite.Trainer)
        if isinstance(obj, dict) and obj.get("format") == "crfsuite":
            import pycrfsuite

            crfsuite_path = obj["path"]
            # If path is relative, resolve against the pickle's directory
            p = Path(crfsuite_path)
            if not p.is_absolute():
                p = self._model_path.parent / p.name
            if not p.exists():
                # Try next to the pickle
                p = self._model_path.with_suffix(".crfsuite")
            self._tagger = pycrfsuite.Tagger()
            self._tagger.open(str(p))
            self._backend = "crfsuite"
        else:
            # Legacy: pickled sklearn_crfsuite.CRF
            self._tagger = obj
            self._backend = "sklearn"

    def extract(self, text: str) -> tuple[list[Citation], list[CitationRelation]]:
        """Extract citations from plain text using CRF tagging."""
        self._load_model()

        features, token_spans = text_to_features(text)
        if not features:
            return [], []

        if self._backend == "crfsuite":
            # pycrfsuite expects list-of-strings features
            crf_features = [_dict_to_crfsuite_features(f) for f in features]
            labels = list(self._tagger.tag(crf_features))
        else:
            labels = self._tagger.predict_single(features)

        spans = bio_to_spans(labels, token_spans, text)
        citations = spans_to_citations(spans)

        return citations, []


# --- CLI for training ---


def _setup_logging(log_file: Path | None = None) -> None:
    """Configure logging to both stderr and optionally a file.

    Important for long-running training jobs that may be killed —
    the log file survives and shows where we got stuck.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Clear any existing handlers
    root.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    root.addHandler(stream_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
        logger.info("Logging to %s", log_file)


def main():
    import argparse
    import sys
    import time

    parser = argparse.ArgumentParser(description="Train or evaluate the CRF citation extractor.")
    parser.add_argument("--train", action="store_true", help="Train the CRF model")
    parser.add_argument("--evaluate", action="store_true", help="Evaluate on validation split")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None, help="Model output path")
    parser.add_argument("--c1", type=float, default=0.1, help="L1 regularization")
    parser.add_argument("--c2", type=float, default=0.1, help="L2 regularization")
    parser.add_argument("--max-iter", type=int, default=50)
    parser.add_argument("--limit", type=int, default=None, help="Limit training to N docs")
    parser.add_argument(
        "--algorithm",
        choices=["lbfgs", "l2sgd"],
        default="lbfgs",
        help="Training algorithm: lbfgs (best F1, high memory) or l2sgd (lower memory, scales better)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("logs/crf.log"),
        help="Log file path (default: logs/crf.log; use empty string to disable)",
    )
    args = parser.parse_args()

    log_file = args.log_file if args.log_file and str(args.log_file) else None
    _setup_logging(log_file)

    if args.train:
        t0 = time.perf_counter()
        model_path = train_crf(
            data_dir=args.data_dir,
            output_path=args.output,
            c1=args.c1,
            c2=args.c2,
            max_iterations=args.max_iter,
            limit=args.limit,
            algorithm=args.algorithm,
        )
        dt = time.perf_counter() - t0
        print(f"Training completed in {dt:.1f}s. Model: {model_path}")

    if args.evaluate:
        from benchmarks.datasets import load_dataset

        ext = CRFExtractor(model_path=args.output)
        ds = load_dataset(args.data_dir, split="validation")

        total_pred = 0
        total_gold = 0
        total_tp = 0
        t0 = time.perf_counter()

        for doc in ds.documents:
            ann = ds.annotations.get(doc.doc_id)
            if not ann:
                continue

            gold_cits = [c for c in ann.citations if c.type in ("law", "case")]
            pred_cits, _ = ext.extract(doc.text)

            gold_spans = {(c.span.start, c.span.end) for c in gold_cits}
            pred_spans = {(c.span.start, c.span.end) for c in pred_cits}

            total_gold += len(gold_spans)
            total_pred += len(pred_spans)
            total_tp += len(gold_spans & pred_spans)

        dt = time.perf_counter() - t0
        p = total_tp / total_pred if total_pred else 0
        r = total_tp / total_gold if total_gold else 0
        f1 = 2 * p * r / (p + r) if (p + r) else 0
        print(f"Validation: P={p:.3f} R={r:.3f} F1={f1:.3f} ({len(ds.documents)} docs, {dt:.1f}s)")

    if not args.train and not args.evaluate:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
