# Transformer Training Guide (Stream G)

**Status:** engine code complete; training is user-driven on MPS/GPU.
**Builds on:** [`implementation_plan.md`](./implementation_plan.md) §G,
[`src/refex/engines/transformer.py`](../../src/refex/engines/transformer.py),
[`src/refex/serializers.py`](../../src/refex/serializers.py) (`to_hf_bio`).

---

## 0. Scope

This doc covers fine-tuning a token-classification model for German legal
citation detection, to be loaded by the `TransformerExtractor` engine.

**In scope:**
- Exporting benchmark annotations to HuggingFace BIO format
- Choosing a base model
- Training with the HuggingFace `Trainer` API on MPS / CUDA
- Evaluating against the benchmark (`make bench` with `--engine transformer`)
- Pushing the trained model to Hugging Face Hub

**Out of scope (for this doc):**
- Building the benchmark dataset (see [`benchmark_dataset_spec.md`](./benchmark_dataset_spec.md))
- LoRA / PEFT variants — add later if full fine-tuning hits memory limits
- Instruction-tuned generative models (not a fit for token classification)

---

## 1. Data Pipeline

### 1.1 Export BIO training data

The `to_hf_bio` serializer in `refex.serializers` produces the canonical
BIO format the transformer engine expects.  Writing a JSONL file for the
HuggingFace `datasets` library looks like this:

```python
import json
from pathlib import Path
from benchmarks.datasets import load_dataset
from refex.citations import ExtractionResult, LawCitation, CaseCitation, Span
from refex.serializers import to_hf_bio

ds = load_dataset(split="train")  # benchmark dataset
out = Path("data/hf_bio/train.jsonl")
out.parent.mkdir(parents=True, exist_ok=True)

with open(out, "w", encoding="utf-8") as f:
    for doc in ds.documents:
        ann = ds.annotations.get(doc.doc_id)
        if not ann:
            continue
        # Build an ExtractionResult from gold annotations
        cits = []
        for c in ann.citations:
            if c.type == "law":
                cits.append(LawCitation(
                    span=Span(c.span.start, c.span.end, c.span.text),
                    book=c.book, number=c.number))
            elif c.type == "case":
                cits.append(CaseCitation(
                    span=Span(c.span.start, c.span.end, c.span.text),
                    court=c.court, file_number=c.file_number))
        result = ExtractionResult(citations=cits)
        record = to_hf_bio(result, doc.text)
        record["doc_id"] = doc.doc_id
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
```

Repeat for `split="validation"` → `data/hf_bio/validation.jsonl`.

Each record has:

```json
{
  "doc_id": "bgh-2003-03-19-...",
  "tokens": ["Die", "Kostenentscheidung", "beruht", "auf", "§", "154", "Abs.", "1", "VwGO", "..."],
  "ner_tags": ["O", "O", "O", "O", "B-LAW_REF", "I-LAW_REF", "I-LAW_REF", "I-LAW_REF", "I-LAW_REF", "..."]
}
```

### 1.2 Tokenization alignment

The transformer takes sub-word tokens, not whitespace tokens.  During
training, the HuggingFace pattern is: tokenize with
`is_split_into_words=True` and use `word_ids` to project word-level BIO
tags onto sub-word tokens.  Standard approach:

- **First-token strategy**: label the first sub-word of each word; set
  other sub-words to `-100` (ignored by loss).  Simplest and matches our
  inference-time aggregation in `TransformerExtractor`.
- **All-token strategy**: label every sub-word (B- for first, I- for
  continuation).  Slightly better recall, but needs a matching inference
  strategy.

Use the first-token strategy to match our inference code.

---

## 2. Base Model Candidates

Pick based on compute budget and domain match.  All are PyTorch-compatible
via `transformers` and support token classification out of the box.

| Model | Params | VRAM (fp32) | Domain | License | Notes |
|-------|--------|------------|--------|---------|-------|
| **`PaDaS-Lab/gbert-legal-ner`** | 110M | ~2 GB | German legal NER | MIT | **Recommended default.** Already fine-tuned on legal NER; shortest path to results. Label schema may need mapping. |
| `deepset/gbert-base` | 110M | ~2 GB | General German | MIT | Strong general-purpose German BERT. Needs fine-tuning from scratch for our schema. |
| `deepset/gbert-large` | 335M | ~5 GB | General German | MIT | Larger version. Better quality, slower inference. |
| `dbmdz/bert-base-german-uncased` | 110M | ~2 GB | General German | MIT | Older but very widely used baseline. |
| `xlm-roberta-base` | 280M | ~4 GB | Multilingual | MIT | Useful if you later extend beyond German. |
| `microsoft/mdeberta-v3-base` | 280M | ~4 GB | Multilingual | MIT | Often best on NER among ~300M-param models. |
| `stefan-it/german-gpt2` or similar | — | — | — | — | **Not recommended** — decoder-only models are poor for token classification. |

### 2.1 Suggested order

1. **Start with `deepset/gbert-base`** — clean slate, easy to reproduce.
   Expected exact-span F1: 0.85–0.92 on the validation split after 3–5
   epochs.
2. **Try `PaDaS-Lab/gbert-legal-ner` as a warm start** — it's already
   seen legal German, so fine-tuning from its checkpoint converges
   faster.  Requires aligning the label head (remap or replace the final
   classification layer to match our 5 labels: `O`, `B-LAW_REF`,
   `I-LAW_REF`, `B-CASE_REF`, `I-CASE_REF`).
3. **If you need headroom**, `gbert-large` or `mdeberta-v3-base` for the
   final model.

---

## 3. Hyperparameters

### 3.1 Baseline recipe (gbert-base)

| Hyperparameter | Value | Notes |
|----------------|-------|-------|
| **Learning rate** | `3e-5` | Standard BERT fine-tuning range; try `2e-5` / `5e-5` for sweeps. |
| **Batch size (per device)** | `16` (MPS) / `32` (CUDA) | MPS has smaller usable VRAM; 16 is safer. |
| **Gradient accumulation** | `2` | Effective batch `32`/`64`. Bumps up if VRAM tight. |
| **Epochs** | `3–5` | Token classification converges fast; early-stop on val F1. |
| **Warmup** | `10%` of total steps | Linear warmup then linear decay. |
| **Weight decay** | `0.01` | Standard. |
| **Max sequence length** | `512` | Matches inference-side windowing. |
| **Stride (for long docs)** | `128` | Overlap between windows; matches inference. |
| **LR scheduler** | `linear` | Transformers default. |
| **Mixed precision** | `fp16` (CUDA) / `fp32` (MPS) | MPS fp16 is still flaky as of transformers 4.45; check for NaN loss. |
| **Seed** | `42` | For reproducibility. |

### 3.2 Label weighting

Class imbalance is real: >90% of tokens are `O`.  Options:

- **Default**: do nothing.  Works fine for BIO on NER tasks in our data
  size range (8K docs, ~15M tokens).
- **Focal loss** (`gamma=2.0`): if you see the model over-predicting `O`.
  Not in stock Trainer; wrap the loss.
- **Class weights**: `class_weights=[1.0, 5.0, 5.0, 5.0, 5.0]` where
  non-`O` classes get higher weight.  Easy to add via a custom
  `compute_loss`.

### 3.3 Evaluation during training

Use the HuggingFace `Trainer` with `evaluation_strategy="epoch"` and
`load_best_model_at_end=True`.  `metric_for_best_model` = span-level F1
(not per-token).  Compute with `seqeval` which understands BIO:

```python
from seqeval.metrics import classification_report, f1_score

def compute_metrics(pred):
    preds = pred.predictions.argmax(-1)
    labels = pred.label_ids
    # Mask out -100 (sub-word continuations)
    true = [[id2label[l] for l in lab if l != -100] for lab in labels]
    predicted = [
        [id2label[p] for p, l in zip(ps, lab) if l != -100]
        for ps, lab in zip(preds, labels)
    ]
    return {
        "f1": f1_score(true, predicted),
        "report": classification_report(true, predicted),
    }
```

### 3.4 Optimizer

Default to `AdamW` (HuggingFace Trainer's default).  For MPS, use
`adafactor` if you see memory issues with AdamW's optimizer state.

---

## 4. Training on MPS (Apple Silicon)

```bash
# Install PyTorch with MPS support (should be default on Apple Silicon)
pip install torch torchvision
pip install "legal-reference-extraction[ml]"
pip install datasets seqeval accelerate

# Train
python scripts/train_transformer.py \
    --model deepset/gbert-base \
    --train data/hf_bio/train.jsonl \
    --eval data/hf_bio/validation.jsonl \
    --output models/refex-transformer \
    --device mps \
    --epochs 4 \
    --batch-size 16 \
    --learning-rate 3e-5
```

**MPS gotchas:**

- `fp16` is unreliable on MPS with transformers < 4.45 — expect NaN loss.
  Stay on fp32 or upgrade transformers.
- Peak memory is typically 2–3× model params.  `gbert-base` (110M) needs
  ~6 GB VRAM in fp32 with batch 16.
- `num_workers > 0` for the DataLoader can crash on MPS — set to `0`.
- Some ops fall back to CPU silently; watch the `PYTORCH_ENABLE_MPS_FALLBACK=1`
  behavior.

Expected wall-clock on M2 Pro: **~2–4 hours** for 3 epochs on 8K docs
with sequence length 512.

---

## 5. Training on CUDA (NVIDIA)

Same script, `--device cuda`.  Use `--bf16` on Ampere+ (A100, RTX 30-series
or newer), otherwise `--fp16`.  Typical wall-clock on a single A10 /
RTX 4090: **~30–60 minutes** for 3 epochs.

```bash
python scripts/train_transformer.py \
    --model deepset/gbert-base \
    --train data/hf_bio/train.jsonl \
    --eval data/hf_bio/validation.jsonl \
    --output models/refex-transformer \
    --device cuda \
    --bf16 \
    --epochs 4 \
    --batch-size 32
```

---

## 6. Loading the Trained Model

The transformer engine accepts any directory `save_pretrained()` wrote to:

```python
from refex.engines.transformer import TransformerExtractor

ext = TransformerExtractor(model="models/refex-transformer", device="cuda")
result = ext.extract(text)
```

Or via the benchmark:

```bash
REFEX_TRANSFORMER_MODEL=models/refex-transformer \
    make bench-transformer BENCH_ARGS="-n 100"
```

(Currently the model path is hard-coded to `DEFAULT_MODEL`; add an env
var / CLI flag if needed.)

---

## 7. Expected Results

Target metrics on the 821-doc validation split, measured with the
benchmark's span F1 metric:

| Engine | Span F1 exact | Span F1 overlap | Throughput (CPU) |
|--------|---------------|-----------------|------------------|
| Regex (current) | 0.734 | 0.887 | ~300 docs/s |
| Regex + CRF | ~0.75 | ~0.91 | ~200 docs/s |
| Regex + Transformer | **0.80+** | **0.93+** | ~20–50 docs/s |
| Transformer alone | 0.85–0.92 | 0.93–0.95 | ~20–50 docs/s |

Transformer throughput on GPU: **1,000+ docs/s** with batching.

---

## 8. Push to Hugging Face Hub

After satisfactory metrics on the validation set and one-shot evaluation
on the test set:

```python
from transformers import AutoModelForTokenClassification, AutoTokenizer

model = AutoModelForTokenClassification.from_pretrained("models/refex-transformer")
tokenizer = AutoTokenizer.from_pretrained("models/refex-transformer")

model.push_to_hub("openlegaldata/refex-transformer-de")
tokenizer.push_to_hub("openlegaldata/refex-transformer-de")
```

Add a model card noting the training data, metrics, and intended use
(German legal citation detection).

Once published, update `DEFAULT_MODEL` in
`src/refex/engines/transformer.py` to point at the published model.

---

## 9. Sanity Checks Before Training

1. **Label cardinality**: `set(chain(*ner_tags))` should equal
   `{"O", "B-LAW_REF", "I-LAW_REF", "B-CASE_REF", "I-CASE_REF"}`.
2. **Span integrity**: reconstruct a few citations from the BIO tags and
   confirm they match the gold text.
3. **Token length**: histogram of per-doc token counts.  Docs in the top
   decile (often >5000 tokens) will be split into multiple windows.
4. **Label balance**: fraction of non-`O` tokens should be 1–5%.  If
   <0.5%, check for annotation alignment bugs.
5. **No leakage**: the train/val/test split must match the benchmark's
   split.  Don't re-shuffle.

---

## 10. Failure Modes & Mitigations

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| NaN loss on MPS | `fp16` instability | Switch to `fp32` or update transformers. |
| Val F1 plateaus at 0.7 | Too few epochs / learning rate too high | Bump epochs, drop LR to 2e-5. |
| Model predicts only `O` | Class imbalance | Add class weights or focal loss. |
| OOM at batch 16 | Long sequences | Drop max_length to 384, reduce batch size. |
| Train F1 high, val F1 low | Overfitting | Add weight decay, dropout, early stopping. |
| Model finds too many false positives | Insufficient `O` examples OR aggressive regularization | Check training data, lower weight on non-`O` classes. |

---

## 11. Next Steps After Training

Once a trained model exists:

1. Add benchmark results to `optimization_log.md`.
2. Update the `DEFAULT_MODEL` in `transformer.py` to the Hub URL.
3. Consider quantization (`optimum`, `onnxruntime`) for CPU inference
   speedup.
4. Decide whether to keep the CRF engine (Stream F) as the lighter
   alternative, or deprecate it in favor of the transformer.
