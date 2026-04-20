"""Fine-tune a transformer for German legal citation token-classification.

Default model is ``EuroBERT/EuroBERT-210m`` (multilingual, Apache-2.0,
8192 ctx).  The recipe follows the EuroBERT paper defaults
(warmup 0.1, linear LR decay, AdamW β₁=0.9 β₂=0.95 ε=1e-5,
weight_decay=0.1) with LR 3e-5.

Training data must be BIO JSONL — produced by ``scripts/export_bio.py``.
Each record: ``{"doc_id": str, "tokens": [str], "ner_tags": [str]}``.

Label set (5 classes, canonical refex scheme):
    O, B-LAW_REF, I-LAW_REF, B-CASE_REF, I-CASE_REF

Sub-word labelling: first-token-of-word strategy — sub-word
continuations get ``-100`` and are ignored by the loss.  This matches
``TransformerExtractor``'s inference-time ``aggregation="first"``.

Usage:
    python scripts/train_transformer.py \\
        --train data/hf_bio/train.jsonl \\
        --eval  data/hf_bio/validation.jsonl \\
        --output models/refex-eurobert-210m \\
        --device mps --epochs 3 --batch-size 16

Logs to ``logs/transformer-train.log`` (rotated if exists) and to
wandb project ``malteos/refex`` when ``WANDB_API_KEY`` is set.
Pass ``--no-wandb`` to force local-only logging.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

LABELS: list[str] = ["O", "B-LAW_REF", "I-LAW_REF", "B-CASE_REF", "I-CASE_REF"]
LABEL2ID: dict[str, int] = {lbl: i for i, lbl in enumerate(LABELS)}
ID2LABEL: dict[int, str] = dict(enumerate(LABELS))

DEFAULT_MODEL = "EuroBERT/EuroBERT-210m"
DEFAULT_OUTPUT = "models/refex-eurobert-210m"
DEFAULT_LOG = "logs/transformer-train.log"

logger = logging.getLogger("refex.train_transformer")


def setup_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    fh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    logging.getLogger("transformers").setLevel(logging.WARNING)


def build_tokenize_and_align(tokenizer, max_length: int):
    """Return a `map` function that tokenises word-level records."""

    def fn(batch: dict) -> dict:
        tokenized = tokenizer(
            batch["tokens"],
            is_split_into_words=True,
            truncation=True,
            max_length=max_length,
            padding=False,
        )
        all_labels: list[list[int]] = []
        for i, word_tags in enumerate(batch["ner_tags"]):
            word_ids = tokenized.word_ids(batch_index=i)
            previous_wid: int | None = None
            label_ids: list[int] = []
            for wid in word_ids:
                if wid is None:
                    label_ids.append(-100)
                elif wid != previous_wid:
                    tag = word_tags[wid]
                    label_ids.append(LABEL2ID.get(tag, 0))
                else:
                    label_ids.append(-100)
                previous_wid = wid
            all_labels.append(label_ids)
        tokenized["labels"] = all_labels
        return tokenized

    return fn


def build_compute_metrics():
    from seqeval.metrics import f1_score, precision_score, recall_score

    def fn(eval_pred) -> dict:
        predictions, label_ids = eval_pred
        preds = predictions.argmax(-1)
        true_seqs: list[list[str]] = []
        pred_seqs: list[list[str]] = []
        for pred_row, label_row in zip(preds, label_ids):
            true_seq: list[str] = []
            pred_seq: list[str] = []
            for p, lbl in zip(pred_row, label_row):
                if lbl == -100:
                    continue
                true_seq.append(ID2LABEL[int(lbl)])
                pred_seq.append(ID2LABEL[int(p)])
            true_seqs.append(true_seq)
            pred_seqs.append(pred_seq)
        return {
            "precision": float(precision_score(true_seqs, pred_seqs, zero_division=0)),
            "recall": float(recall_score(true_seqs, pred_seqs, zero_division=0)),
            "f1": float(f1_score(true_seqs, pred_seqs, zero_division=0)),
        }

    return fn


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--eval", dest="eval_path", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT))
    parser.add_argument("--device", choices=["cpu", "mps", "cuda"], default="mps")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--grad-accum", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=3e-5)
    parser.add_argument("--weight-decay", type=float, default=0.1)
    parser.add_argument("--warmup-ratio", type=float, default=0.1)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--limit", type=int, default=None, help="Truncate train set (smoke test)")
    parser.add_argument("--eval-limit", type=int, default=None, help="Truncate eval set")
    parser.add_argument("--wandb-project", default="malteos/refex")
    parser.add_argument("--wandb-run-name", default=None)
    parser.add_argument("--no-wandb", action="store_true")
    parser.add_argument("--log-file", type=Path, default=Path(DEFAULT_LOG))
    parser.add_argument("--logging-steps", type=int, default=20)
    parser.add_argument("--trust-remote-code", action="store_true", default=True)
    parser.add_argument("--attn-impl", default="sdpa", help="sdpa|eager|flash_attention_2")
    args = parser.parse_args()

    setup_logging(args.log_file)

    if args.device == "mps":
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    use_wandb = (not args.no_wandb) and bool(os.environ.get("WANDB_API_KEY"))
    if use_wandb:
        entity, _, project = args.wandb_project.partition("/")
        if not project:
            project = entity
            entity = None
        os.environ["WANDB_PROJECT"] = project
        if entity:
            os.environ["WANDB_ENTITY"] = entity
        default_name = f"{Path(args.model).name}-e{args.epochs}-b{args.batch_size}-lr{args.learning_rate:g}"
        run_name = args.wandb_run_name or default_name
        os.environ["WANDB_NAME"] = run_name
        logger.info("wandb enabled: entity=%s project=%s run=%s", entity, project, run_name)
    else:
        logger.info("wandb disabled (no WANDB_API_KEY or --no-wandb set)")

    # Import heavy deps after setup so --help is snappy.
    import torch
    from datasets import load_dataset as hf_load_dataset
    from transformers import (
        AutoModelForTokenClassification,
        AutoTokenizer,
        DataCollatorForTokenClassification,
        EarlyStoppingCallback,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    set_seed(args.seed)

    logger.info("Loading tokenizer %s", args.model)
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=args.trust_remote_code)

    logger.info("Loading datasets: train=%s eval=%s", args.train, args.eval_path)
    ds = hf_load_dataset(
        "json",
        data_files={"train": str(args.train), "validation": str(args.eval_path)},
    )
    if args.limit is not None:
        ds["train"] = ds["train"].select(range(min(args.limit, len(ds["train"]))))
    if args.eval_limit is not None:
        ds["validation"] = ds["validation"].select(range(min(args.eval_limit, len(ds["validation"]))))
    logger.info("Train size=%d  eval size=%d", len(ds["train"]), len(ds["validation"]))

    tokenize_fn = build_tokenize_and_align(tokenizer, args.max_length)
    tokenised = ds.map(
        tokenize_fn,
        batched=True,
        remove_columns=ds["train"].column_names,
        desc="tokenising",
    )

    logger.info("Loading model %s num_labels=%d", args.model, len(LABELS))
    try:
        model = AutoModelForTokenClassification.from_pretrained(
            args.model,
            num_labels=len(LABELS),
            id2label=ID2LABEL,
            label2id=LABEL2ID,
            trust_remote_code=args.trust_remote_code,
            attn_implementation=args.attn_impl,
        )
    except (TypeError, ValueError) as e:
        logger.warning("attn_implementation=%s rejected (%s); retrying without it", args.attn_impl, e)
        model = AutoModelForTokenClassification.from_pretrained(
            args.model,
            num_labels=len(LABELS),
            id2label=ID2LABEL,
            label2id=LABEL2ID,
            trust_remote_code=args.trust_remote_code,
        )

    # Compute training args
    use_bf16 = args.device == "cuda" and torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    use_fp16 = args.device == "cuda" and not use_bf16

    args.output.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(args.output),
        overwrite_output_dir=True,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        warmup_ratio=args.warmup_ratio,
        lr_scheduler_type="linear",
        adam_beta1=0.9,
        adam_beta2=0.95,
        adam_epsilon=1e-5,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        logging_strategy="steps",
        logging_steps=args.logging_steps,
        report_to=(["wandb"] if use_wandb else []),
        dataloader_num_workers=0,  # MPS safety
        fp16=use_fp16,
        bf16=use_bf16,
        seed=args.seed,
        save_safetensors=True,
        use_mps_device=(args.device == "mps"),
        disable_tqdm=False,
    )

    collator = DataCollatorForTokenClassification(tokenizer)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenised["train"],
        eval_dataset=tokenised["validation"],
        tokenizer=tokenizer,
        data_collator=collator,
        compute_metrics=build_compute_metrics(),
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    logger.info(
        "Starting training: epochs=%d batch=%d grad_accum=%d lr=%g device=%s",
        args.epochs,
        args.batch_size,
        args.grad_accum,
        args.learning_rate,
        args.device,
    )
    t0 = time.time()
    train_result = trainer.train()
    train_wall = time.time() - t0

    logger.info("Final eval...")
    eval_result = trainer.evaluate()

    logger.info("Saving best model to %s", args.output)
    trainer.save_model(str(args.output))
    tokenizer.save_pretrained(str(args.output))

    summary = {
        "model": args.model,
        "output": str(args.output),
        "device": args.device,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "grad_accum": args.grad_accum,
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "warmup_ratio": args.warmup_ratio,
        "max_length": args.max_length,
        "seed": args.seed,
        "train_size": len(tokenised["train"]),
        "eval_size": len(tokenised["validation"]),
        "train_wall_seconds": round(train_wall, 2),
        "train_metrics": {k: float(v) for k, v in train_result.metrics.items() if isinstance(v, (int, float))},
        "eval_metrics": {k: float(v) for k, v in eval_result.items() if isinstance(v, (int, float))},
        "wandb_run_name": os.environ.get("WANDB_NAME"),
    }
    summary_path = Path("logs") / f"train-summary-{Path(args.output).name}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    logger.info("Wrote summary: %s", summary_path)

    logger.info(
        "Done. train_wall=%.1fs  best_f1=%.4f  val_loss=%.4f",
        train_wall,
        float(eval_result.get("eval_f1", 0.0)),
        float(eval_result.get("eval_loss", 0.0)),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
