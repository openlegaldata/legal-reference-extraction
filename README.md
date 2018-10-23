# Legal Reference Extraction

Toolkit for extracting references from legal documents. References to law sections and case files are supported.

Supported countries:
- Germany

## Install

```
pip install -r requirements.txt
```

## Usage

```python
from refex.extractor import RefExtractor

extractor = RefExtractor()

content, markers = self.extractor.extract('<p>Ein Satz mit § 3b AsylG, und weiteren Sachen.</p>')
```

## License

MIT
