# Legal Reference Extraction

Extract citations from German legal documents — law references (`§ 433 BGB`)
and case references (`BGH, VIII ZR 295/01`).

Used by [de.openlegaldata.io](https://de.openlegaldata.io/).

**Supported Python versions:** 3.11, 3.12, 3.13 (tested on every CI run).

## Install

```bash
pip install legal-reference-extraction

# or from git
pip install git+https://github.com/openlegaldata/legal-reference-extraction.git

# local dev
make install
```

## Usage

```python
from refex.orchestrator import CitationExtractor

extractor = CitationExtractor()
result = extractor.extract("Die Entscheidung beruht auf § 42 VwGO.")

for cit in result.citations:
    print(cit.type, cit.span.text)
# law § 42 VwGO
```

### Input formats

Plain text, HTML, and Markdown are supported. Format is auto-detected or
can be set explicitly:

```python
# HTML — tags are stripped, entities decoded, spans map to plain text
result = extractor.extract("<p>Gemäß &#167; 433 BGB ist der Käufer verpflichtet.</p>", fmt="html")

# Markdown — formatting markers stripped
result = extractor.extract("Gemäß **§ 433 BGB** ist der Käufer verpflichtet.", fmt="markdown")

# Auto-detect (based on content sniffing)
result = extractor.extract(html_content)
```

For HTML and Markdown input, span offsets reference the canonical plain-text
projection. Use `map_span_to_raw` to recover positions in the original:

```python
from refex.document import Document, map_span_to_raw

doc = Document(raw="<p>§ 433 BGB</p>", format="html")
result = extractor.extract(doc)
for cit in result.citations:
    raw_span = map_span_to_raw(cit.span, doc)
    print(f"{cit.span.text} → raw[{raw_span.start}:{raw_span.end}]")
```

### Output formats

```python
from refex.serializers import to_jsonl, to_hf_bio, to_gliner, to_spacy_doc, to_web_annotation, to_akn_ref

to_jsonl(result, doc_id="example")      # JSONL (primary format)
to_hf_bio(result, text)                 # HuggingFace BIO tags
to_gliner(result)                       # GLiNER span format
to_spacy_doc(result, text)              # spaCy Doc dict
to_web_annotation(result)               # W3C Web Annotation
to_akn_ref(result, text)                # Akoma Ntoso XML
```

### Examples

**Law references** — `§` and `§§` patterns with section numbers and law book codes:

```python
result = extractor.extract(
    "Bar und bar §§ 1, 2 Abs. 2, 3, 10 Abs. 1 Nr. 1 BGB foo."
)
for cit in result.citations:
    print(cit.book, cit.number)
# bgb 1
# bgb 2
# bgb 3
# bgb 10
```

**Cross-references** — `i.V.m.` (in conjunction with) linking sections across law books:

```python
result = extractor.extract(
    "Die vorläufige Vollstreckbarkeit folgt aus "
    "§ 167 VwGO i.V.m. §§ 708 Nr. 11, 711 ZPO."
)
for cit in result.citations:
    print(cit.book, cit.number)
# vwgo 167
# zpo 708
# zpo 711
```

**Case references** — court names and file numbers:

```python
result = extractor.extract(
    "Das OVG Schleswig habe bereits in seinem Urteil vom 22.04.2010 "
    "(1 KN 19/09) entschieden."
)
for cit in result.citations:
    print(cit.court, cit.file_number)
# OVG Schleswig 1 KN 19/09
```

**Artikel / Grundgesetz** — `Art.` references are supported:

```python
result = extractor.extract("Gemäß Art. 12 Abs. 1 GG besteht Berufsfreiheit.")
```

**Law book context** — extract bare `§` references within a specific law:

```python
extractor = CitationExtractor()
# ... set law_book_context on the underlying engine if needed
```

### Legacy API

The old `RefExtractor` API is still available but deprecated:

```python
from refex.extractor import RefExtractor

extractor = RefExtractor()
content, markers = extractor.extract("Ein Satz mit § 3b AsylG.")
# Note: content no longer contains [ref=UUID] markers (deprecated in v0.7.0)
```

## Development

```bash
make install   # create venv + install in editable mode with dev deps
make test      # run pytest (271 tests)
make lint      # ruff check + format check
make format    # auto-fix lint + format
```

## Benchmark

Run the extraction benchmark against gold-annotated German legal documents:

```bash
make bench-ci           # vendored CI subset (15 docs, no external data needed)
make bench-dev          # full validation split (821 docs)
make bench-quick        # quick check (50 docs on validation)
make bench-validate     # dataset integrity checks
make diagnose           # error analysis
```

Current metrics (validation split, 821 docs):

| Metric | Value |
|--------|-------|
| Span F1 (exact) | 0.734 |
| Case F1 (exact) | 0.613 |
| Law F1 (exact) | 0.797 |
| Throughput | 418 docs/s |

See [`benchmarks/README.md`](benchmarks/README.md) for details.

## Optional extras

The base install has zero runtime dependencies.  Inference engines
and format adapters live in opt-in extras — pick the ones you need:

```bash
pip install "legal-reference-extraction[adapters]"     # spaCy adapter for to_spacy_doc
pip install "legal-reference-extraction[crf]"          # CRF engine  (~30 MB, sklearn-crfsuite)
pip install "legal-reference-extraction[transformers]" # transformer engine (~2 GB, transformers + torch)
pip install "legal-reference-extraction[training]"     # fine-tuning utilities (wandb, seqeval, datasets, accelerate)
```

Most users pick exactly one inference engine (`[crf]` *or*
`[transformers]`).  `[training]` is only needed when fine-tuning a
transformer via `scripts/train_transformer.py`.

## See also

- [CiteURL — citations to U.S. court decisions and U.S. code](https://github.com/raindrum/citeurl)

## License

MIT
