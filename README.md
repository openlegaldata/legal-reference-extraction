# Legal Reference Extraction

Toolkit for extracting references from legal documents. References to law sections and case files are supported.

Supported countries:

- Germany

## Install

```bash
# latest from git
pip install git+https://github.com/openlegaldata/legal-reference-extraction.git

# specific version (using git tag)
pip install git+https://github.com/openlegaldata/legal-reference-extraction.git@v0.3.0

# local dev
make install
```

## Usage

```python
from refex.extractor import RefExtractor

extractor = RefExtractor()

content, markers = extractor.extract('<p>Ein Satz mit § 3b AsylG, und weiteren Sachen.</p>')
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
