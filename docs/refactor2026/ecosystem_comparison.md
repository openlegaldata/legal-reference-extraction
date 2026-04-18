# Comparison: Citation Extraction Landscape

**Date:** 2026-04-14
**Scope:** Position `legal-reference-extraction` within the broader citation-extraction
ecosystem — both legal-focused and research-paper-focused tools — and extract architectural
lessons.

---

## 1. Peer Group: Legal Citation Extraction

| Project | Language | Approach | Scale Tested | Dependencies |
|---------|----------|----------|--------------|--------------|
| **legal-reference-extraction** | German | Handcrafted regex + masking | Unknown (42 fixture tests) | Zero |
| **eyecite** (Free Law Project) | English (US) | Regex + Hyperscan engine | 50M+ citations | `hyperscan`, `reporters-db`, `courts-db`, `diff-match-patch` |
| **Blackstone** (ICLR&D) | English (UK) | spaCy NER + custom pipe | ICLR archive | `spacy`, trained model (~500MB) |
| **LexNLP** (LexPredict) | English (US) | Regex (via `reporters-db`) | SEC EDGAR corpus | ~30 deps |

### Key observations

**eyecite is the closest analog** (regex-based, legal citations, zero ML). Its architecture is
instructive:

- **Separates data from code:** patterns externalized into `reporters-db` and `courts-db`
  (community-maintained, versioned). This project hardcodes `default_law_book_codes` into the
  extractor class, and the bundled `law_book_codes.txt` is not actually used for matching
  (see `get_law_book_ref_regex` in `law_dnc.py`).
- **Pluggable resolvers:** separates "find citation" from "resolve to canonical form."
  This project conflates extraction with tagging (`RefMarker.replace_content`).
- **Multiple citation types as first-class concerns:** eyecite handles full / short / supra /
  id / ibid as distinct token types. This project only handles full citations plus a crude
  `i.V.m.` cross-reference mechanism — no `a.a.O.`, `ebenda`, `s. dort`.

**Blackstone** shows the ML path: a spaCy pipeline with a custom pipe for `CASENAME`/`CITATION`
pairing. Pipeline-based composition is exactly the kind of strategy pattern a refactor should
adopt.

### Performance gap

- **eyecite uses Hyperscan** (Intel's network-packet regex engine) to apply thousands of regex
  patterns in parallel. This project uses `re.finditer` with patterns recompiled per call.
  Orders of magnitude difference at scale.
- This project's masking approach (string slicing to insert underscores) is O(n) per match —
  acceptable for single documents, problematic at scale.

### German-specific research

Darji et al. (2023, arXiv:2303.05388) fine-tuned German BERT on a Legal Entity Recognition
dataset and **outperformed the prior BiLSTM-CRF baseline**. A follow-up paper ("A Dataset of
German Legal Reference Annotations") specifically targets law citation extraction. **The
academic direction for German legal citations is clearly toward transformer-based NER.**

### Citation taxonomy — thin

| Citation concept | eyecite | Blackstone | This project |
|------------------|---------|------------|--------------|
| Primary reference (full) | ✓ | ✓ | ✓ |
| Short form | ✓ | ✓ | ✗ |
| Ibid / supra / id (a.a.O. / ebenda) | ✓ | via NER | ✗ |
| Cross-reference (i.V.m. / cf.) | — | ✓ | partial |
| Anchor to canonical DB | ✓ | ✗ | ✗ |
| Confidence scores | — | ✓ | ✗ |

### Where this project leads peers

1. **Zero runtime dependencies** — rare in this space. eyecite pulls Hyperscan; LexNLP pulls
   ~30 packages; Blackstone requires ~500MB spaCy model.
2. **German-specific focus** — none of the major tools target German legal citations seriously.
3. **`§§` multi-references with `bis`/`und` ranges** — German-specific and harder than it looks;
   peers don't address it because English citations don't have this form.
4. **License clarity** — MIT, which LexNLP is not (AGPL).

---

## 2. Research Paper Citation Extraction (Broader Field)

The research-paper citation extraction space is substantially more mature — 20+ years of
evolution from regex → CRF → neural → transformer. The problem is genuinely similar, and
the lessons are directly applicable.

### The landscape

| Tool | Approach | Year | Benchmark F1 | Input |
|------|----------|------|--------------|-------|
| **ParsCit** | CRF (Wapiti) | 2008 | 0.75 out-of-box, 0.87 retrained | Reference strings |
| **CERMINE** | SVM classifiers + CRF | 2015 | 0.83 out-of-box, 0.92 retrained | PDF |
| **AnyStyle** | Wapiti CRF | 2011 | (trainable) | Reference strings |
| **refextract** (CERN) | Regex + heuristics | 2011 | — (DOI-specialized) | PDF/string/URL |
| **GROBID** | CRF → BidLSTM-CRF → BERT-CRF | 2008–present | 0.89 out-of-box, 0.92 retrained | PDF |
| **Neural ParsCit** | LSTM + CRF | 2018 | ~0.90 | Reference strings |
| **deep_reference_parser** (Wellcome) | BiLSTM-CRF | 2019 | — | Text |
| **TransParsCit** | Transformer + CRF | 2022 | State of the art | Reference strings |
| **Science Parse / S2ORC** (AllenAI) | Wraps GROBID | 2019–2020 | Inherits GROBID | PDF → JSON |

### Four clear generations

1. **Regex + heuristics (1990s-2000s):** refextract still exemplifies this. Fast, explainable,
   fragile, hard to maintain as formats drift. **This is where `legal-reference-extraction` sits.**
2. **CRF (2008-2015):** ParsCit, AnyStyle, CERMINE. Trained sequence labelers with handcrafted
   features. Major jump in coverage; requires labeled data.
3. **Neural + CRF (2018-2020):** Neural ParsCit (LSTM-CRF), BiLSTM-CRF. +5-10 F1 points over
   pure CRF; handles multilingual data and out-of-domain text.
4. **Transformer + CRF (2022-):** TransParsCit, BERT-CRF variants in GROBID. State of the art;
   expensive at inference.

**GROBID, the leader, is all four generations layered.** Engine is picked at configuration
time: Wapiti CRF for speed, BidLSTM-CRF for accuracy, BERT-CRF for best quality.
**That's the architectural lesson.**

### Patterns that are standard in this field (and missing here)

#### Two-stage pipeline: find → parse → (resolve)

Every mature tool separates:
- **Citation string detection** — find where references live.
- **Reference parsing** — decompose the string into fields.

ParsCit only does stage 2. GROBID does both as distinct models. S2ORC's pipeline adds a
**third resolution stage** (linking `(Smith 2001)` inline mention → bibliography entry →
global paper ID).

This project collapses all three into one mixin method. The `i.V.m.` "waiting marker"
mechanism is a buried hint of the resolution problem.

#### Standard benchmark datasets

Research-paper extraction has the **CORA corpus** as canonical benchmark. Every new paper
reports F1 on CORA, enabling direct comparison. This project doesn't report precision/recall
at all.

Relevant German legal benchmark datasets:

- **Darji et al. 2023, "A Dataset of German Legal Reference Annotations"**
  (`PaDaS-Lab/legal-reference-annotations`, ICAIL 2023) — 2,944 manually annotated **law
  references** (`§`-citations) with 21 structured properties each (Buch, Teil, Titel,
  Untertitel, paragraph text, etc.). **Law-side only** — does *not* annotate case citations
  or Aktenzeichen, even though source documents are court decisions.
- **Leitner et al. 2020, "A Dataset of German Legal Documents for NER"**
  (LREC 2020, arXiv:2003.13016, GitHub `elenanereiss/Legal-Entity-Recognition`) — ~67k
  sentences, 54k annotated entities in 19 classes including `law`, `court decision`,
  `court`, `ordinance`, `regulation`, `European legal norm`, `contract`, `legal literature`.
  Covers **both law and case references** (as entity spans), plus several reference types
  this project doesn't handle. Does not decompose Aktenzeichen into chamber/code/number/year,
  so benchmarks **detection**, not **parsing**.
- **Open Legal Data bulk citations (2019)** — ~100k court decisions with ~444k
  machine-extracted citations. Silver-standard; useful as pretraining / weak supervision,
  not as a clean benchmark.

Recommended split: **Darji → law extractor benchmark; Leitner → case extractor detection
benchmark + broader-entity stretch targets; Open Legal Data → silver-standard training
corpus.**

#### Retrainability is first-class

Tkaczyk 2018 (arXiv:1802.01168) found **3-16% F1 gains from retraining** GROBID / CERMINE /
ParsCit on domain data. Core value proposition of CRF tools: ship reasonable defaults, let
users train on their domain.

The regex approach has no retraining story. New German law book code → code release needed.

#### Standard output formats

- GROBID → TEI/XML (academic standard)
- S2ORC → JSON with global paper IDs
- AnyStyle → BibTeX, CSL-JSON
- refextract → structured dict (DOI, journal, volume, year)

Every mature tool emits something a downstream citation manager or knowledge graph can
consume. **`[ref=UUID]...[/ref]` is not such a format.**

#### Layout features as a distinct channel

GROBID/CERMINE explicitly model PDF visual structure (font, position, indentation) as
separate feature channels. Gets GROBID from F1 0.89 (text-only) to state of the art.

Architectural lesson applicable here: **features from structure (HTML tags, positional
context) are independent signals** and should be first-class inputs.

#### The Wellcome `deep_reference_parser` pattern

Wellcome Trust's `deep_reference_parser` is a **BiLSTM-CRF model wrapped in a small, Python-
friendly API** — no Java runtime (unlike GROBID), no heavy deps. Closest model in spirit to
what a Pythonic, transformer-ready legal-reference-extraction could look like: small
inference model, pip-installable, trainable.

---

## 3. Direct Lessons Mapped to This Project

| Research-paper / legal tool pattern | Applied to legal-reference-extraction |
|--------------------------------------|-----------------------------------------|
| Two-stage pipeline (find → parse → resolve) | Split `extract_law_ref_markers` into finder + parser + cross-ref resolver |
| CORA benchmark | Adopt Darji 2023 for law extractor, Leitner 2020 for case extractor |
| Reporting F1 / precision / recall | Add benchmark metrics to CI output |
| CRF as the first ML step (not transformers) | Introduce optional CRF extractor before jumping to BERT — cheaper, retrainable, proven |
| Standard output format | Emit spaCy Doc / JSON-LD / TEI instead of `[ref=UUID]` markers |
| Layered engine choice (GROBID pattern) | `RefExtractor(engine="regex" \| "crf" \| "transformer")` |
| Reporter-DB pattern (eyecite, ParsCit) | Extract `law_book_codes` + `file_number_codes` into separate versioned package |
| Trainability | Ship training scripts + labeled data loader, even if default engine stays regex |

---

## 4. The Parallel Evolution

Generational gap, explicit:

- **ParsCit (2008)** — first-generation academic: CRF, trainable, open source.
- **eyecite (2021)** — first-generation *legal* but stayed regex + Hyperscan (chose speed over
  ML, deliberate).
- **GROBID (2008→now)** — tracked ML trajectory through all four generations.
- **Darji et al. (2023)** — did the generational jump for German legal citations: BERT-CRF,
  published models, public dataset.
- **`legal-reference-extraction`** — generation zero: no ML, no benchmarks, no retraining,
  regex-only. Roughly 15 years behind the research-paper field's architectural state.

---

## 5. Revised Refactoring Plan (Updated with Peer-Group Context)

The previous architecture review recommended Phase 1 (cleanup) → Phase 2 (strategy pattern)
→ Phase 3 (transformers). The research-paper field suggests an **intermediate Phase 2.5:
CRF extractor**.

### Phase 1 — Code quality cleanup (unchanged)

1. Delete `law.py` (legacy extractor).
2. Fix mutable class defaults on `RefMarker` and mixin classes.
3. Remove dead code (`get_codes()`, unused `codes = ["Sa"]`, commented-out lines).
4. Fix `Ref.__eq__` to return `NotImplemented` instead of asserting.
5. Pre-compile regex patterns at init time.

### Phase 2 — Extractor protocol + data package split (informed by eyecite)

1. Define `Extractor` protocol: `extract(text) -> list[ExtractedRef]`.
2. Wrap existing regex logic as `RegexLawExtractor`, `RegexCaseExtractor`.
3. Make `RefExtractor` an orchestrator accepting a list of extractors.
4. **Extract `law_book_codes` and `file_number_codes` into a separate `de-legal-codes`
   package** (eyecite/reporters-db pattern). Versioned independently.
5. Replace `[ref=UUID]` output with a standard format (spaCy Doc or structured JSON).

### Phase 2.5 — CRF engine (informed by ParsCit / AnyStyle / GROBID)

1. Add `CRFLawExtractor` using `python-crfsuite` or `sklearn-crfsuite`.
2. Training/eval splits:
   - **Law extractor** → Darji 2023 (`PaDaS-Lab/legal-reference-annotations`) as the
     labeled dataset. Law-references-only, 21 structured properties — fits the existing
     `Ref(book, section, ...)` model directly.
   - **Case extractor** → Leitner 2020 (`elenanereiss/Legal-Entity-Recognition`)
     `court decision` entity for detection; Aktenzeichen parsing would need additional
     annotation (or continue using the existing regex parser downstream of ML detection).
3. Report F1 in CI alongside test pass/fail.
4. Document retraining flow (following ParsCit's retrainability pattern).

### Phase 3 — Transformer engine (informed by Darji 2023, TransParsCit)

1. Add `TransformerLawExtractor` using the Darji German BERT model or a fine-tuned variant.
2. Optional install: `pip install legal-reference-extraction[ml]`.
3. Confidence-based overlap resolution in the orchestrator.
4. Existing regex extractor remains as fast default.

---

## 6. Bottom Line

The research-paper citation extraction field is the strongest evidence base for what
architecture a citation extractor should have. Its consensus patterns — two-stage pipeline,
retrainable models, standard benchmarks, swappable engines, separated data packages — are
exactly what `legal-reference-extraction` is missing. The problem is nearly identical; the
solutions have been engineered over 20 years; the patterns are well-documented and
copy-pastable.

If the project's goal is to become the **"GROBID of German legal citations,"** the roadmap
is clear: strategy pattern → CORA-style benchmark (use Darji dataset) → CRF engine → optional
transformer engine, with stable plain-text input and standard output format throughout.
The regex extractor becomes the fast default, not the only option.

The zero-dependency, German-specific niche is real and defensible. But staying at generation
zero indefinitely means the project will be leapfrogged by any ML-based German legal NER tool
that emerges from the Darji research line.

---

## Sources

### Legal citation extraction
- [eyecite on GitHub](https://github.com/freelawproject/eyecite)
- [eyecite whitepaper](https://free.law/pdf/eyecite-whitepaper.pdf)
- [Blackstone on GitHub](https://github.com/ICLRandD/Blackstone)
- [Blackstone at ICLR&D](https://research.iclr.co.uk/blackstone)
- [LexNLP on GitHub](https://github.com/LexPredict/lexpredict-lexnlp)
- [LexNLP paper (arXiv:1806.03688)](https://arxiv.org/abs/1806.03688)
- [German BERT for Legal NER (arXiv:2303.05388)](https://arxiv.org/abs/2303.05388)
- [A Dataset of German Legal Reference Annotations (Darji 2023)](https://ca-roll.github.io/downloads/A_Dataset_of_German_Legal_Reference_Annotations.pdf)
- [PaDaS-Lab/legal-reference-annotations on HuggingFace](https://huggingface.co/datasets/PaDaS-Lab/legal-reference-annotations)
- [A Dataset of German Legal Documents for NER (Leitner 2020, LREC)](https://aclanthology.org/2020.lrec-1.551/)
- [Leitner Legal-Entity-Recognition on GitHub](https://github.com/elenanereiss/Legal-Entity-Recognition)
- [Open Legal Data court decisions dataset release (2019)](http://openlegaldata.io/research/2019/02/19/court-decision-dataset.html)
- [mrm8488/bert-base-german-finetuned-ler on HuggingFace](https://huggingface.co/mrm8488/bert-base-german-finetuned-ler)

### Research paper citation extraction
- [GROBID on GitHub](https://github.com/kermitt2/grobid)
- [GROBID Deep Learning models](https://github.com/grobidOrg/grobid/blob/master/doc/Deep-Learning-models.md)
- [ParsCit on GitHub](https://github.com/knmnyn/ParsCit)
- [CERMINE paper (Springer)](https://link.springer.com/article/10.1007/s10032-015-0249-8)
- [Evaluation and Comparison of Open Source Bibliographic Extraction Tools (Tkaczyk 2018)](https://arxiv.org/pdf/1802.01168)
- [Neural ParsCit paper](https://link.springer.com/article/10.1007/s00799-018-0242-1)
- [TransParsCit: A Transformer-Based Citation Parser](https://digitalcommons.odu.edu/cgi/viewcontent.cgi?article=1133&context=computerscience_etds)
- [Wellcome deep_reference_parser on GitHub](https://github.com/wellcometrust/deep_reference_parser)
- [AnyStyle on GitHub](https://github.com/inukshuk/anystyle)
- [refextract on GitHub (CERN/INSPIRE)](https://github.com/inspirehep/refextract)
- [AllenAI Science Parse on GitHub](https://github.com/allenai/science-parse)
- [AllenAI S2ORC on GitHub](https://github.com/allenai/s2orc)
- [S2ORC paper (arXiv:1911.02782)](https://ar5iv.labs.arxiv.org/html/1911.02782)
