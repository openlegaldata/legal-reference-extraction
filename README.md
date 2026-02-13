# Legal Reference Extraction

A toolkit for extracting references and citations from legal documents. References to law sections and case files are supported.

Supported countries:

- Germany (used by [de.openlegaldata.io](https://de.openlegaldata.io/))

## Install

```bash
pip install legal-reference-extraction

# or install from git
pip install git+https://github.com/openlegaldata/legal-reference-extraction.git

# local dev
make install
```

## Usage

```python
from refex.extractor import RefExtractor

extractor = RefExtractor()

content, markers = extractor.extract('<p>Ein Satz mit § 3b AsylG, und weiteren Sachen.</p>')
```

### Examples

**Single law reference** -- a basic `§` citation is extracted with the section number and law book code:

```python
from refex.extractor import RefExtractor

extractor = RefExtractor()

content, markers = extractor.extract(
    "Die Entscheidung beruht auf § 42 VwGO."
)

for marker in markers:
    for ref in marker.get_references():
        print(ref)
# <Ref(law: vwgo/42)>
```

The returned `content` wraps each matched reference with marker tags:
```
Die Entscheidung beruht auf [ref=<uuid>]§ 42 VwGO[/ref].
```

**Multiple sections from the same law** -- `§§` with comma-separated or semicolon-separated sections:

```python
content, markers = extractor.extract(
    "Bar und bar §§ 1, 2 Abs. 2, 3, 10 Abs. 1 Nr. 1 BGB foo."
)

refs = [ref for m in markers for ref in m.get_references()]
print(sorted(refs))
# [<Ref(law: bgb/1)>, <Ref(law: bgb/10)>, <Ref(law: bgb/2)>, <Ref(law: bgb/3)>]
```

**Cross-references between laws** -- `i.V.m.` (in conjunction with) linking sections across different law books:

```python
content, markers = extractor.extract(
    "Die Entscheidung über die vorläufige Vollstreckbarkeit folgt aus "
    "§ 167 VwGO i.V.m. §§ 708 Nr. 11, 711 ZPO."
)

refs = [ref for m in markers for ref in m.get_references()]
print(sorted(refs))
# [<Ref(law: vwgo/167)>, <Ref(law: zpo/708)>, <Ref(law: zpo/711)>]
```

**Case references** -- court names and file numbers are extracted from citations:

```python
extractor = RefExtractor()
extractor.do_law_refs = False  # only extract case references
extractor.do_case_refs = True

content, markers = extractor.extract(
    "Das OVG Schleswig habe bereits in seinem Urteil vom 22.04.2010 "
    "(1 KN 19/09) zur im Wesentlichen gleichlautenden Vorgängervorschrift "
    "im LROP-TF 2004 festgestellt, dass dieser Vorschrift die erforderliche "
    "Bestimmtheit nicht zukomme."
)

for marker in markers:
    for ref in marker.get_references():
        print(ref)
# <Ref(case: OVG Schleswig/1 KN 19/09/)>
```

**Multiple case references** -- multiple courts and file numbers from a single passage:

```python
content, markers = extractor.extract(
    "(vgl. BVerwG, Beschluss vom 12.11.1987 - 4 B 216/87 -, juris [Rn. 2]; "
    "VGH BW, Urteil vom 10.01.2007 - 3 S 1251/06 -, juris [Rn. 25])"
)

for marker in markers:
    for ref in marker.get_references():
        print(ref.court, ref.file_number)
# BVerwG 4 B 216/87
# VGH BW 3 S 1251/06
```

**Law book context** -- when extracting from within a specific law's text, set `law_book_context` to resolve bare `§` references without an explicit book code:

```python
extractor = RefExtractor()
extractor.do_case_refs = False
extractor.law_book_context = "bgb"

content, markers = extractor.extract(
    "Der Vorsitzende kann einen solchen Vertreter auch bestellen, "
    "wenn in den Fällen des § 20 eine nicht prozessfähige Person bei dem "
    "Gericht ihres Aufenthaltsortes verklagt werden soll."
)

refs = [ref for m in markers for ref in m.get_references()]
print(refs[0])
# <Ref(law: bgb/20)>
```

## Development

```bash
make install   # create venv + install in editable mode with dev deps
make test      # run pytest
make lint      # ruff check + format check
make format    # auto-fix lint + format
```

## See also

- [CiteURL supports citations to U.S. court decisions and U.S. code](https://github.com/raindrum/citeurl)

## License

MIT
