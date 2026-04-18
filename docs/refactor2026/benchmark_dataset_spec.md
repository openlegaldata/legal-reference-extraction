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

Target ≥ 10% double-annotation. Report span-F1 agreement (exact + relaxed)
and field-level Cohen's κ in the HF dataset card. Flag documents with
disagreement > threshold for a third annotator to adjudicate.

---

## 11. Open Items for Dataset Builders

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
