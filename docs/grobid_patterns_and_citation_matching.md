# GROBID Deep Dive: Borrowable Patterns for Legal Citation Extraction & Matching

**Date:** 2026-08-24
**Scope:** In-depth analysis of GROBID's architecture, mapped to actionable patterns for
`legal-reference-extraction` and the planned citation matching extension.

---

## 1. GROBID's Architecture: The Cascade

GROBID's core innovation is a **cascade of small, composable sequence-labeling models**.
Instead of one monolithic model that tries to understand an entire document, GROBID chains
six+ specialized models, each with a small label set, where the output of one feeds the
input of the next.

### 1.1 The Model Chain

```
┌──────────────────────────────────────────────────────────────┐
│ PDF Document                                                 │
└──────────────┬───────────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────────┐
│ 1. Segmentation Model (line-level, CRF)                      │
│    Labels: header, body, bibliography, footnotes, headnotes  │
│    → Identifies document regions                             │
└──────────────┬───────────────────────────────────────────────┘
               ▼
       ┌───────┴───────┐
       ▼               ▼
┌─────────────┐  ┌──────────────────────────────────────┐
│ 2. Header   │  │ 3. Fulltext Model (token-level, CRF) │
│    Model    │  │    Labels: paragraphs, sections,      │
│  (BidLSTM-  │  │    inline citation callouts,          │
│   CRF)      │  │    figure/table refs                  │
│  → title,   │  │    → Finds "[12]", "Austin 2008(b)"  │
│  authors,   │  │    in running text                    │
│  abstract   │  └──────────────┬───────────────────────┘
└─────────────┘                 │ inline citation markers
                                ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. Reference-Segmenter Model (BidLSTM-ChainCRF-FEATURES)    │
│    → Splits bibliography section into individual ref strings │
└──────────────┬───────────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────────┐
│ 5. Citation Model (BidLSTM-CRF-FEATURES)                     │
│    Labels: author, title, year, journal, volume, pages, DOI  │
│    → Parses each reference string into structured fields     │
└──────────────┬───────────────────────────────────────────────┘
               ▼
       ┌───────┴───────┐
       ▼               ▼
┌─────────────┐  ┌─────────────┐
│ 6. Date     │  │ 7. Name     │
│    Model    │  │    Model    │
│  → ISO date │  │  → given,   │
│             │  │    surname  │
└─────────────┘  └─────────────┘
               ▼
┌──────────────────────────────────────────────────────────────┐
│ 8. Inline Citation Resolution                                │
│    → Links "[12]" in fulltext to bibliography entry #12      │
│    F1: 0.76–0.91                                             │
└──────────────┬───────────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────────┐
│ 9. Consolidation Service (biblio-glutton / CrossRef)         │
│    → Matches parsed ref to canonical entity with DOI         │
│    F1: >0.95 from PDF extraction                             │
│    Adds +12–13 F1 points to header extraction                │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 Key Design Properties

- **55 total leaf labels** across all models — but no single model has more than ~15.
  Each model is easy to train, debug, and iterate.
- **Per-model engine choice:** Segmentation uses fast CRF (line-level). Citation parsing
  uses BidLSTM-CRF-FEATURES (best accuracy). Fulltext stays CRF because input sequences
  are too long for current DL. Each model picks the right tool for its job.
- **Layout Tokens, not plain text.** GROBID doesn't operate on strings — it operates on
  tokens enriched with font name, font size, bold/italic/superscript, bounding box
  position, indentation, relative page position. These layout features are a separate
  input channel that consistently adds +3–5 F1 points.
- **Independently retrainable.** Update the citation model without touching segmentation.
  Swap CRF for BERT in one stage without rebuilding the pipeline.

---

## 2. The Consolidation Service (biblio-glutton)

This is the most directly relevant pattern for the planned citation matching extension.

### 2.1 Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ Parsed Reference (from GROBID extraction)                    │
│   {author: "Smith", title: "On Law", year: "2020",          │
│    journal: "MLR", volume: "83", pages: "1-20"}              │
└──────────────┬───────────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────────┐
│ biblio-glutton Matching Cascade                              │
│                                                              │
│  Step 1: Strong-ID lookup (LMDB)                             │
│     DOI / PMID / PMC / ISTEX ID → instant hit               │
│     Thousands of requests/sec                                │
│     ↓ miss                                                   │
│                                                              │
│  Step 2: First-author lastname + title (Elasticsearch)       │
│     Fuzzy text match against indexed metadata                │
│     ↓ miss                                                   │
│                                                              │
│  Step 3: Journal + volume + first page (Elasticsearch)       │
│     Structured field match                                   │
│     ↓ miss                                                   │
│                                                              │
│  Step 4: Full raw reference string (Elasticsearch)           │
│     Most expensive, last resort                              │
│     ↓ miss                                                   │
│                                                              │
│  Step 5: No match → return extracted fields only             │
└──────────────┬───────────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────────┐
│ Consolidated Output                                          │
│   {doi: "10.1234/...", pmid: "...", oa_url: "...",           │
│    author, title, year, journal, volume, pages,              │
│    match_confidence: 0.97}                                   │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Two-Tier Storage

| Tier | Tech | Purpose | Speed |
|------|------|---------|-------|
| Fast lookup | LMDB (embedded key-value) | Exact ID resolution | Thousands/sec |
| Fuzzy matching | Elasticsearch cluster | Text-based search | Scales horizontally |

LMDB handles the common case (exact ID match) at embedded-DB speed. Elasticsearch is only
invoked when the fast path misses — this keeps average latency low even at batch scale.

### 2.3 Metadata Aggregation

biblio-glutton merges data from multiple sources into a single enriched record:
- **CrossRef** — DOI, title, authors, journal metadata
- **PubMed / PubMed Central** — PMID, PMC ID, MeSH terms
- **Unpaywall** — Open Access URLs
- **ISTEX** — French academic full-text archive

Daily sync keeps the local index current with CrossRef updates.

### 2.4 The Critical Insight

**Consolidation adds +12–13 F1 points** to extraction quality. Even imperfect extraction,
when matched against a knowledge base, produces much better results than extraction alone.
The KB acts as a correctional layer — it normalizes variants, fills missing fields, and
rejects false positives that don't match any known entity.

**For Open Legal Data, this means: a matching service against the existing OLDP database
may be more impactful than improving the regex extractor.**

---

## 3. Inline Citation Resolution (eyecite Pattern)

Separate from consolidation (matching to a DB), there's a **resolution** step: linking
abbreviated in-text references back to their full antecedent within the same document.

### 3.1 GROBID's Approach

The fulltext model finds inline markers (`[12]`, `Austin 2008(b)`) and links them to
bibliography entries. This is an **intra-document linking** problem. F1: 0.76–0.91.

### 3.2 eyecite's Approach (Legal-Specific)

eyecite's `resolve_citations()` clusters citation mentions by type:

| Resolver | Example | Resolution |
|----------|---------|------------|
| `resolve_full_citation()` | "Bush v. Gore, 531 U.S. 98" | Creates canonical `Resource` |
| `resolve_shortcase_citation()` | "531 U.S., at 99" | Matches to full cite by reporter+volume |
| `resolve_supra_citation()` | "Bush, supra, at 100" | Matches to full cite by case name |
| `resolve_id_citation()` | "Id., at 101" | Links to immediately preceding cite |

Returns: `dict[Resource, list[Citation]]` — one canonical entity per group of mentions.

Custom resolvers can be plugged in for DB-backed resolution (e.g., CourtListener).

### 3.3 German Legal Equivalents (Not Currently Handled)

| German form | English equivalent | Current support |
|-------------|-------------------|-----------------|
| `§ 42 VwGO` (full) | Full citation | ✓ Handled |
| `i.V.m. § 42 VwGO` | Cross-reference | Partial (waiting markers) |
| `a.a.O.` (am angegebenen Ort) | Supra | ✗ Not handled |
| `ebenda` | Ibid / Id. | ✗ Not handled |
| `s. dort` / `wie oben` | See above | ✗ Not handled |
| `Abs. 2` (bare, after full cite) | Short form | ✗ Not handled |
| `die genannte Vorschrift` | "said provision" | ✗ Not handled |

An eyecite-style resolution pass would handle these by scanning backward from each
abbreviated reference to find its full antecedent.

---

## 4. Mapped to Legal-Reference-Extraction

### 4.1 The Legal Cascade (Borrowing GROBID's Pattern)

```
┌──────────────────────────────────────────────────────────────┐
│ Court Decision (HTML/text)                                   │
└──────────────┬───────────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────────┐
│ 1. Segmenter                                                 │
│    Identifies citation-dense regions:                        │
│    Tenor, Tatbestand, Entscheidungsgründe, Leitsätze         │
│    (Optional — helps focus extraction and provides context)  │
│    Engine: regex or lightweight CRF                          │
└──────────────┬───────────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. Finder                                                    │
│    Finds reference spans in text                             │
│    Outputs: [(start, end, text, ref_type), ...]              │
│    Engine: regex (current), CRF, or transformer              │
│    Law finder: §/§§ patterns                                 │
│    Case finder: Aktenzeichen patterns                        │
└──────────────┬───────────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. Parser                                                    │
│    Decomposes each span into structured fields               │
│    Law:  (book, section, absatz, satz, nr, alt)              │
│    Case: (court, file_number, date, ecli)                    │
│    Engine: regex (current), CRF, or transformer              │
└──────────────┬───────────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. Resolver (NEW — eyecite pattern)                          │
│    Links abbreviated refs to full antecedents:               │
│    a.a.O. → preceding full cite                              │
│    i.V.m. → cross-reference (partial today)                  │
│    bare "Abs. 2" → most recent § cite                        │
│    Engine: heuristic (distance-based, backward scan)         │
└──────────────┬───────────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────────┐
│ 5. Matcher (NEW — biblio-glutton pattern)                    │
│    Maps parsed ref to canonical entity in OLDP DB            │
│    Cascade: exact ID → field match → fuzzy → raw string      │
│    Engine: OLDP Elasticsearch + SQLite/LMDB                  │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 What Changes vs. Current Architecture

| Current | Proposed | GROBID analog |
|---------|----------|---------------|
| One `extract()` method does find + parse + tag | Three separate stages (find, parse, tag) | Cascade of models |
| Mixin inheritance composes extractors | Strategy/protocol composes extractors | Model registry |
| `[ref=UUID]...[/ref]` only output | Structured output (JSON/dataclass) primary, markers as optional rendering | TEI output |
| No resolution step | Resolver for a.a.O., ebenda, bare Abs. refs | Fulltext inline resolution |
| No matching step | Matcher service against OLDP DB | biblio-glutton consolidation |
| No layout features | HTML tag features (link, bold, heading level) | Layout Tokens |
| All regex, no ML | Per-stage engine choice | CRF/BidLSTM/BERT per model |

---

## 5. Citation Matching Architecture for OLDP

### 5.1 The Matching Service

Borrowing from biblio-glutton's two-tier design, adapted for legal data:

```
┌──────────────────────────────────────────────────────────────┐
│ Parsed Reference                                             │
│   Law:  Ref(book="vwgo", section="42")                       │
│   Case: Ref(court="BVerwG", file_number="10 C 23.12")       │
└──────────────┬───────────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────────┐
│                    Matching Cascade                           │
│                                                              │
│  ┌─ LAW REFERENCES ───────────────────────────────────────┐  │
│  │                                                        │  │
│  │  Step 1: Exact (book_code, section) lookup             │  │
│  │     SQLite/LMDB index of OLDP law entities             │  │
│  │     "vwgo" + "42" → law_id=12345                       │  │
│  │     ↓ miss                                             │  │
│  │                                                        │  │
│  │  Step 2: Book-name normalization via alias table       │  │
│  │     "verwaltungsgerichtsordnung" → "vwgo"              │  │
│  │     "außensteuergesetz" → "astg"                       │  │
│  │     Handles genitive: "gesetzes" → "gesetz"            │  │
│  │     ↓ miss                                             │  │
│  │                                                        │  │
│  │  Step 3: Fuzzy book name (Elasticsearch)               │  │
│  │     Trigram/phonetic matching on law titles             │  │
│  │     ↓ miss                                             │  │
│  │                                                        │  │
│  │  Step 4: Unmatched → return fields only + flag         │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ CASE REFERENCES ──────────────────────────────────────┐  │
│  │                                                        │  │
│  │  Step 1: ECLI exact lookup (if ECLI extracted)         │  │
│  │     ECLI:DE:BVERWG:2013:200213U10C23.12.0 → case_id   │  │
│  │     ↓ miss or no ECLI                                  │  │
│  │                                                        │  │
│  │  Step 2: Exact (court, normalized_file_number) lookup  │  │
│  │     "bverwg" + "10 c 23.12" → case_id=67890           │  │
│  │     ↓ miss                                             │  │
│  │                                                        │  │
│  │  Step 3: Court-name normalization + file number match  │  │
│  │     "Bundesverwaltungsgericht" → "bverwg"              │  │
│  │     "OVG Nordrhein-Westfalen" → "ovg nrw"             │  │
│  │     ↓ miss                                             │  │
│  │                                                        │  │
│  │  Step 4: Fuzzy match (Elasticsearch)                   │  │
│  │     Court name variants + file number + optional date  │  │
│  │     ↓ miss                                             │  │
│  │                                                        │  │
│  │  Step 5: Unmatched → return fields only + flag         │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────┬───────────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────────┐
│ Matched Output                                               │
│   Law:  {law_id: 12345, book: "vwgo", section: "42",        │
│          match_confidence: 1.0, match_step: "exact"}         │
│   Case: {case_id: 67890, court: "BVerwG",                   │
│          file_number: "10 C 23.12", ecli: "ECLI:DE:...",    │
│          match_confidence: 0.95, match_step: "fuzzy"}        │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 OLDP Already Has Most of the Infrastructure

| Component | biblio-glutton | OLDP equivalent | Gap |
|-----------|---------------|-----------------|-----|
| Knowledge base | CrossRef dump | OLDP law + case DB | ✓ Exists |
| Fuzzy search | Elasticsearch | OLDP Elasticsearch | ✓ Exists |
| Fast exact lookup | LMDB | Not present | Build SQLite/LMDB index |
| Metadata sync | CrossRef daily API | Law/case ingestion pipeline | ✓ Exists |
| Matching API | biblio-glutton REST | Not present | Build as library or service |
| Alias tables | N/A | Not present | Build book-code + court-name alias tables |

**The gap is narrow.** OLDP has the knowledge base (laws and court decisions) and the
search engine (Elasticsearch). What's missing is:

1. A fast exact-lookup index (SQLite or LMDB, built from OLDP data).
2. Normalization / alias tables for book codes and court names.
3. The matching cascade logic itself.
4. Confidence scoring and match-step tracking.

### 5.3 Implementation: Library vs. Service

biblio-glutton is a separate microservice (Java, REST API). For OLDP:

**Start as a library** (Python package, no network overhead). Reasons:
- Batch processing (no latency budget — no need for HTTP).
- Single consumer (OLDP pipeline).
- Zero-dependency constraint fits a library better than a service.
- Can graduate to a service later if other consumers appear.

Proposed API:

```python
class LegalMatcher:
    """Matches extracted references to canonical OLDP entities."""

    def __init__(self, law_index: LawIndex, case_index: CaseIndex):
        ...

    def match_law(self, book: str, section: str) -> MatchResult:
        """Cascade: exact → alias → fuzzy → unmatched."""
        ...

    def match_case(self, court: str, file_number: str,
                   date: str | None = None,
                   ecli: str | None = None) -> MatchResult:
        """Cascade: ECLI → exact → normalized → fuzzy → unmatched."""
        ...

    def match_refs(self, refs: list[Ref]) -> list[MatchResult]:
        """Batch matching for all refs from one document."""
        ...

@dataclass
class MatchResult:
    ref: Ref                          # Original extracted reference
    entity_id: int | None             # OLDP entity ID (None if unmatched)
    confidence: float                 # 0.0–1.0
    match_step: str                   # "exact", "alias", "fuzzy", "unmatched"
    canonical: dict[str, str] | None  # Normalized fields from KB
```

### 5.4 Alias Tables

The single highest-value data asset for matching. Two tables:

**Book code aliases** (maps variants to canonical code):
```
verwaltungsgerichtsordnung    → vwgo
bürgerliches gesetzbuch       → bgb
bürgerlichen gesetzbuchs      → bgb      (genitive)
bürgerlichen gesetzbuches      → bgb      (genitive)
grundgesetz                    → gg
asylgesetz                     → asylg
sozialgesetzbuch               → sgb
...
```

**Court name aliases** (maps variants to canonical identifier):
```
bundesverwaltungsgericht       → bverwg
bverwg                         → bverwg
ovg nordrhein-westfalen        → ovg nrw
ovg nrw                        → ovg nrw
schleswig-holsteinisches ovg   → ovg sh
ovg schleswig                  → ovg sh
schl.-holst. ovg               → ovg sh
...
```

These tables can be bootstrapped from the existing `law_book_codes.txt`,
`file_number_codes.csv`, and the court/state lists already hardcoded in `case.py`.

---

## 6. What to Borrow from GROBID (and What Not To)

### 6.1 Borrow

| Pattern | GROBID implementation | Legal adaptation | Priority |
|---------|----------------------|------------------|----------|
| **Cascade of small models** | 6+ models, 55 labels total | Segmenter → Finder → Parser → Resolver → Matcher | High |
| **Per-stage engine choice** | CRF for fast, BidLSTM for accurate, BERT for best | Regex default, CRF optional, transformer optional | High |
| **Consolidation service** | biblio-glutton (LMDB + Elasticsearch) | OLDP matcher (SQLite + existing Elasticsearch) | **Highest** |
| **Matching cascade** | Strong ID → fields → raw string | ECLI → (court, fn) → alias → fuzzy | **Highest** |
| **Layout features as separate channel** | Font, position, bold, bounding box | HTML tags, heading level, link context, list markers | Medium |
| **Two-tier storage** | LMDB (fast exact) + ES (fuzzy) | SQLite (fast exact) + OLDP ES (fuzzy) | High |
| **Confidence + match-step tracking** | Match quality metadata in output | `MatchResult(confidence, match_step)` | High |
| **Inline citation resolution** | Fulltext model links callouts to bibliography | Resolver links a.a.O./ebenda/bare Abs. to antecedent | Medium |
| **Training data format** | TEI with human review gate | CoNLL-2002 (Darji/Leitner format) with review gate | Medium |
| **Instance vs field F1** | Separate metrics for whole-ref and per-field accuracy | Report both in benchmark CI | Medium |

### 6.2 Don't Borrow

| Pattern | Why not |
|---------|---------|
| **Java stack** | Project is Python; stay Python |
| **PDF layout tokens** | Input is HTML/text, not PDF; HTML features are the analog |
| **TEI output format** | Align with OLDP's Django models and JSON API instead |
| **Separate microservice** | Single consumer (OLDP batch pipeline); start as library |
| **GROBID's fulltext model** | Their sequences are too long for DL; same issue applies to legal documents; regex/heuristic segmentation is sufficient |
| **GROBID's segmentation model** | German court decisions have simpler structure than academic papers; regex on Tenor/Tatbestand/Gründe headings suffices initially |
| **Reference-segmenter model** | Legal refs are inline, not in a bibliography section; the finder stage handles this |

---

## 7. GROBID's Biggest Lesson for OLDP

**Consolidation is more impactful than better extraction.**

GROBID's numbers:
- Extraction alone (no consolidation): F1 ~0.75 for header metadata
- Extraction + biblio-glutton consolidation: F1 ~0.89 (+12–13 points)
- Consolidation match rate: >0.95 F1

The knowledge base acts as a **correctional layer**:
- Normalizes abbreviation variants ("Verwaltungsgerichtsordnung" → "VwGO")
- Fills missing fields (court name not found by heuristic → infer from file number + DB)
- Rejects false positives (extracted "book code" that doesn't exist in law DB)
- Resolves ambiguity (multiple courts with same abbreviation → pick by file number format)

For Open Legal Data, this means:

1. **Phase 0 (benchmark) and Phase 5 (matcher) have the highest ROI.** The matcher
   directly leverages the existing OLDP database — 100k+ court decisions and law texts
   already indexed.

2. **The current extractor's false positives** (from the overly-permissive
   `[A-Z]...V|G|O|B` book pattern) would be caught by the matcher — if the "book code"
   doesn't match any law in the DB, reject it.

3. **Improving the regex extractor matters less if the matcher is good.** A mediocre
   extractor + strong matcher outperforms a strong extractor + no matcher.

---

## 8. Revised Roadmap (Incorporating GROBID Patterns)

| Phase | Content | GROBID pattern borrowed | Effort |
|-------|---------|------------------------|--------|
| **0** | Establish benchmark (Darji + Leitner) | Instance vs. field F1 metrics | Small |
| **1** | Audit + cleanup (measured against benchmark) | — | Small |
| **2** | Pipeline refactor: Finder → Parser → Tagger as separate stages | Cascade architecture | Medium |
| **3** | Resolver: a.a.O., ebenda, bare Abs. → antecedent | Inline citation resolution | Medium |
| **4** | **Matcher: SQLite index + alias tables + OLDP ES** | **biblio-glutton consolidation** | Medium |
| **5** | CRF extractor option (per-stage engine choice) | Per-model engine selection | Medium |
| **6** | Transformer option (PaDaS-Lab/gbert-legal-ner) | BidLSTM-CRF → BERT-CRF upgrade path | Large |

**Phase 4 (matcher) is moved up** — it has the highest expected impact for the least
effort, given that OLDP already has Elasticsearch and the knowledge base. Alias tables +
SQLite index + cascade logic is weeks of work, not months. And it immediately improves
quality for the 444k citation dataset.

---

## Sources

- [GROBID on GitHub](https://github.com/kermitt2/grobid)
- [How GROBID works (Principles)](https://grobid.readthedocs.io/en/latest/Principles/)
- [GROBID Deep Learning models](https://github.com/grobidOrg/grobid/blob/master/doc/Deep-Learning-models.md)
- [GROBID Consolidation](https://grobid.readthedocs.io/en/latest/Consolidation/)
- [GROBID Training](https://grobid.readthedocs.io/en/latest/Training-the-models-of-Grobid/)
- [biblio-glutton on GitHub](https://github.com/kermitt2/biblio-glutton)
- [biblio-glutton matching discussion (Issue #21)](https://github.com/kermitt2/biblio-glutton/issues/21)
- [eyecite on GitHub](https://github.com/freelawproject/eyecite)
- [eyecite whitepaper](https://free.law/pdf/eyecite-whitepaper.pdf)
- [BO-ECLI Parser Engine](https://ceur-ws.org/Vol-2143/paper4.pdf)
- [ECLI on EUR-Lex](https://eur-lex.europa.eu/content/help/eurlex-content/ecli.html)
- [OLDP on GitHub](https://github.com/openlegaldata/oldp)
