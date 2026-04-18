# Output Format Recommendation for the Refactor

**Date:** 2026-04-18
**Scope:** Choose an output format for the refactored `RefExtractor` that (a) interoperates
with mainstream NER / citation-extraction tooling and (b) losslessly represents the full
structure of German `§`-law citations **and** case citations (Aktenzeichen + court + ECLI).

Complements `architecture_review.md` (Phase 2 — strategy pattern & output migration) and
`ecosystem_comparison.md` (positioning in the ecosystem). This doc picks the concrete schema.

---

## 1. Starting Point: the Current Shape

Current model (`src/refex/models.py:11-175`):

- `extract() -> (content_with_[ref=UUID]markers, list[RefMarker])`
- `RefMarker`: `text, uuid, start, end, line, references: list[Ref]`
- `Ref` is a union model with fields that only make sense per `ref_type`:
  - **Law:** `ref_type=LAW, book, section, sentence`
  - **Case:** `ref_type=CASE, court, file_number, ecli, date`
- No `to_dict` / `to_json`; downstream code reaches into `__dict__`.
- Inline `[ref=UUID]...[/ref]` marker injection is **not a standard format** — no downstream
  tool consumes it, and it conflates extraction with rendering.

Constraints the new format must satisfy:

1. **Character-offset faithful** (the regex extractors already produce exact offsets; must not
   be lossy).
2. **Handles multiple refs per span** — a single `§§ 708 Nr. 11, 711 ZPO` marker expands into
   several normalised `Ref` objects today. Must be preserved.
3. **Handles cross-reference glue** (`i.V.m.`, `iVm`) that binds two markers.
4. **Type-discriminated** without Ref subclassing (a real pain point in the current code).
5. **Zero runtime deps** for the core shape — any interop format is produced via an adapter.
6. **Aligns with Darji 2023 schema** (the de-facto benchmark for German law references).

---

## 2. Formats Used by Peer Tools

| Tool | Format | Granularity | Typed fields? | Character offsets? |
|------|--------|-------------|---------------|--------------------|
| **spaCy** | `Doc` + `Span` (binary `DocBin`; `Doc.to_json()`) | token-indexed spans; char offsets via `span.start_char` | labels only (custom attrs via `span._.xxx`) | yes (via fast tokenizer) |
| **HF `token-classification` pipeline** | `list[dict]` with `entity/score/start/end/word` | character offsets | label only | yes |
| **GLiNER** | `list[dict]` with `text/label/start/end/score` | character offsets | label only | yes |
| **GROBID** | TEI-XML (`<bibl>`, `<author>`, `<biblScope unit="page">`, …) | rich nested structure | yes — scholarly bibliography fields | PDF bbox coords |
| **eyecite** | Typed Python dataclasses per citation kind (`FullCaseCitation`, `FullLawCitation`, `IdCitation`, `SupraCitation`, `ShortCaseCitation`, …); each has `span()`, `groups`, `metadata` | class-discriminated | yes — per-class fields | yes (`.span()`) |
| **Blackstone** | spaCy NER labels (`CASENAME`, `CITATION`, `INSTRUMENT`, `PROVISION`) + custom pipe for pairing | spaCy `Span` | label only | yes |
| **LexNLP** | Dicts: `{volume, reporter, reporter_full_name, page, page_range, court, year, source}` | character offsets + structured fields | yes | partial |
| **AnyStyle / ParsCit** | BibTeX / CSL-JSON for bibliographic records | record-level | yes (scholarly schema) | n/a (parse reference strings) |
| **doccano / Label Studio** | JSONL with `{text, label, start_offset, end_offset}` | character offsets | label only | yes |
| **CoNLL-U / BIO** | per-token tags `B-X / I-X / O` | token-level | label only | token-level |
| **W3C Web Annotation** | JSON-LD with `TextPositionSelector` / `TextQuoteSelector` | standoff | arbitrary body | yes |
| **Akoma Ntoso / LegalDocML.de** | XML with `<ref href="/akn/de/...">` URIs | document-level structure | yes (legal URIs) | document-structure |

### Observed consensus patterns

1. **Character-offset spans are universal** in NER-family tools (spaCy, HF, GLiNER, doccano).
   BIO/token-only tagging is legacy; every modern tool can round-trip to character offsets.
2. **Typed-per-citation-kind dataclasses** (eyecite, LexNLP) are the dominant pattern in the
   *legal* subfield. Union-style "one class with all fields nullable" (current `Ref`) does
   not appear in any peer tool.
3. **Standoff > inline markers.** No peer tool mutates the input text by inserting
   `[ref=UUID]` tags. The input string stays intact; annotations live in a separate list of
   objects that reference it by `(start, end)`.
4. **Rendering is a separate concern.** GROBID emits TEI, but also ships a hyperlinker
   (CiteURL/eyecite-style). The extraction output feeds the renderer, not vice-versa.
5. **JSONL is the lingua franca** for training data (HF datasets, doccano, Label Studio,
   Prodigy, spaCy's `.spacy` format can be dumped to JSONL).

---

## 3. Requirements Specific to German Legal Citations

Details the Darji schema captures that a generic NER span can't:

### Law references (Darji 2023 — 21 properties per annotation)

`law_book`, `Buch`, `Teil`, `Abschnitt`, `Unterabschnitt`, `Titel`, `Untertitel`,
`Kapitel`, `Unterkapitel`, `Paragraph`, `Absatz`, `Satz`, `Halbsatz`, `Nummer`,
`Buchstabe`, `Alternative`, `Variante`, plus range flags (`von`/`bis`), `f./ff.` markers,
and an optional free-text residual.

Current `Ref(book, section, sentence)` captures roughly **3 of 21**. The refactor should
expand this — but without hardcoding 21 columns into a base dataclass. A nested
`structure: dict[str, str]` with a documented key set fits better (see §5).

### Case references

`court`, `file_number` (Aktenzeichen), `ecli`, `date` — plus the ones not yet modelled:
`decision_type` (Urteil / Beschluss / Verfügung), `docket_parts` (chamber / file_no / year
split of the Aktenzeichen), `reporter` (BGHZ / NJW / …), `reporter_volume`, `reporter_page`,
`reporter_marginal` (`Rn.`), `parallel_citations`.

### Cross-reference relations

`i.V.m.` / `iVm` / `i. V. m.` binds two law markers. Also needed: `a.a.O.`, `ebenda`,
`siehe dort`, `vgl.` (the `supra/id/ibid` equivalents). These are **relations between
citations**, not properties of a single citation. W3C Web Annotation's `motivation: linking`
or spaCy's custom extension attributes both model this cleanly; a flat list of
`(source_id, target_id, relation)` triples works too.

### Short-form / id / supra (generation-zero gap)

Not addressed today. Format must have a slot for `kind: full | short | id | supra | ibid`
so future extractors can emit them without a schema bump.

---

## 4. Recommendation

### 4.1 Core in-memory model: typed dataclasses per citation kind

Follow the **eyecite pattern** — the only peer tool solving the same problem (legal
citations, regex-first, zero-ML):

```python
# src/refex/models.py (sketch)

@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int
    text: str

@dataclass(frozen=True, slots=True)
class Citation:
    """Base — never instantiated directly."""
    id: str                     # stable hash, not random UUID (reproducibility)
    span: Span
    kind: Literal["full", "short", "id", "supra", "ibid"]
    confidence: float = 1.0     # regex = 1.0; ML engines set probabilities
    source: str = "regex"       # which extractor produced it

@dataclass(frozen=True, slots=True)
class LawCitation(Citation):
    book: str                                   # e.g. "bgb", "vwgo"
    section: str                                # "§" number, e.g. "708"
    structure: dict[str, str] = field(default_factory=dict)
    # keys: "buch","teil","abschnitt","titel","paragraph","absatz","satz",
    #       "halbsatz","nummer","buchstabe","alternative","variante", ...
    # (Darji 2023 property set, documented as constants)
    range_end: str | None = None                # for §§ A bis B
    range_extensions: list[str] = field(default_factory=list)  # ["f", "ff"]

@dataclass(frozen=True, slots=True)
class CaseCitation(Citation):
    court: str | None = None                    # "BGH", "OVG Schleswig", ...
    file_number: str | None = None              # "1 KN 19/09"
    file_number_parts: dict[str, str] = field(default_factory=dict)
    # keys: "senate","register","serial","year"
    date: str | None = None                     # ISO 8601
    decision_type: str | None = None            # "Urteil" | "Beschluss" | ...
    ecli: str | None = None
    reporter: str | None = None                 # "BGHZ"
    reporter_volume: str | None = None
    reporter_page: str | None = None
    reporter_marginal: str | None = None        # "Rn. 23"
    parallel_citations: list["CaseCitation"] = field(default_factory=list)

@dataclass(frozen=True, slots=True)
class CitationRelation:
    source_id: str
    target_id: str
    relation: Literal["ivm", "aao", "ebenda", "vgl", "siehe"]
    span: Span                                  # the connector's own span
```

Why:
- **Type-discriminated.** `isinstance(c, LawCitation)` works; mypy narrows. No more
  `if ref.ref_type == RefType.LAW: use book`.
- **Stable IDs.** Hash `(kind, span, source)` — reproducible runs, diffable CI output.
  (The current random `uuid.uuid4()` breaks snapshot tests.)
- **Kind axis separate from type axis.** A `short`-form `LawCitation` is valid; a
  `supra`-form `CaseCitation` is valid.
- **Nested `structure: dict` for the long tail.** Avoids 20+ null columns and gives the
  Darji schema room to grow.
- **Relations are first-class.** `i.V.m.` doesn't have to be a "waiting marker" hack
  anymore.

### 4.2 Primary serialisation: JSONL with character-offset spans

One JSON object per document, written to a file of JSONL records. Aligns with doccano,
Label Studio, HF datasets, Prodigy, Darji's hosted dataset on HuggingFace.

```json
{
  "text": "Die Kostenentscheidung beruht auf § 154 Abs. 1 VwGO.",
  "citations": [
    {
      "id": "c_9f2a",
      "type": "law",
      "kind": "full",
      "span": {"start": 34, "end": 51, "text": "§ 154 Abs. 1 VwGO"},
      "book": "vwgo",
      "section": "154",
      "structure": {"absatz": "1"},
      "confidence": 1.0,
      "source": "regex"
    }
  ],
  "relations": []
}
```

Adapters (each ~30 lines, in `src/refex/adapters/`):

| Adapter | Purpose | Tools it talks to |
|---------|---------|-------------------|
| `to_jsonl` | primary format above | doccano, Label Studio, HF `datasets` |
| `to_spacy_doc` | `Doc` with `doc.ents` + `span._.citation` extension | spaCy / Blackstone downstream, training via `spacy train` |
| `to_hf_bio` | per-token BIO tagging | HF `token-classification` training |
| `to_gliner` | `{text, label, start, end}` list | GLiNER inference / evaluation |
| `to_web_annotation` | W3C Web Annotation JSON-LD with `TextPositionSelector` | hypothes.is, digital-humanities pipelines |
| `to_ref_marker` | legacy `[ref=UUID]...[/ref]` wrapping | existing Open Legal Data consumers (keep until migration done, then delete) |
| `to_akn_ref` | `<ref href="/akn/de/act/...">` for Akoma Ntoso / LegalDocML.de | the German federal legislative publication format |

Rationale for JSONL primary:
- Character-offset, tool-neutral, human-readable, streaming-friendly (one doc per line —
  good for batch ingestion, which is the actual workload).
- Directly loadable by `datasets.load_dataset("json", ...)` and doccano's importer.
- Matches Darji's HuggingFace dataset shape closely — benchmark runs become a one-adapter
  exercise.
- No schema validation dependency required; can add a JSON Schema doc separately if
  consumers want one.

### 4.3 Labels for NER-style consumers

Two-level flat label set when projecting to BIO / spaCy ents / GLiNER:

```
LAW_REF        — any §/Art. law citation
LAW_REF_SHORT  — short-form law ref (future)
CASE_REF       — any case citation (court + file number)
FILE_NUMBER    — bare Aktenzeichen without a court
COURT          — court name span
ECLI           — ECLI identifier span
REPORTER       — BGHZ/NJW-style reporter citation
RELATION_IVM   — i.V.m. connector
```

Structure / sub-fields do **not** become NER labels — they live in the JSONL `structure`
dict. This keeps the NER label space small enough for training on modest datasets while
leaving the rich structure available via the typed object model.

### 4.4 Keep inline markers as a render mode, not the core output

`to_ref_marker(text, citations) -> str` produces the current `[ref=UUID]...[/ref]` string.
Migrate Open Legal Data's pipeline to the JSONL output; retire the inline marker format
once nothing reads it.

---

## 5. Compatibility Matrix

| Consumer | Direct format | Adapter needed |
|----------|---------------|----------------|
| spaCy / Blackstone training | — | `to_spacy_doc` / `DocBin` |
| Hugging Face `token-classification` fine-tune | — | `to_hf_bio` |
| GLiNER zero-shot / fine-tune | — | `to_gliner` |
| doccano / Label Studio / Prodigy import | JSONL (primary) | none |
| Darji 2023 benchmark eval | JSONL (primary) | thin mapping of `structure` keys |
| Leitner 2020 NER benchmark | — | `to_hf_bio` with the LAW_REF/CASE_REF/COURT labels |
| GROBID-style TEI consumers | — | optional `to_tei` (low priority — scholarly, not legal) |
| Hypothes.is / Web Annotation ecosystem | — | `to_web_annotation` |
| Akoma Ntoso / LegalDocML.de | — | `to_akn_ref` |
| Open Legal Data legacy | — | `to_ref_marker` (deprecated) |

No single format covers every consumer, but the **JSONL core + thin adapters** design
minimises the surface each adapter has to handle. This is the GROBID pattern applied to
output instead of engines.

---

## 6. Migration Plan (fits into Phase 2 of `architecture_review.md`)

1. Add `Citation`, `LawCitation`, `CaseCitation`, `CitationRelation`, `Span` dataclasses
   alongside the existing `Ref` / `RefMarker`. Do not delete the old ones yet.
2. Have `RegexLawExtractor` / `RegexCaseExtractor` populate the new types natively; keep a
   `to_ref_marker` adapter for existing callers.
3. Add `to_jsonl` and land a golden-file test suite against the existing fixture set —
   locks current behaviour as a regression net.
4. Implement `to_spacy_doc` and `to_hf_bio` next (unlocks Phase 2.5 CRF training + Darji
   benchmark wiring).
5. Move Open Legal Data ingestion to consume the JSONL output; then delete
   `RefMarker.replace_content`, `[ref=UUID]` format constants, and the `Ref` union class.

---

## 7. What We Deliberately Don't Do

- **Don't emit TEI/XML as the primary format.** TEI is excellent for scholarly bibliography
  (GROBID's domain); legal citations have a different native vocabulary (Akoma Ntoso). Ship
  TEI only if a concrete consumer appears.
- **Don't adopt spaCy `Doc` as the primary format.** It pulls `spacy` into the default
  install, which violates the project's zero-dependency stance. Keep spaCy as an adapter
  target behind an extra.
- **Don't invent a new URI scheme** for citation IDs. Stable content-hash IDs are enough
  until there's a canonical catalogue to point at (gesetze-im-internet.de is the obvious
  one; wire this in only when a resolver exists).
- **Don't bake a JSON Schema file into the package yet.** The shape will drift through
  Phase 2–3; freeze it once the transformer extractor stabilises the field set.

---

## 8. Sources

### Format specifications
- [spaCy Doc.to_json / DocBin](https://spacy.io/api/doc)
- [spaCy SpanRuler / EntityRuler](https://spacy.io/api/spanruler)
- [HF token-classification pipeline output](https://huggingface.co/docs/transformers/main_classes/pipelines)
- [GLiNER on GitHub](https://github.com/urchade/GLiNER)
- [GROBID TEI encoding of results](https://grobid.readthedocs.io/en/latest/TEI-encoding-of-results/)
- [eyecite API documentation](https://freelawproject.github.io/eyecite/)
- [eyecite TUTORIAL.ipynb](https://github.com/freelawproject/eyecite/blob/main/TUTORIAL.ipynb)
- [LexNLP citation extraction](https://lexpredict-lexnlp.readthedocs.io/en/docs-0.1.6/modules/extract_en_citations.html)
- [Blackstone on GitHub](https://github.com/ICLRandD/Blackstone)
- [doccano export format](https://doccano.github.io/doccano/tutorial/)
- [CoNLL / IOB2 tagging](https://en.wikipedia.org/wiki/Inside%E2%80%93outside%E2%80%93beginning_(tagging))
- [W3C Web Annotation Data Model](https://www.w3.org/TR/annotation-model/)
- [Akoma Ntoso vocabulary (OASIS)](https://docs.oasis-open.org/legaldocml/akn-core/v1.0/akn-core-v1.0-part1-vocabulary.html)
- [ECLI — European Case Law Identifier](https://e-justice.europa.eu/topics/legislation-and-case-law/european-case-law-identifier-ecli_en)

### German legal NER datasets
- [PaDaS-Lab/legal-reference-annotations (Darji 2023)](https://huggingface.co/datasets/PaDaS-Lab/legal-reference-annotations)
- [A Dataset of German Legal Reference Annotations (Darji 2023 PDF)](https://ca-roll.github.io/downloads/A_Dataset_of_German_Legal_Reference_Annotations.pdf)
- [elenanereiss/Legal-Entity-Recognition (Leitner 2020)](https://github.com/elenanereiss/Legal-Entity-Recognition)
