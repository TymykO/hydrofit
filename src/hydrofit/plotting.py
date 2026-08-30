"""Matplotlib figures: a series drawn against the polynomial fitted to it.

Figures are built as bare `Figure` objects, never through `pyplot`. That is what keeps this
module free of global state: `pyplot` is what holds the registry of open windows and what
selects an interactive backend, and nothing here imports it — measured, not assumed. So no
backend is pinned: the tests pass identically whether the machine resolves one interactive or
headless, and `savefig` picks its writer from the file format rather than from the display.

Nothing in this module writes a file. Building the figure and saving it are separate so that a
test can assert on what was drawn rather than against a *stored* image — bytes this project has
already watched change under a runner with a different processor while the code stood still. Two
images produced by one run on one machine may still be compared with each other, and are: that
comparison says the drawings differ, which is a claim about this run and not about the future.
"""

import math
from collections.abc import Sequence

import numpy as np
from matplotlib.figure import Figure

from hydrofit.errors import HydrofitError
from hydrofit.fitting import PolynomialFit
from hydrofit.models import Series

# Enough to look continuous at any figure size a report uses, and small enough that the cost of
# drawing never enters the conversation. It is not a claim about accuracy: the curve is exact at
# every one of these abscissae, and straight between them.
_CURVE_POINTS = 200

# The palette lives here, named, and never as a literal at a call site. Comparison figures add a
# second curve, which needs a colour that collides with neither of these; a palette spread
# across the places that draw drifts apart at the first change to any one of them.
_POINTS_COLOUR = "#1f77b4"
_FIT_COLOUR = "#d62728"

# A comparison figure carries four artists at most — two sets of points and two curves — and
# each needs to be told from the other three. These two extend the table above rather than
# starting a second one somewhere else, which is the whole reason the table exists.
_COMPARISON_POINTS_COLOUR = "#9467bd"
_COMPARISON_COLOUR = "#2ca02c"

# Colour alone does not separate two curves. It survives neither a monochrome print nor a reader
# who cannot tell red from blue, so the second curve is told apart by its dash as well: three
# properties in one place stay consistent, two here and one somewhere else do not.
_FIT_LINESTYLE = "-"
_COMPARISON_LINESTYLE = "--"

# Wide enough to read where it crosses the scatter. Deliberately untested: an assertion on this
# number would pin the constant to itself and could turn red only by editing the line that sets
# it, which is a test that cannot fail for any reason worth catching. Width is a property for an
# eye, and looking at the saved figure is already a closing criterion of this work.
_FIT_LINEWIDTH = 2.5

# Explicit, because "drawn later" is not a guarantee: zorder decides what covers what, and it
# overrides call order. Relying on the order of the calls is relying on something the code does
# not say. The fit belongs on top — it is the claim, and the points underneath are the evidence
# it has to be read against.
_POINTS_ZORDER = 2
_FIT_ZORDER = 3
_COMPARISON_ZORDER = 4


def curve_domain(series: Series) -> np.ndarray:
    """Abscissae the fitted curve is drawn over.

    The domain stops where the data stops. A degree-6 polynomial does not merely lose accuracy
    beyond its points, it diverges, and `eval` warns about exactly that in words. A picture has
    no line to put a warning on, so the drawing ends where the evidence ends instead.

    Args:
        series: The series whose x-range bounds the curve.

    Returns:
        Evenly spaced abscissae from the lowest x of the series to the highest.
    """
    low, high = series.x_range()
    return np.linspace(low, high, _CURVE_POINTS)


def figure_for_fit(series: Series, fit: PolynomialFit) -> Figure:
    """Draw one series and the polynomial fitted to it.

    Args:
        series: The stored points.
        fit: The polynomial to draw through them.

    Returns:
        A figure carrying the points as a scatter and the fit as a red line above them, over
        the range of the data, with both axes labelled as the catalogue spells them, unit in
        square brackets. No legend: with one curve there is nothing to tell apart, and the
        legend that names each curve's metrics arrives with the comparison figures.
    """
    figure = Figure()
    axes = figure.subplots()

    axes.scatter(series.x, series.y, color=_POINTS_COLOUR, zorder=_POINTS_ZORDER)
    x = curve_domain(series)
    axes.plot(
        x,
        [fit.evaluate(float(value)) for value in x],
        color=_FIT_COLOUR,
        linestyle=_FIT_LINESTYLE,
        linewidth=_FIT_LINEWIDTH,
        zorder=_FIT_ZORDER,
    )

    # Taken from the axis rather than formatted here. The convention "name [unit]" already has
    # one home in models.py, and a second copy of it drifts at the first change to either.
    axes.set_xlabel(series.x_axis.label)
    axes.set_ylabel(series.y_axis.label)
    return figure


def legend_label(series: Series, fit: PolynomialFit) -> str:
    """Name one curve in the legend, with the quality of its fit.

    R² is left out whenever it is not a finite number. `nan` is what a flat series produces —
    R² measures the share of variation a fit accounts for, and there is none to account for —
    and a legend reading `R2=nan` looks like a measurement that came back strange rather than
    one that was never possible. The test is `isfinite` rather than `isnan` as care rather than
    as measurement: no series in this package's tests produces an infinite R², so that half of
    the guard is defensive and unproven. Saying so is cheaper than implying a fixture that does
    not exist.

    Only ASCII is added here. The superscript in R² would be decoration, and the only non-ASCII
    characters in this package's output are the ones the catalogue itself carries, such as the
    unit `m³/h` in an axis label.

    Args:
        series: The series the curve was fitted to.
        fit: The fitted polynomial.

    Returns:
        A single line naming the series, the degree, and the metrics that could be computed.
    """
    metrics = fit.metrics(series)
    parts = [f"{series.product}, degree {fit.degree}"]
    if math.isfinite(metrics.r_squared):
        parts.append(f"R2={metrics.r_squared:.4f}")
    parts.append(f"max error={metrics.max_abs_error:.3g}")
    return "  ".join(parts)


def _refuse_undrawable(pairs: Sequence[tuple[Series, PolynomialFit]]) -> None:
    """Stop before drawing a comparison that would mislead rather than compare.

    Three refusals, one place. **Exactly two pairs**, because exactly two are given distinct
    colours, dashes and stacking: a third would be drawn identically to the second and be
    indistinguishable on the figure, which is worse than being absent. **The same axes**,
    because two units on one axis is a figure that lies, and a picture outlives the session
    that made it — the comparison is on the `AxisSpec` itself and never on the rendered label,
    since a check on a derived value quietly changes meaning when the derivation does. **Not the same
    request twice**, because one series at one degree asked for twice produces two identical
    legend entries and a curve hidden exactly beneath itself.

    That last refusal is about the request and not about the drawing, and the difference is
    worth stating: two *different* requests can still produce curves that coincide, and a
    parabola fitted at degree 2 and at degree 4 does exactly that, to within 1e-13. Such a
    figure is permitted, because the coincidence is the answer — degree 4 buys nothing here —
    and refusing it would hide the very finding the comparison was asked for.

    The refusals live here rather than at the command because it is the drawing that would
    mislead, not the request.

    Args:
        pairs: The series and fits about to be drawn together.

    Raises:
        HydrofitError: If there are not exactly two pairs, if the series measure different
            quantities, or if one series at one degree was asked for twice.
    """
    if len(pairs) != 2:
        raise HydrofitError(
            f"a comparison figure draws exactly two curves, not {len(pairs)}"
        )

    (first, first_fit), (second, second_fit) = pairs
    for axis, ours, theirs in (
        ("x", first.x_axis, second.x_axis),
        ("y", first.y_axis, second.y_axis),
    ):
        if ours != theirs:
            raise HydrofitError(
                f"{first.product} and {second.product} cannot share a figure: "
                f"their {axis} axes are {ours.label} and {theirs.label}"
            )

    if first.slug == second.slug and first_fit.degree == second_fit.degree:
        raise HydrofitError(
            f"{first.product} at degree {first_fit.degree} compared with itself "
            "is one request twice, not a comparison"
        )


def figure_comparing(pairs: Sequence[tuple[Series, PolynomialFit]]) -> Figure:
    """Draw two fits on one figure, with the quality of each named in the legend.

    Exactly two pairs, and the function does not distinguish the two shapes that reach it: two
    degrees over one series, and two series each with its own fit. The difference is entirely
    in what the caller passes, and a series appearing twice contributes one scatter — its
    points do not become denser because two curves were asked of them.

    Args:
        pairs: The series and the fit drawn for each, in the order they are drawn.

    Returns:
        A figure carrying one scatter per distinct series, one line per pair, and a legend with
        one entry per line. Each line is drawn over the range of its own series' data.

    Raises:
        HydrofitError: If the pairs are not exactly two, do not share both axes, or repeat one
            series at one degree.
    """
    _refuse_undrawable(pairs)

    figure = Figure()
    axes = figure.subplots()

    drawn_series: set[str] = set()
    for index, (series, fit) in enumerate(pairs):
        first = index == 0
        if series.slug not in drawn_series:
            drawn_series.add(series.slug)
            axes.scatter(
                series.x,
                series.y,
                color=_POINTS_COLOUR if first else _COMPARISON_POINTS_COLOUR,
                zorder=_POINTS_ZORDER,
            )
        x = curve_domain(series)
        axes.plot(
            x,
            [fit.evaluate(float(value)) for value in x],
            color=_FIT_COLOUR if first else _COMPARISON_COLOUR,
            linestyle=_FIT_LINESTYLE if first else _COMPARISON_LINESTYLE,
            linewidth=_FIT_LINEWIDTH,
            zorder=_FIT_ZORDER if first else _COMPARISON_ZORDER,
            label=legend_label(series, fit),
        )

    first_series = pairs[0][0]
    axes.set_xlabel(first_series.x_axis.label)
    axes.set_ylabel(first_series.y_axis.label)
    axes.legend()
    return figure
