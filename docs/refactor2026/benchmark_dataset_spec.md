# Benchmark Dataset Specification

**Purpose:** defines the shape, splits, annotation guidelines and distribution of the
gold-standard dataset used to measure the refactored extractor. This doc is the contract
for whoever builds the dataset.

**Distribution model:**

- **Full dataset** → published to Hugging Face Hub under
  `openlegaldata/german-legal-references-benchmark` (or similar — slug tbd).
- **CI subset** → a ~10–20 document curated slice vendored into
  `benchmarks/fixtures/` in this repo so every PR can run `make bench` without network
  access or HF credentials.

**Builds on:**
[`output_format_recommendation.md`](./output_format_recommendation.md) ·
[`implementation_plan.md`](./implementation_plan.md) (Stream A)

---

## 1. Core Principle — Benchmark Input ≡ Extractor Output

The benchmark's gold labels **must use the same JSONL schema** as the extractor's primary
output format (per [`output_format_recommendation.md`](./output_format_recommendation.md)
§4.2). Scoring is a straight diff between two JSONL files of the same shape. No
translation layer.

This is the single most important rule. Annotation guidelines flow from it.

---

## 2. Directory Layout on Hugging Face

```
openlegaldata/german-legal-references-benchmark/
├── README.md                       # HF dataset card (authors, license, citation)
├── dataset_infos.json              # HF auto-generated
├── data/
│   ├── train/
│   │   ├── documents.jsonl         # {doc_id, text, metadata}
│   │   └── annotations.jsonl       # {doc_id, citations[], relations[]}
│   ├── dev/
│   │   ├── documents.jsonl
│   │   └── annotations.jsonl
│   ├── test/
│   │   ├── documents.jsonl
│   │   └── annotations.jsonl
│   └── ci_subset/
│       ├── documents.jsonl         # ~10–20 docs, mirror into refex/benchmarks/fixtures/
│       └── annotations.jsonl
└── guidelines/
    ├── annotation_guidelines.md    # human-facing rules for annotators
    └── examples/                   # worked cases, ambiguous patterns
```

Split policy: **80 / 10 / 10** (train / dev / test) for documents. The CI subset is a
stratified sample across document types (BGH, BVerwG, BVerfG, OVG, LG, ...) drawn from
the **test split** so that CI regression numbers are comparable to published test F1.

---

## 3. `documents.jsonl` Schema

One JSON object per line. One object per document.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `doc_id` | string | yes | Stable ID, e.g. `bgh-2003-03-19-viii-zr-295-01`. Globally unique within the dataset. |
| `text` | string | yes | Raw plain-text of the decision. Newlines `\n` preserved. No HTML. |
| `language` | string | yes | ISO 639-1 code. Always `"de"` for this dataset. |
| `source` | string | yes | URL or dataset-internal source identifier, e.g. `openlegaldata://case/12345`. |
| `court` | string | no | Court of origin, e.g. `"BGH"`. Useful for stratified sampling. |
| `decision_date` | string | no | ISO 8601 date, e.g. `"2003-03-19"`. |
| `decision_type` | string | no | `"Urteil"` / `"Beschluss"` / `"Verfügung"` / ... |
| `license` | string | yes | Per-document license. See §7. |

**Example:**

```json
{"doc_id": "bgh-2003-03-19-viii-zr-295-01",
 "text": "Die Kostenentscheidung beruht auf § 154 Abs. 1 VwGO i.V.m. § 708 Nr. 11 ZPO. ...",
 "language": "de",
 "source": "openlegaldata://case/789456",
 "court": "BGH",
 "decision_date": "2003-03-19",
 "decision_type": "Urteil",
 "license": "CC0-1.0"}
```

---

## 4. `annotations.jsonl` Schema

One JSON object per line. One object per document. `doc_id` must match
`documents.jsonl`; the dataset loader joins them.

```json
{
  "doc_id": "bgh-2003-03-19-viii-zr-295-01",
  "citations": [ /* list[Citation] */ ],
  "relations": [ /* list[CitationRelation] */ ]
}
```

### 4.1 `Citation` — shared envelope

Every citation (law or case) has:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string | yes | Annotation-local ID, e.g. `c_001`. Only needs to be unique **within this document**; used to wire relations. |
| `type` | string | yes | `"law"` \| `"case"`. Discriminator. |
| `kind` | string | yes | `"full"` \| `"short"` \| `"id"` \| `"ibid"` \| `"supra"` \| `"aao"` \| `"ebenda"`. See §5.5. |
| `span` | object | yes | `{"start": int, "end": int, "text": string}`. Character offsets into `documents.jsonl[doc_id].text`. `text` must equal `text[start:end]`. |
| `confidence` | float | no | Annotator confidence 0..1. Default `1.0`. Useful for ambiguous cases. |
| `annotator` | string | no | Annotator ID, for inter-annotator agreement analysis. |
| `notes` | string | no | Free text, e.g. rationale for a hard call. |

### 4.2 Law citation — additional fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `unit` | string | yes | `"paragraph"` (§, §§) \| `"article"` (Art., Artikel). |
| `delimiter` | string | yes | Exact matched token: `"§"`, `"§§"`, `"Art."`, `"Art"`, `"Artikel"`. |
| `book` | string | yes | Normalised law-book code, lowercase: `"bgb"`, `"vwgo"`, `"gg"`, `"rl-2001-29-eg"`. Must be listed in `src/refex/data/law_book_codes.txt` or added to it. |
| `number` | string | yes | The main number as a string (preserves letter suffix): `"708"`, `"3a"`, `"77"`. |
| `structure` | object | no | Nested fields. Keys from the controlled set: `buch`, `teil`, `abschnitt`, `unterabschnitt`, `titel`, `untertitel`, `kapitel`, `unterkapitel`, `absatz`, `satz`, `halbsatz`, `nummer`, `buchstabe`, `alternative`, `variante`. All values are strings. |
| `range_end` | string \| null | no | For ranges like `§§ 2 bis 4 ZPO`, set `number="2"` and `range_end="4"`. |
| `range_extensions` | array[string] | no | `["f"]` or `["ff"]` for `§ 123 f.` / `§ 123 ff.`. |
| `resolves_to` | string \| null | no | For `kind != "full"`: the `id` of the full citation this short-form refers to. Annotators: leave null if the target is outside the document or ambiguous. |

### 4.3 Case citation — additional fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `court` | string \| null | yes if present in text | e.g. `"BGH"`, `"OVG Schleswig"`. Lowercase normalisation not required at annotation time. |
| `file_number` | string \| null | yes if present | Aktenzeichen as written, e.g. `"VIII ZR 295/01"`. |
| `file_number_parts` | object | no | `{"senate": "VIII", "register": "ZR", "serial": "295", "year": "01"}`. Leave empty if parsing is ambiguous. |
| `date` | string \| null | no | ISO 8601 date if visible. |
| `decision_type` | string \| null | no | `"Urteil"` / `"Beschluss"` / ... |
| `ecli` | string \| null | no | Full ECLI if present. |
| `reporter` | string \| null | no | `"BGHZ"`, `"NJW"`, `"BVerfGE"`, ... |
| `reporter_volume` | string \| null | no | |
| `reporter_page` | string \| null | no | |
| `reporter_marginal` | string \| null | no | `"Rn. 23"`, `"Rz. 5"`, ... |
| `parallel_citations` | array[string] | no | IDs of other `CaseCitation`s in this document that cite the same decision (e.g. the reporter citation of the same judgment). |
| `resolves_to` | string \| null | no | As above. |

### 4.4 `CitationRelation` — connectors & cross-refs

```json
{
  "source_id": "c_001",
  "target_id": "c_002",
  "relation": "ivm",
  "span": {"start": 40, "end": 46, "text": "i.V.m."}
}
```

`relation` vocabulary:

| Value | Meaning |
|-------|---------|
| `ivm` | `i.V.m.` / `iVm` / `i. V. m.` — "in connection with". Binds two law refs. |
| `vgl` | `vgl.` — "compare". Hints at a parenthetical citation. |
| `aao` | `a.a.O.` refers-back link. |
| `ebenda` | `ebenda` / `ebd.` refers-back link. |
| `siehe` | `siehe dort` refers-back link. |
| `resolves_to` | Any `short`/`id`/`supra` citation's link to its full form. Annotators may either set `resolves_to` on the citation itself or emit this relation — loader accepts both. |
| `parallel` | Two citations of the same underlying decision (reporter + Aktenzeichen pair). |

### 4.5 Worked example

Text: `Die Zulassung folgt aus § 167 VwGO i.V.m. §§ 708 Nr. 11, 711 ZPO.`

```json
{
  "doc_id": "example-001",
  "citations": [
    {"id": "c_001", "type": "law", "kind": "full",
     "span": {"start": 24, "end": 35, "text": "§ 167 VwGO"},
     "unit": "paragraph", "delimiter": "§", "book": "vwgo", "number": "167"},
    {"id": "c_002", "type": "law", "kind": "full",
     "span": {"start": 43, "end": 59, "text": "§§ 708 Nr. 11"},
     "unit": "paragraph", "delimiter": "§§", "book": "zpo", "number": "708",
     "structure": {"nummer": "11"}},
    {"id": "c_003", "type": "law", "kind": "full",
     "span": {"start": 61, "end": 68, "text": "711 ZPO"},
     "unit": "paragraph", "delimiter": "§§", "book": "zpo", "number": "711"}
  ],
  "relations": [
    {"source_id": "c_001", "target_id": "c_002", "relation": "ivm",
     "span": {"start": 36, "end": 42, "text": "i.V.m."}}
  ]
}
```

Note: `c_003` shares the `§§` delimiter with `c_002` even though the `§§` token
appears only once in the source — the multi-ref expands to both sections.

---

## 5. Annotation Guidelines

### 5.1 Span boundaries

- **Law refs**: include the delimiter (`§`, `§§`, `Art.`, `Artikel`) and the book code
  at the tail. Example span: the whole of `§ 154 Abs. 1 VwGO`.
- **Multi-refs under one `§§`**: each section becomes its own citation. The first
  citation's span includes `§§` + first section's structure; subsequent citations span
  only their own number + structure; the book-code span belongs to the **last** citation
  (which is also where the book is legally attached in German usage).
- **Case refs**: include court + Aktenzeichen + reporter + marginal if they form a
  single semantic unit. A parenthetical reporter citation of the same case
  (`BGHZ 154, 239, 242 f.`) is a **separate** `CaseCitation` linked via
  `relation: "parallel"`.

### 5.2 Normalisation

- `book` codes are **normalised to lowercase** (e.g. `"VwGO"` → `"vwgo"`) at annotation
  time. This matches the extractor's output (`Ref.clean_section`-style normalisation).
- `number` is written as it appears, preserving letter suffixes (`"3a"`, not `"3"`) and
  dropping surrounding whitespace. No leading zeros.
- Dates always ISO 8601 (`2003-03-19`, not `19. März 2003`).
- `file_number` is stored **verbatim** (preserving internal spaces and punctuation), but
  whitespace is collapsed to single spaces.

### 5.3 Controlled structure keys

Only these keys are allowed in `structure`. Anything else is an error.

```
buch, teil, abschnitt, unterabschnitt, titel, untertitel,
kapitel, unterkapitel,
absatz, satz, halbsatz, nummer, buchstabe, alternative, variante
```

Values are always strings, never ints (`"1"`, not `1`). Preserves cases like
`"Halbsatz": "1"` vs a future `"1a"`.

### 5.4 `Art. 3 II Buchst. c RL 2001/29/EG`

Roman numerals as Absatz is a German-legal convention for Artikel citations. Normalise
to Arabic: `"absatz": "2"`. Record the original Roman form in `notes` only if useful.

### 5.5 Short-form / supra / id / ibid / a.a.O. / ebenda

- **Full (`kind: "full"`):** any citation with enough information to resolve on its own
  (book + number for law; court + file number or reporter + volume + page for case).
- **Short (`kind: "short"`):** one missing piece, resolvable from earlier in the
  document. Example: bare `§ 5` after a prior `§ 3 BGB` — short-form inheriting book.
  Example: `531 U.S., at 99` after a prior full cite.
- **Id / ibid (`kind: "id"` / `kind: "ibid"`):** refers to the **immediately previous**
  citation.
- **Supra (`kind: "supra"`):** refers back to a named earlier citation.
- **a.a.O. / ebenda (`kind: "aao"` / `kind: "ebenda"`):** German equivalents of id/ibid.

All non-`full` kinds **should** have a `resolves_to` pointer when the target exists in
the same document. If it doesn't (first-short in a document, cross-document reference),
leave `resolves_to: null` and note this in `notes`.

### 5.6 What NOT to annotate

- **Prose mentions** of laws without a citation form: "das BGB regelt..." — skip unless
  followed by a specific reference.
- **Court names in running text** unattached to a decision citation: "die Kammer hat
  entschieden" — skip.
- **Statutes in section headings** that are not referenced from prose — skip (they
  belong to document structure, not citations).
- **Archive signatures / file numbers of the current document itself** — skip, these are
  metadata, not citations.

### 5.7 Ambiguity protocol

When in doubt:
1. Prefer over-annotation: emit the citation with `confidence < 1.0` and a `notes`
   entry.
2. Mark with a secondary annotator via `annotator` field for disagreement analysis.
3. Document unresolved cases in `guidelines/examples/ambiguous.md` so future
   annotators see the precedent.

---

## 6. CI Subset — Curation Rules

**Target size:** 10–20 documents, ~100–300 citations total.

**Stratification** — the subset must include at least one of each:

- Law refs:
  - `§` single refs (`§ 3 BGB`)
  - `§§` multi refs with comma + `Nr.` (`§§ 708 Nr. 11, 711 ZPO`)
  - `§§` range refs with `bis` (`§§ 2 bis 4 ZPO`)
  - `Art.` refs (Grundgesetz or EU directive)
  - A ref with `Abs.` + `Satz` + `Halbsatz` all present
  - A ref with `i.V.m.` connector across two books
  - A short-form / a.a.O. / ebenda reference
- Case refs:
  - BVerfG cite (ECLI present)
  - BGH cite with reporter (BGHZ) and marginal (Rn.)
  - OVG / LG / administrative court cite
  - Parallel citation (Aktenzeichen + reporter of same decision)

**Selection process:** stratified sample from the **test split**. Document IDs listed
in `guidelines/ci_subset.md` on the HF repo for reproducibility.

**Mirroring into the refex repo:**

```
refex/benchmarks/fixtures/
├── documents.jsonl
├── annotations.jsonl
└── SOURCE                 # file containing the HF dataset revision SHA + date
```

A `make bench-sync` target in the refex Makefile fetches the current `ci_subset` from
HF and overwrites the fixture directory; run this whenever the HF dataset advances.

---

## 7. Licensing & Provenance

- **Texts**: German court decisions are generally not copyrighted (§ 5 UrhG — amtliche
  Werke), but commentary and headnotes may be. Annotators must check per document.
  Record per-document license in `documents.jsonl[].license`.
- **Annotations**: contributed under **CC0-1.0** so the benchmark can be used freely.
  The HF dataset card must state this.
- **Provenance**: every document must have a traceable `source` URL or dataset ID so
  the original text can be re-fetched if needed.

---

## 8. Versioning

- Dataset versions follow `YYYY-MM-DD` date tags on the HF repo.
- `refex/benchmarks/fixtures/SOURCE` pins the exact revision the CI subset mirrors.
- Any schema change triggers a **minor** dataset version bump; annotation additions
  without schema changes are a **patch** bump.
- `benchmarks/datasets.py` loader pins the minimum compatible dataset version.

---

## 9. Quality Checks

Before publishing a new dataset revision, run (ideally as a CI job on the dataset repo):

1. **Schema validation**: every record validates against JSON Schemas committed to the
   dataset repo (`schemas/document.schema.json`, `schemas/annotation.schema.json`).
2. **Span integrity**: for every citation, `text[span.start:span.end] == span.text`.
3. **Join integrity**: every `doc_id` in `annotations.jsonl` has a matching entry in
   `documents.jsonl` and vice-versa.
4. **ID uniqueness**: citation `id`s unique within their document; `doc_id`s unique
   across the dataset.
5. **Controlled vocabulary**: `structure` keys, `unit`, `kind`, `relation` values all
   from the permitted sets.
6. **Resolves-to integrity**: every `resolves_to` target is an `id` present in the same
   document, or `null`.
7. **`book` membership**: every `book` value exists in
   `src/refex/data/law_book_codes.txt` (or a PR opened to add it).

`benchmarks/validate.py` in refex runs the same checks on the CI subset.

---

## 10. Inter-Annotator Agreement (Recommended)

Target **≥ 10% double-annotation** on the test split (and ideally on dev too). Metric
choice matters:

- **Krippendorff's α** is the preferred headline agreement metric — unlike Cohen's κ it
  generalises cleanly to more than two annotators, supports partial overlaps between
  annotator pools, and accommodates categorical / ordinal / interval scales in one
  framework ([Artstein & Poesio, 2008](https://www.mitpressjournals.org/doi/abs/10.1162/coli.07-034-R2) —
  the canonical reference for IAA in computational linguistics).
- **Cohen's κ** is acceptable when there are exactly two annotators and a fixed label
  set. Report it per-field (`book`, `unit`, `kind`, each `structure` key) rather than
  globally.
- **Span F1 between annotators** (exact + SemEval-2013 partial) captures boundary
  disagreement that kappa hides.

Report these in the HF dataset card. Flag documents with Krippendorff's α < 0.67
(Artstein & Poesio's "tentative conclusions" floor) for a third annotator to
adjudicate. Keep the adjudication protocol in `guidelines/adjudication.md`.

Crucially, IAA demonstrates **reliability, not validity** — high agreement proves
annotators interpret the guidelines consistently, not that the guidelines capture the
legally-correct distinction. Validate against domain expert review on a sample
(~20 documents) separately.

---

## 11. Best Practices & Common Pitfalls

Drawn from the broader NER / citation-extraction benchmarking literature. Each item
lists how this spec addresses it.

### 11.1 Label noise is pervasive — plan for it

[Northcutt et al. (2021)](https://arxiv.org/abs/2103.14749) found label errors in every
major ML benchmark they audited (average 3.3%, up to 10.1% in some). For NER
specifically, [Wang et al. (2019)](https://aclanthology.org/2020.conll-1.16/) identified
1,300+ incorrect labels in CoNLL-2003 — comparable to the error rate of SOTA
models. [CleanCoNLL](https://arxiv.org/abs/2310.16225) (2023) later re-annotated the
corpus to near-noise-free status and showed that SOTA rankings change materially on
clean data.

**What this spec does:**

- Double-annotation (§10) + adjudication protocol catches a first pass.
- `benchmarks/validate.py` (§9) enforces span integrity, controlled vocabulary, and
  resolves-to integrity — cheap checks that catch annotator slips.
- The dataset is **versioned** (§8) so corrections can ship as a patch release without
  invalidating prior benchmarks.
- **Expect to ship a "clean" revision 6–12 months after v1.** Budget annotation time
  for error-mining on the test split once a model is in use — errors cluster where
  models are confident-but-wrong
  ([cleanlab methodology](https://cleanlab.ai/blog/learn/entity-recognition/)).

### 11.2 Token-level F1 hides boundary errors — use entity-level + SemEval-2013

The default `seqeval` metric (entity-level strict match) is the minimum; reporting only
token-level F1 double-penalises partial matches and masks systematic boundary-shift
errors ([Batista, 2018](https://www.davidsbatista.net/blog/2018/05/09/Named_Entity_Evaluation/)).

The [MUC-5](https://aclanthology.org/M93-1007/) / [SemEval-2013 Task 9](https://aclanthology.org/S13-2056/)
scheme defines four metrics that together give a fuller picture:

| Metric | Checks |
|--------|--------|
| **Strict** | exact boundaries **and** type |
| **Exact** | exact boundaries, type ignored |
| **Partial** | overlapping boundaries, type ignored (partial credit: 0.5) |
| **Type** | some overlap **and** correct type |

**What this spec does:** §A2 in [`implementation_plan.md`](./implementation_plan.md)
requires all four. The [`nervaluate`](https://github.com/MantisAI/nervaluate) library
implements them against arbitrary label sets and is the recommended dependency under
the `[adapters]` extra.

### 11.3 Document-level splits, not sentence-level

Leakage-through-document is the most common silent error in legal NLP benchmarks. The
same court decision can be republished across reporters, excerpted in commentary, or
re-indexed with minor edits. Sentence-level splits that land the same case in both
train and test inflate scores dramatically.

**What this spec does:**

- Splits are defined at the **document level** (§2).
- Near-duplicate detection across splits must be a QC step before publication.
  Recommended: MinHash on paragraph-shingles at `threshold=0.8`, flag any cross-split
  hit.
- `source` field (§3) carries the provenance URL so re-publications of the same
  judgment can be grouped and held out together.

### 11.4 Stratify by court, date, and decision type

Legal NLP benchmarks that don't stratify suffer from **domain collapse**: the test
split ends up dominated by one court or era, and the reported F1 doesn't generalise
([LexGLUE, Chalkidis et al. 2022](https://aclanthology.org/2022.acl-long.297/);
[LEXTREME, Niklaus et al. 2023](https://arxiv.org/abs/2301.13126)).

**What this spec does:**

- CI subset stratification (§6) requires coverage across BVerfG / BGH / administrative
  / civil courts and across law-ref pattern types.
- Full dataset splits should preserve the same court + date proportions (reported in
  the dataset card).
- Report F1 **per stratum** in `benchmarks/metrics.py`, not just the aggregate.

### 11.5 Benchmark data contamination

[Dodge et al. (2021)](https://aclanthology.org/2021.emnlp-main.98/) showed that widely-
used pre-training corpora (C4) contain the test splits of common benchmarks, causing
LLMs to appear to generalise when they've memorised. For a German legal citation
benchmark, the risk surfaces two ways:

1. Training a transformer extractor (Stream G) on a corpus that includes the gold
   documents.
2. The benchmark's source court decisions already living in `openlegaldata`'s public
   dump and therefore in any common German web crawl.

**What this spec does:**

- Require that any submitted model declares whether its training data overlaps with the
  benchmark, checked via document-level hash or URL match against the
  `documents.jsonl[].source` field.
- Publish **document hashes** in the dataset card so hosts can filter them out of
  scraped corpora.
- Keep the test split's exact `doc_id`s pinned to HF revision SHAs; rotate a sealed
  "holdout" split periodically for robust evaluation.

### 11.6 Report more than one number

F1 alone hides systematic errors. Per the NER evaluation literature, always include:

- Precision + recall separately (F1 can stay flat while P/R trade off).
- Per-class and per-field F1 (a model can win overall by over-predicting the majority
  class).
- Error-type breakdown: [SemEval-2013](https://aclanthology.org/S13-2056/) *correct /
  incorrect / partial / missed / spurious* counts — actionable for debugging.
- Confidence calibration histogram (for ML engines under Streams F/G).

**What this spec does:** §A2 of [`implementation_plan.md`](./implementation_plan.md)
requires a JSON report with all of the above, not a single F1 number.

### 11.7 Version everything, pin revisions downstream

Benchmarks that don't version cause irreproducible papers. HF Hub's git-backed revisions
are the right substrate, but only if callers pin them.

**What this spec does:**

- Date-tag dataset revisions on HF (§8).
- `benchmarks/fixtures/SOURCE` pins the CI-subset revision SHA.
- `benchmarks/datasets.py` loader accepts `revision=` and defaults to the pinned SHA,
  not `main`.

### 11.8 Precedents from adjacent domains

Research-paper citation extraction already solved many of these problems; reuse
directly rather than re-deriving:

- **[Tkaczyk et al. (2018)](https://arxiv.org/abs/1802.01168)** — the canonical
  evaluation of 10 open-source bibliographic reference parsers. Methodology: single
  evaluation corpus (9.5k papers), same metrics per tool, out-of-box vs retrained
  splits. Their finding that retraining adds 3–16 F1 points is the core argument for
  Stream F (CRF) in our plan.
- **[GROBID's end-to-end evaluation protocol](https://grobid.readthedocs.io/en/latest/References/)**
  — builds directly on Tkaczyk; a good template for per-field scoring when the schema
  has nested structure (as ours does with `structure`).
- **[eyecite's CI workflow](https://github.com/freelawproject/eyecite)** — posts
  per-PR accuracy + speed deltas vs main as a comment. Directly the model we're
  adopting for §A4a.
- **[Darji et al. (2023)](https://arxiv.org/abs/2303.05388)** / **Leitner et al.
  ([2020](https://aclanthology.org/2020.lrec-1.551/))** — German legal NER precedent;
  their property sets inform our schema and should be reviewed as a sanity check
  before freezing v1.

### 11.9 Document datasets, not just tools

[Gebru et al.'s Datasheets for Datasets (2021)](https://dl.acm.org/doi/10.1145/3458723)
is the standard; HF's dataset card is a rendering of it. Common pitfalls:

- Skipping "Motivation" and "Considerations for Using the Data" sections — these are
  where legal, licensing, and bias caveats live. Research found only ~8% of low-download
  HF dataset cards complete all suggested sections
  ([Yang et al., 2024](https://arxiv.org/abs/2401.13822)).
- Missing licensing per-document (§7 here) — critical for German court decisions where
  some documents are free (§ 5 UrhG) and some carry third-party commentary.
- Not declaring annotation process / IAA / adjudication — consumers can't calibrate
  trust.

**What this spec does:** §7 (licensing per-document), §10 (IAA), and §11 itself all
feed the dataset card directly. Keep the dataset card's skeleton pulled from the
[HF community template](https://huggingface.co/docs/hub/en/datasets-cards).

---

## 12. Summary: Common Pitfalls Checklist

Run through this before publishing any dataset revision:

- [ ] Every annotation's `text[start:end] == span.text` (span integrity).
- [ ] No document appears in more than one split (document-level leakage check).
- [ ] Near-duplicate detection run across splits (MinHash or SimHash on paragraph
      shingles).
- [ ] Court / date / decision-type distributions reported per split.
- [ ] Every `book` in annotations exists in `law_book_codes.txt`.
- [ ] IAA (Krippendorff's α) reported per field in the dataset card.
- [ ] ≥ 10% of test split double-annotated; adjudication trail preserved.
- [ ] CI subset is a stratified draw from the test split, not from train.
- [ ] Dataset card completes all Gebru/HF sections — especially motivation, known
      limitations, licensing.
- [ ] Revision SHA pinned in the downstream consumer (`benchmarks/fixtures/SOURCE`).
- [ ] Document hashes published so pre-training corpora can filter them out.
- [ ] Validators (`benchmarks/validate.py`) pass with zero errors.

---

## 13. Open Items for Dataset Builders

Items this spec deliberately leaves to the dataset-building team to decide:

- **Annotation tool**: doccano, Label Studio, Prodigy, or a bespoke tool. The JSONL
  schema here is compatible with all three via simple exporters.
- **Target dataset size**: recommended 500–2,000 documents; final size depends on
  annotation budget.
- **Domain coverage**: civil / criminal / administrative / constitutional balance — set
  by the sampling strategy used on the Open Legal Data corpus.
- **Adjudication process**: how disagreements are resolved (majority vote, senior
  annotator override, discussion protocol).
- **PII policy**: German court decisions are often pseudonymised upstream, but verify.

These decisions should be recorded in the HF dataset card alongside the dataset itself,
not here — this doc is the *format contract*, not the annotation project plan.
