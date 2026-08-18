# hydrofit

![CI](https://github.com/TymykO/hydrofit/actions/workflows/ci.yml/badge.svg)

Fit polynomials to instrument curves and export coefficient tables.

hydrofit imports x/y series from catalogue spreadsheets, keeps them as plain text, fits a
polynomial of a chosen degree, reports how well that fit holds, plots the data against it, and
exports coefficient tables in the column layouts that downstream spreadsheets expect.

**Status:** early development. The distribution installs and the gates run; the command set is
not implemented yet.

## Requirements

Python 3.12.

## Installation

```bash
pip install -e .
```

## Usage

Documented once the command set exists.

## Architecture

Documented once there is more than an empty package to describe.

## Development

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux, macOS
pip install -r requirements.txt
pip install -e .
pre-commit install
```

`pre-commit install` sets up two stages: formatting and typing are checked when you commit,
the test suite runs when you push. The hooks call the tools from this environment rather than
from isolated ones, so the virtualenv has to be active — otherwise they stop with
`Executable not found` rather than passing quietly.

## Testing

```bash
pytest
coverage run -m pytest
coverage report -m
```

The same three gates run in CI on every push and pull request: lint, typecheck, tests.

## License

MIT — see [LICENSE](LICENSE).
