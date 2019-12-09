# Legal Reference Extraction

[![Build Status](https://travis-ci.org/openlegaldata/legal-reference-extraction.svg?branch=master)](https://travis-ci.org/openlegaldata/legal-reference-extraction)

Toolkit for extracting references from legal documents. References to law sections and case files are supported.

Supported countries:
- Germany

## Install

```
# from git
pip install git+https://github.com/openlegaldata/legal-reference-extraction.git#egg=legal-reference-extraction


# Local dev
pip install -r requirements.txt
```

## Usage

```python
from refex.extractor import RefExtractor

extractor = RefExtractor()

content, markers = extractor.extract('<p>Ein Satz mit § 3b AsylG, und weiteren Sachen.</p>')
```

## License

MIT
