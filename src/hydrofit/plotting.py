"""Matplotlib figures: a series drawn against the polynomial fitted to it.

Figures are built as bare `Figure` objects, never through `pyplot`. That is what keeps this
module free of global state: `pyplot` is what holds the registry of open windows and what
selects an interactive backend, and nothing here imports it — measured, not assumed. So no
backend is pinned: the tests pass identically whether the machine resolves one interactive or
headless, and `savefig` picks its writer from the file format rather than from the display.

Nothing in this module writes a file. Building the figure and saving it are separate so that a
test can assert on what was drawn rather than on the bytes of a PNG — bytes this project has
already watched change under a runner with a different processor while the code stood still.
"""

import numpy as np
from matplotlib.figure import Figure

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

# Colour alone does not separate two curves. It survives neither a monochrome print nor a reader
# who cannot tell red from blue, so the second curve is told apart by its dash as well. The style
# sits in this table from the start even though only the solid one is drawn today: three
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
