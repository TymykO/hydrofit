# hydrofit

![CI](https://github.com/TymykO/hydrofit/actions/workflows/ci.yml/badge.svg)

Fit polynomials to instrument curves and export coefficient tables.

hydrofit imports x/y series from catalogue spreadsheets, keeps them as plain text, fits a
polynomial of a chosen degree, reports how well that fit holds, plots the data against it, and
exports coefficient tables in the column layouts that downstream spreadsheets expect.

**Status:** early development. Series can be imported from catalogue spreadsheets, listed,
inspected, fitted and evaluated; the coefficients reproduce the ones a legacy tool published
for the same curves. Measured across all fourteen catalogue curves, the largest relative
difference is 3.1e-12 — a measurement, and the only number here that no test holds. The two
that are held sit above it: 1e-10, some thirty times higher, so that a slow drift fails a test
long before it approaches the promise, and 1e-9, some three hundred times higher, which is the
promise. Series can also be plotted against their fit. Export is not implemented yet.

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

### Fit

```bash
hydrofit fit stad-10-52-851-010
```

```
series     stad-10-52-851-010
degree     6
x6         -22.92960500971207
x5         110.3138223543574
x4         -206.3105377713971
x3         191.08483423614774
x2         -92.85444040852808
x1         24.462548199081514
x0         -0.5732876628312868
r squared  0.9985481719731737
max error  0.08767295306030265
rmse       0.038552677500576324
```

The coefficients run in descending powers, the order a spreadsheet formula reads them in.
`--degree N` fits another degree (default: 6), and `--residuals` appends the difference between
the curve and every point.

A fit the data cannot resolve at the degree asked for says so, on a line that appears only
then — when the solver reports a rank below the number of coefficients that degree needs:

```
conditioning  rank 3 of the 7 coefficients a degree-6 fit needs: the data does not support it
```

The numbers above such a line are still printed, because they are what the request produced.
A rank below `degree + 1` does not mean the points fail to determine that many coefficients —
distinct points always do, in exact arithmetic — but that they do not determine them to a
precision the solver can resolve over so narrow an interval. What comes back is one of the
answers that fit, chosen by the solver, and it is at least six orders of magnitude larger than
the curve it claims to describe: that much is asserted by a test, while the digits themselves
are not, since another machine may choose a different answer. A series shorter than
`degree + 1` points is refused outright.

### Evaluate

```bash
hydrofit eval stad-10-52-851-010 --x 0.8
```

```
3.0373228261292198
```

Outside the range of the data the answer is marked, and the reason goes to stderr:

```
$ hydrofit eval stad-10-52-851-010 --x 2.0
warning: x=2.0 lies outside Kv [m³/h] 0.054 .. 1.36; a degree-6 polynomial diverges there
-32.808288634087845  [extrapolated]
```

The split is deliberate. A degree-6 polynomial does not merely lose accuracy outside its data,
it diverges — the setting above reads -32.8 where the instrument goes from 0.5 to 4 — so the
caveat has to survive `hydrofit eval ... > answer.txt`, which is why it is in the answer line
and not only in the sentence. The sentence stays out of that file for the opposite reason. This
is not an error: the exit code is 0.

A problem you can fix — an absent file, an unknown series, a sheet that breaks the convention —
arrives as one line on stderr and exit code 1, never as a traceback.

Two exit codes, and they do not mean the same thing:

| Code | What it says | Examples |
|---|---|---|
| `2` | the command line could not be parsed | an unknown flag, a missing required value, two mutually exclusive flags together such as `--compare-degree` with `--overlay` |
| `1` | the command line was understood and the work could not be done | an unknown series, a degree the series is too short to carry, two series that do not share their axes, a file that cannot be written |

The `2` cases never reach hydrofit's own code — argparse rejects them and prints its usage
line, which is why the message reads differently from every other error here. A script that
treats the two as one failure will retry a typo the same way it retries a missing file.

Units are printed as the catalogue spells them, so output can contain characters such as `³`.
On a Windows console still running a legacy code page, set `PYTHONIOENCODING=utf-8`; without it
hydrofit says so and stops rather than writing half a report.

### Plot

```bash
hydrofit plot stad-10-52-851-010 -o stad-10.png
```

```
stad-10.png
```

The figure carries the stored points as a scatter and the fitted polynomial as a line through
them, each axis labelled the way the catalogue spells it, unit in square brackets. There is no
legend: with a single curve there is nothing to tell apart. `--degree` chooses the polynomial
exactly as it does for `fit` and `eval`.

The only thing printed is the path that was written, spelled as your platform spells it:
separators normalised, and nothing else touched. It is not resolved against the filesystem, so
`./sub/../out.png` comes back with the `..` still in it. The figure itself is the output.

The curve is drawn across the range of the data and no further. Outside it a degree-6
polynomial diverges — the property `eval` spells out in a warning — and a picture has no line
to carry a warning on, so the drawing ends where the evidence ends.

`-o` is required, and the extension chooses the format: `png`, `pdf` and `svg` among others.
An unknown series, a degree the series is too short to carry, an extension matplotlib does not
write, or a path that cannot be opened — each arrives as one line on stderr and exit code 1,
like every other problem you can fix.

Two curves fit on one figure, and a legend then names each one with the quality of its fit:

```bash
hydrofit plot stad-10-52-851-010 --compare-degree 4 -o degrees.png
hydrofit plot stad-10-52-851-010 --overlay stad-15-52-851-015 -o sizes.png
```

`--compare-degree M` draws a second curve of that degree over the same points, which turns the
choice of degree from an argument into something you can look at. `--overlay SLUG` draws a
second series with its own fit. The two answer different questions and cannot be combined.

Each legend entry carries the series, the degree, and how closely that fit follows its points.
R² is left out whenever it is not a finite number — which is what a flat series produces, since
there is no variation for it to account for. `R2=nan` in a legend would read as a measurement
that came back strange rather than as one that was never possible.

Comparing a series with itself at the same degree is refused: two identical curves and two
identical legend entries read as a comparison and are not one.

`--overlay` is refused when the two series do not measure the same quantities — the message
names both axis labels, and nothing is written. Two units on one axis is a figure that lies,
and a picture outlives the session that made it.

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
