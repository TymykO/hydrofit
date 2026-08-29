"""Command line surface: import a workbook, list and inspect what is stored, fit, evaluate.

Thin by design — parse arguments, call a module, print. No domain logic lives here.

Two things happen at this edge and nowhere else. The clock is read here, so that everything
below stays deterministic and a stored catalogue is byte-identical between runs. And
`HydrofitError` is turned into a message plus exit code 1 here, so that a problem the user can
fix never reaches them as a traceback.
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from hydrofit.errors import HydrofitError
from hydrofit.fitting import DEFAULT_DEGREE, PolynomialFit
from hydrofit.importer import import_workbook
from hydrofit.models import DataKind, Series
from hydrofit.plotting import figure_for_fit
from hydrofit.store import SeriesStore

# Said in full because the alternative reads as a bug: `--product DN10` will one day also return
# `DN100`, and a user who was never told about substring matching will file that as one.
_PRODUCT_HELP = "matches any part of the product name, case-insensitive"

# Spelled out because the layout is the one thing a user must get right, and because nothing in
# hydrofit knows what a valve or a vessel is — a reader who assumes otherwise will look for a
# product setting that does not exist.
_IMPORT_DESCRIPTION = """\
hydrofit knows no products. One sheet becomes one series, read like this:

  sheet name   <product> | <article no.>   the identity, and the slug
  cell A1      labels column A, the y axis: the computed quantity
  cell B1      labels column B, the x axis: the free variable
  labels       name [unit], taken exactly as written, unit never empty

Which quantities those are is entirely up to the sheet. A balancing valve
carries n [-] over Kv [m³/h]: the setting is turned, kv follows from it.
A pressurisation vessel carries Δp [kPa] over q [m³/h]: the flow is turned,
the pressure drop follows. hydrofit reads both the same way, and invents
nothing about either.
"""

_DEFAULT_STORE = "store"

# Plain ASCII on purpose. The only characters in hydrofit's output that a legacy console cannot
# render should be the ones the data itself carries, such as the unit m³/h — decoration has no
# business adding to that list.
_RANGE_SEPARATOR = " .. "

# Attached to the answer itself rather than printed beside it. Either single-stream choice
# fails a user who redirects: everything on stdout writes prose into what is otherwise a file
# holding one number, and everything on stderr strips the caveat off a value that needs it. In
# the line, the caveat travels wherever the number travels.
_EXTRAPOLATED = "  [extrapolated]"


def _emit(lines: Sequence[str], out: TextIO) -> None:
    """Write a whole block of output in one call.

    Building the block first is not a style preference. Encoding happens before the first byte
    reaches the stream, so a console that cannot render a unit fails with nothing written rather
    than with half a report on screen and an error underneath it.

    Args:
        lines: The lines to write, without terminators.
        out: Stream to write to.
    """
    print("\n".join(lines), file=out)


def _fmt_range(bounds: tuple[float, float]) -> str:
    """Render a low/high pair for a table.

    Args:
        bounds: The low and high value.

    Returns:
        The pair as text.
    """
    return f"{bounds[0]:g}{_RANGE_SEPARATOR}{bounds[1]:g}"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    """Lay out rows in columns wide enough for their contents.

    Args:
        headers: Column headings.
        rows: Cell text, one sequence per row.

    Returns:
        The rendered lines, heading first. Trailing padding is stripped so that no line carries
        invisible differences into a reference file.
    """
    widths = [
        max(len(str(cell)) for cell in column)
        for column in zip(headers, *rows, strict=True)
    ]
    return [
        "  ".join(
            cell.ljust(width) for cell, width in zip(line, widths, strict=True)
        ).rstrip()
        for line in (headers, *rows)
    ]


def _run_import(args: argparse.Namespace, out: TextIO) -> int:
    """Read a workbook into the store.

    A sheet that cannot describe a series is reported as a warning and the rest of the workbook
    still lands — the contract puts sheet-level problems against the sheet. The operation only
    fails when nothing at all could be imported, because that is the case where the user asked
    for something and received nothing.

    Args:
        args: Parsed arguments.
        out: Stream to write the report to.

    Returns:
        Process exit code.

    Raises:
        HydrofitError: If the file itself cannot be read.
    """
    result = import_workbook(
        args.path,
        imported_at=datetime.now(tz=UTC).isoformat(timespec="seconds"),
        kind=args.kind,
        sheet=args.sheet,
    )

    for problem in result.problems:
        print(f"warning: {problem.sheet}: {problem.message}", file=sys.stderr)

    store = SeriesStore(Path(args.store))
    for series in result.series:
        store.save(series)

    skipped = f", skipped {len(result.problems)} sheet(s)" if result.problems else ""
    _emit(
        [
            f"imported {len(result.series)} series from {Path(args.path).name}{skipped}",
            *(
                f"  {series.slug}  {series.kind}  {len(series.x)} points"
                for series in result.series
            ),
        ],
        out,
    )
    return 1 if not result.series else 0


def _run_list(args: argparse.Namespace, out: TextIO) -> int:
    """Print the stored series, narrowed by the filters given.

    Args:
        args: Parsed arguments.
        out: Stream to print the table to.

    Returns:
        Process exit code. An empty result is an answer, not a failure.

    Raises:
        HydrofitError: If an entry in the store cannot be read.
    """
    found = SeriesStore(Path(args.store)).list_series(
        product=args.product, kind=args.kind
    )
    if not found:
        _emit(["no series match"], out)
        return 0

    rows = [
        [
            series.slug,
            series.product,
            str(series.kind),
            str(len(series.x)),
            _fmt_range(series.x_range()),
            _fmt_range(series.y_range()),
        ]
        for series in found
    ]
    table = _table(("slug", "product", "kind", "points", "x range", "y range"), rows)
    _emit([*table, f"{len(found)} series"], out)
    return 0


def _run_show(args: argparse.Namespace, out: TextIO) -> int:
    """Print one series in full, optionally with its points.

    Args:
        args: Parsed arguments.
        out: Stream to print to.

    Returns:
        Process exit code.

    Raises:
        HydrofitError: If the slug is unknown or the entry cannot be read.
    """
    series: Series = SeriesStore(Path(args.store)).load(args.slug)
    # Axes are printed through `label`, never through `unit`: the brackets belong to the model,
    # and a path that assembles them here is a path that can one day forget to.
    fields = (
        ("slug", series.slug),
        ("product", series.product),
        ("article no.", series.article_no),
        ("kind", str(series.kind)),
        ("points", str(len(series.x))),
        ("x axis", series.x_axis.label),
        ("y axis", series.y_axis.label),
        ("x range", _fmt_range(series.x_range())),
        ("y range", _fmt_range(series.y_range())),
        ("source file", series.source.file),
        ("source sheet", series.source.sheet),
        ("imported at", series.source.imported_at),
    )
    width = max(len(name) for name, _ in fields)
    lines = [f"{name.ljust(width)}  {value}" for name, value in fields]
    if args.points:
        lines.append("")
        lines.extend(f"  {x!r},{y!r}" for x, y in zip(series.x, series.y, strict=True))
    _emit(lines, out)
    return 0


def _run_fit(args: argparse.Namespace, out: TextIO) -> int:
    """Fit a stored series and print the coefficients with the quality of the fit.

    Args:
        args: Parsed arguments.
        out: Stream to print to.

    Returns:
        Process exit code.

    Raises:
        HydrofitError: If the slug is unknown, or the series cannot carry the degree.
    """
    series: Series = SeriesStore(Path(args.store)).load(args.slug)
    fit = PolynomialFit.fit(series, args.degree)
    metrics = fit.metrics(series)
    fields = [
        ("series", series.slug),
        ("degree", str(fit.degree)),
        *(
            (f"x{power}", repr(value))
            for power, value in zip(
                range(fit.degree, -1, -1), fit.coefficients, strict=True
            )
        ),
        ("r squared", repr(metrics.r_squared)),
        ("max error", repr(metrics.max_abs_error)),
        ("rmse", repr(metrics.rmse)),
    ]
    # Only when it has something to say: a line that appears on every fit is a line that
    # stops being read. Prose is at home here and not in `eval` because the streams have
    # different shapes — see the comment on `_EXTRAPOLATED` — and because these coefficients
    # are exactly the ones that must not be redirected into a file that looks clean.
    if fit.rank < fit.degree + 1:
        fields.append(
            (
                "conditioning",
                f"rank {fit.rank} of the {fit.degree + 1} coefficients "
                f"a degree-{fit.degree} fit needs: the data does not support it",
            )
        )
    width = max(len(name) for name, _ in fields)
    lines = [f"{name.ljust(width)}  {value}" for name, value in fields]
    if args.residuals:
        lines.append("")
        lines.extend(
            f"  {x!r},{residual!r}"
            for x, residual in zip(series.x, fit.residuals(series), strict=True)
        )
    _emit(lines, out)
    return 0


def _run_plot(args: argparse.Namespace, out: TextIO) -> int:
    """Write a figure of one series and the polynomial fitted to it.

    Args:
        args: Parsed arguments.
        out: Stream to print to.

    Returns:
        Process exit code.

    Raises:
        HydrofitError: If the slug is unknown, the series cannot carry the degree, or the
            output path cannot be written.
    """
    series: Series = SeriesStore(Path(args.store)).load(args.slug)
    fit = PolynomialFit.fit(series, args.degree)
    figure = figure_for_fit(series, fit)
    destination = Path(args.output)
    try:
        figure.savefig(destination)
    except (OSError, ValueError) as error:
        # Two families. OSError is the filesystem saying no — a directory that does not exist,
        # a name it refuses, a file already open. ValueError is matplotlib refusing the
        # *format*, which it takes from the extension and rejects before touching the disk:
        # `-o out.dat` raised `Format 'dat' is not supported` straight through main and into
        # the user's face (measured 2026-08-29). Both are things the user can fix by retyping
        # the argument, so both are one line rather than a traceback out of a library never
        # called by name.
        #
        # The guard spans the whole call, drawing included, which is wider than those two
        # causes. A ValueError raised while rendering would be reported as "cannot write",
        # naming the file when the file is innocent. Accepted rather than narrowed: `Series`
        # already refuses non-finite values, so there is no known way to reach it, and
        # catching by inspecting the message text would be worse than the imprecision.
        raise HydrofitError(f"cannot write {destination}: {error}") from error
    _emit([str(destination)], out)
    return 0


def _run_eval(args: argparse.Namespace, out: TextIO) -> int:
    """Evaluate the fitted polynomial at one x.

    Args:
        args: Parsed arguments.
        out: Stream to print to.

    Returns:
        Process exit code. Extrapolation is not an error and does not change it.

    Raises:
        HydrofitError: If the slug is unknown, or the series cannot carry the degree.
    """
    series: Series = SeriesStore(Path(args.store)).load(args.slug)
    fit = PolynomialFit.fit(series, args.degree)
    low, high = series.x_range()
    outside = not low <= args.x <= high
    if outside:
        # Written before the answer so that the two orders agree. stdout is block-buffered into
        # a pipe and line-buffered into a terminal, while stderr is neither; printing the
        # sentence second would put it first for one reader and second for the other, and a
        # documented transcript could then only be true of one of them.
        print(
            f"warning: x={args.x!r} lies outside {series.x_axis.label} "
            f"{_fmt_range((low, high))}; a degree-{fit.degree} polynomial diverges there",
            file=sys.stderr,
        )
    _emit([f"{fit.evaluate(args.x)!r}{_EXTRAPOLATED if outside else ''}"], out)
    return 0


def _parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        The parser for every subcommand.
    """
    parser = argparse.ArgumentParser(
        prog="hydrofit",
        description="Fit polynomials to instrument curves.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    def with_store(sub: argparse.ArgumentParser) -> argparse.ArgumentParser:
        """Add the store option shared by every subcommand.

        Args:
            sub: The subparser to extend.

        Returns:
            The same subparser.
        """
        sub.add_argument(
            "--store",
            default=_DEFAULT_STORE,
            metavar="DIR",
            help=f"directory holding the series (default: {_DEFAULT_STORE})",
        )
        return sub

    importer = with_store(
        subcommands.add_parser(
            "import",
            help="read a spreadsheet",
            description=_IMPORT_DESCRIPTION,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    )
    importer.add_argument("path", help="path to the .xlsx file")
    importer.add_argument(
        "--sheet", metavar="NAME", help="import only this sheet, by its name"
    )
    importer.add_argument(
        "--kind",
        type=DataKind,
        choices=list(DataKind),
        help="force the kind instead of classifying each sheet by its shape",
    )

    listing = with_store(subcommands.add_parser("list", help="list stored series"))
    listing.add_argument(
        "--product", metavar="TEXT", help=f"filter by product: {_PRODUCT_HELP}"
    )
    listing.add_argument("--kind", type=DataKind, choices=list(DataKind))

    show = with_store(subcommands.add_parser("show", help="show one series"))
    show.add_argument("slug", help="identifier from the list output")
    show.add_argument("--points", action="store_true", help="print the points too")

    def with_degree(sub: argparse.ArgumentParser) -> argparse.ArgumentParser:
        """Add the degree option shared by the fitting subcommands.

        Args:
            sub: The subparser to extend.

        Returns:
            The same subparser.
        """
        sub.add_argument(
            "--degree",
            type=int,
            default=DEFAULT_DEGREE,
            metavar="N",
            help=f"degree of the polynomial (default: {DEFAULT_DEGREE})",
        )
        return sub

    fitting = with_degree(
        with_store(subcommands.add_parser("fit", help="fit one series"))
    )
    fitting.add_argument("slug", help="identifier from the list output")
    fitting.add_argument(
        "--residuals", action="store_true", help="print the residual at every point"
    )

    evaluation = with_degree(
        with_store(subcommands.add_parser("eval", help="evaluate one series at an x"))
    )
    evaluation.add_argument("slug", help="identifier from the list output")
    evaluation.add_argument(
        "--x",
        type=float,
        required=True,
        metavar="V",
        help="where to evaluate; an answer from outside the data is marked in the line",
    )

    plotting = with_degree(
        with_store(subcommands.add_parser("plot", help="draw one series and its fit"))
    )
    plotting.add_argument("slug", help="identifier from the list output")
    plotting.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="PATH",
        help="file to write; the format comes from the extension, and the curve is drawn "
        "only across the range of the data",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run hydrofit.

    Args:
        argv: Arguments without the program name. `None` reads them from the command line.

    Returns:
        Process exit code: 0 on success, 1 for a problem the user can fix.
    """
    runners = {
        "import": _run_import,
        "list": _run_list,
        "show": _run_show,
        "fit": _run_fit,
        "eval": _run_eval,
        "plot": _run_plot,
    }
    try:
        # Parsing is inside the guard because `--help` prints from within it. The import help
        # spells the axis labels the way real sheets carry them, superscript and all, so the
        # help screen is one more thing a legacy console can fail to render — and the screen a
        # stuck user reaches for first is the worst possible place for a traceback.
        args = _parser().parse_args(argv)
        return runners[args.command](args, sys.stdout)
    except HydrofitError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except UnicodeEncodeError as error:
        # The catalogue carries units like m³/h, which a legacy console codepage cannot render.
        # That is an environment problem, not a data problem, and it is worth saying so plainly
        # rather than letting an encoder traceback stand in for the explanation.
        print(
            f"error: this console cannot print {error.object[error.start : error.end]!r} "
            f"({error.encoding}); set PYTHONIOENCODING=utf-8 and run again",
            file=sys.stderr,
        )
        return 1
