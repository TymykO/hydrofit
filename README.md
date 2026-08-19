# hydrofit

![CI](https://github.com/TymykO/hydrofit/actions/workflows/ci.yml/badge.svg)

Fit polynomials to instrument curves and export coefficient tables.

hydrofit imports x/y series from catalogue spreadsheets, keeps them as plain text, fits a
polynomial of a chosen degree, reports how well that fit holds, plots the data against it, and
exports coefficient tables in the column layouts that downstream spreadsheets expect.

**Status:** early development. Series can be imported from catalogue spreadsheets, listed and
inspected. Fitting, plotting and export are not implemented yet.

## Requirements

Python 3.12.

## Installation

```bash
pip install -e .
```

## Usage

### Import

**hydrofit knows no products.** It has no table of valves, no list of vessels, and no opinion
about what any quantity means. Everything it knows comes from the sheet:

| Where | What it carries |
|---|---|
| sheet name | `<product> \| <article no.>` — the identity, and the slug the series is stored under |
| cell `A1` | label for column A, which is the **y axis**: the computed quantity |
| cell `B1` | label for column B, which is the **x axis**: the free variable |
| both labels | `name [unit]`, taken exactly as written; the unit is never empty |

Which quantities those are is entirely up to the sheet, and the axis roles follow from how the
data was made rather than from what the product is. A balancing valve carries `n [-]` over
`Kv [m³/h]` — the setting is what you turn, kv is what follows from it. A pressurisation vessel
carries `Δp [kPa]` over `q [m³/h]` — there the flow is what you turn and the pressure drop
follows. hydrofit reads both the same way and invents nothing about either; the names and units
in its output are the ones your spreadsheet wrote.

Decimal commas are accepted. A sheet that cannot describe a series is reported against that
sheet and the rest of the workbook still lands; only a problem with the file itself stops the
import.

```bash
hydrofit import "BV - IMI.xlsx"
```

```
imported 14 series from BV - IMI.xlsx
  stad-10-52-851-010  generated  701 points
  ...
  ta-bvs-243-dn250-6-52-240-094  raw  17 points
```

Each series is classified `generated` or `raw` by its shape — dense and evenly stepped on
either axis means generated — and `--kind raw|generated` overrides that for the whole file.
`--sheet NAME` imports a single sheet, `--store DIR` chooses where the series are kept
(default: `store`).

### List and inspect

```bash
hydrofit list --product stad
```

```
slug                product  kind       points  x range       y range
stad-10-52-851-010  STAD 10  generated  701     0.054 .. 1.36  0.5 .. 4
...
7 series
```

`--product` matches any part of the product name, case-insensitively, so `stad` finds every
`STAD` size at once. `--kind` narrows to one kind.

```bash
hydrofit show stad-10-52-851-010
```

```
slug          stad-10-52-851-010
product       STAD 10
article no.   52 851-010
kind          generated
points        701
x axis        Kv [m³/h]
y axis        n [-]
x range       0.054 .. 1.36
y range       0.5 .. 4
source file   BV - IMI.xlsx
source sheet  STAD 10 | 52 851-010
imported at   2026-08-19T12:11:11+00:00
```

`--points` appends every pair, written so that no digit is lost in the printing.

A problem you can fix — an absent file, an unknown series, a sheet that breaks the convention —
arrives as one line on stderr and exit code 1, never as a traceback.

Units are printed as the catalogue spells them, so output can contain characters such as `³`.
On a Windows console still running a legacy code page, set `PYTHONIOENCODING=utf-8`; without it
hydrofit says so and stops rather than writing half a report.

## Architecture

Documented once the full path — import, fit, plot, export — exists to describe.

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
