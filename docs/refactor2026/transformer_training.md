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

Researched as of **April 2026**. Picks ordered by recommendation for
German legal NER.  All are encoder-style token-classification compatible
unless noted.

### 2.1 Modern era (2024–2025) — recommended

| Model | HF ID | Params | Ctx | Release | License | Fit |
|-------|-------|--------|-----|---------|---------|-----|
| **ModernGBERT-1B** | `LSX-UniWue/ModernGBERT_1B` | 1.0B | 8192 | 2025-05 | **RAIL-M (research-only)** | **SOTA German NER** (SuperGLEBer NER 0.845; +8pp over XLM-R-XL at 3.5x smaller).  8192 ctx covers most legal decisions without windowing. |
| **ModernGBERT-134M** | `LSX-UniWue/ModernGBERT_134M` | 134M | 8192 | 2025-05 | **RAIL-M (research-only)** | Best small-footprint German base.  SuperGLEBer avg 0.749 vs GBERT-base 0.718. |
| **EuroBERT-610m** | `EuroBERT/EuroBERT-610m` | 610M | 8192 | 2025-03 | Apache-2.0 | Multilingual (15 EU languages incl. German) ModernBERT-style.  Matches XLM-R-XL (3.5B) on multilingual benchmarks. **Best commercial-license option**. |
| EuroBERT-210m | `EuroBERT/EuroBERT-210m` | 210M | 8192 | 2025-03 | Apache-2.0 | Smaller multilingual alternative. |
| EuroBERT-2.1B | `EuroBERT/EuroBERT-2.1B` | 2.1B | 8192 | 2025-03 | Apache-2.0 | Tops 10/18 multilingual tasks but requires A100-80GB for full fine-tune. |

### 2.2 Classic baselines (still useful)

| Model | HF ID | Params | Ctx | License | Fit |
|-------|-------|--------|-----|---------|-----|
| `deepset/gbert-base` | `deepset/gbert-base` | 110M | 512 | MIT | Proven German BERT, widely used for reproducibility comparisons. |
| `deepset/gbert-large` | `deepset/gbert-large` | 335M | 512 | MIT | Larger German BERT. SuperGLEBer avg 0.768. |
| `microsoft/mdeberta-v3-base` | `microsoft/mdeberta-v3-base` | 278M | 512 | MIT | Strong cross-lingual NER.  No v4 / mDeBERTa-v4 exists as of 2026-04. |
| `xlm-roberta-large` | `FacebookAI/xlm-roberta-large` | 560M | 512 | MIT | Standard multilingual baseline; predictable fine-tuning behaviour. |

### 2.3 Legal-domain pre-trained

| Model | HF ID | Params | Ctx | License | Fit |
|-------|-------|--------|-----|---------|-----|
| `joelniklaus/legal-xlm-roberta-large` | — | ~560M | 512 | CC-BY-SA | Warm-started XLM-R-large with 128k legal BPE, trained on MultiLegalPile (689 GB, 24 languages incl. German).  Good starting point when training data is limited. |
| `joelniklaus/legal-xlm-roberta-base` | — | ~200M | 512 | CC-BY-SA | Smaller version of above. |
| `joelniklaus/legal-german-roberta-base` | — | ~125M | 512 | CC-BY-SA | **German-only** legal RoBERTa from MultiLegalPile. |
| `PaDaS-Lab/gbert-legal-ner` | — | 110M | 512 | Unspecified | **Task model** (already NER fine-tuned with 18 classes).  Use as baseline, not as pre-training checkpoint — the classification head would need to be replaced. |

### 2.4 Not recommended for this task

- **`answerdotai/ModernBERT-base` / `ModernBERT-large`** — despite the
  name, **trained English + code only**.  Model card explicitly warns
  about non-English performance.  Use ModernGBERT or EuroBERT instead.
- **`Alibaba-NLP/gte-multilingual-base`** — retrieval-contrastive
  embedding model, not a good NER base.  If you want the mGTE
  architecture, fine-tune from the MLM variant
  (`gte-multilingual-mlm-base`, 306M, Apache-2.0).
- **`jhu-clsp/mmBERT-base`** — the authors' own paper notes NER/POS is
  not its strong suit due to the Gemma-2 tokenizer's word-boundary
  behaviour.
- **Decoder-only LLMs** (Qwen3, Llama, SmolLM, phi, German GPT-2) —
  poor fit for token classification without substantial surgery.
- **`xlm-roberta-xl` / `xxl`** — 3.5B/10.7B params; rarely worth the
  compute over EuroBERT-2.1B or ModernGBERT-1B at 30–50% the size.
- **`nlpaueb/legal-bert-*`** — English (EU/US) legal corpora only.

### 2.5 VRAM estimates for fine-tuning

Batch size 32, sequence length 512, AdamW optimiser, mixed precision
(bf16 on Ampere+, fp16 elsewhere):

| Class | VRAM (full FT) | VRAM (LoRA) |
|-------|----------------|-------------|
| 110–210M (gbert-base, EuroBERT-210m, ModernGBERT-134M) | **6–10 GB** | 2–4 GB |
| 280–610M (mdeberta-v3, XLM-R-large, EuroBERT-610m, ModernGBERT-1B w/ grad-ckpt) | **14–22 GB** | 4–8 GB |
| 1B (ModernGBERT-1B full FT) | **24–32 GB** (A100-40 or RTX 4090 + grad-ckpt) | 6–10 GB |
| 2–3.5B (EuroBERT-2.1B, XLM-R-XL) | **40–80 GB** | 10–24 GB |
| 10B+ (XLM-R-XXL) | Not practical for NER | 30–48 GB |

ModernBERT-style models (ModernGBERT, EuroBERT) are 2–4× faster than
classic XLM-R at seq 512 and scale much better at longer contexts,
thanks to Flash-Attention 2 and local-global alternating attention.

### 2.6 Recommended training order

1. **First baseline: `deepset/gbert-base`** (110M, MIT, 512 ctx).  Easy,
   fast, reproducible.  Expected Span F1 exact: 0.85–0.92 after 3–5
   epochs.  Publish as the default model.
2. **Quality target: `EuroBERT-610m`** (Apache-2.0, 8192 ctx).  Best
   commercial-friendly model with enough capacity to saturate the
   task.  Can replace gbert-base once metrics are confirmed.
3. **Research target: `ModernGBERT-1B`** (RAIL-M research-only, 8192
   ctx).  Highest expected F1 on German NER, but license prevents
   commercial distribution.  Useful for internal evaluation and as an
   upper bound on what's achievable with German pre-training.
4. **Long-doc extension: any 8192-ctx model** (EuroBERT, ModernGBERT)
   eliminates the need for our inference-time sliding window at
   `max_length=512 / stride=128`.  Update `TransformerExtractor`'s
   defaults to `max_length=4096` or higher when using a model that
   supports it.
5. **Small-footprint edge: `EuroBERT-210m`** or `ModernGBERT-134M`
   when VRAM or CPU inference latency is tight.
6. **Legal pre-adaptation**: `joelniklaus/legal-xlm-roberta-large`
   (CC-BY-SA) if the training set is small (<5K documents) and
   pre-adapted weights matter more than a modern architecture.

### 2.7 License watch

Stream G is blocked on a commercial-friendly baseline if the model is
to be redistributed by OLDP:

- **Apache-2.0**: EuroBERT family, ModernBERT (but English-only), mmBERT.
- **MIT**: gbert-base/large, mdeberta-v3, xlm-roberta.
- **CC-BY-SA**: joelniklaus/legal-* family — requires attribution + share-alike.
- **RAIL-M (research-only)**: ModernGBERT family — cannot redistribute
  commercially without explicit permission from LSX-UniWue.

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

| Engine | Base model | Span F1 exact | Span F1 overlap | Throughput (CPU) |
|--------|------------|---------------|-----------------|------------------|
| Regex (current) | — | 0.734 | 0.887 | ~300 docs/s |
| Regex + CRF | sklearn-crfsuite | ~0.75 | ~0.91 | ~200 docs/s |
| Regex + Transformer | gbert-base | **0.80+** | **0.93+** | ~20–50 docs/s |
| Transformer alone | gbert-base | 0.85–0.92 | 0.93–0.95 | ~20–50 docs/s |
| Transformer alone | EuroBERT-610m | 0.90–0.94 | 0.94–0.97 | ~15–35 docs/s |
| Transformer alone | ModernGBERT-1B | **0.92–0.95** | **0.96–0.98** | ~8–15 docs/s (CPU), research-only |

Transformer throughput on GPU with batching: **1,000+ docs/s** for
base-sized models, **300–500 docs/s** for 1B-param models.

Long-context bonus: EuroBERT / ModernGBERT at 8192 ctx eliminates the
`max_length=512 / stride=128` sliding window in
`TransformerExtractor`, reducing inference overhead per doc.

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
