"""Unit tests for the plotting layer.

Assertions here reach for the *data* an artist carries rather than for the number of artists,
with one deliberate exception: the absence of a legend is a claim about an artist that must not
exist, and there is no data to read. Everything else compares values, because a figure test
written the other way passes for any drawing at all — two lines exist whether they were built
from two arrays or twice from one, and an axis has a label whether or not the label says what
the axis measures. Each test below has been seen red on a broken value: a moved point, a
widened or shortened domain, a label stripped of its unit, a curve drawn from the raw points
instead of the fit.

Reaching for the data is necessary and was not sufficient. Two tests here read real data and
still could not fail: one compared the fit against itself by taking its abscissae from the
artist it was checking, and one bounded `curve_domain` while leaving `figure_for_fit` free to
ignore it: a curve drawn five units past the data passed, and so did a line drawn straight
through the points. Each test therefore names, in its own docstring, which property it holds
and which it leaves to another test or to the eye. That division is the point — a test file
whose prose claims more than its assertions check is worse than one that claims less.
"""

import numpy as np
from matplotlib.colors import to_rgba

from hydrofit.fitting import PolynomialFit
from hydrofit.models import AxisSpec, DataKind, Series, SourceRef
from hydrofit.plotting import curve_domain, figure_for_fit

KV = AxisSpec("Kv", "m³/h")
OPENING = AxisSpec("n", "-")
SOURCE = SourceRef("built in the test", "", "2026-01-01T00:00:00")

# Descending, x^n…x^0, the order the coefficients are stored and consumed in.
CURVE = (0.5, -1.25, 3.0)


def series_on_curve(count: int = 12) -> Series:
    """Build a series lying exactly on CURVE, so the fit is known by construction."""
    x = np.linspace(1.0, 4.0, count)
    y = np.polyval(np.asarray(CURVE), x)
    return Series(
        product="TEST",
        article_no="000",
        x_axis=KV,
        y_axis=OPENING,
        x=tuple(float(value) for value in x),
        y=tuple(float(value) for value in y),
        kind=DataKind.RAW,
        source=SOURCE,
    )


def test_scatter_carries_the_points_of_the_series() -> None:
    """The scatter holds the series' own points, by value and by count."""
    series = series_on_curve()
    figure = figure_for_fit(series, PolynomialFit.fit(series, degree=2))

    # asarray, because the stubs type the return as a union wide enough to include a bare
    # string; the value is an Nx2 array and indexing it needs mypy to know that.
    offsets = np.asarray(figure.axes[0].collections[0].get_offsets())

    assert len(offsets) == len(series.x)
    assert np.allclose(offsets[:, 0], np.asarray(series.x), rtol=0, atol=0)
    assert np.allclose(offsets[:, 1], np.asarray(series.y), rtol=0, atol=0)


def test_line_is_the_fit_over_the_curve_domain() -> None:
    """The line is the fit, sampled at the domain the module defines — both halves asserted.

    Written this way because the obvious form proves nothing. Taking the abscissae from the line
    and evaluating the fit at them compares a function with itself, and a series that lies
    exactly on its own fit lets `plot(series.x, series.y)` pass as well. So the fixture is
    fitted one degree too low, which puts the curve visibly off its points, and the abscissae
    come from `curve_domain` instead of from the artist.

    What that does and does not buy, said plainly: the count and the abscissae are checked
    against the same function `figure_for_fit` calls, so this test pins the two to each other
    and not to the data. A domain of the wrong *extent* is caught by
    `test_the_drawn_curve_stays_within_the_data_on_the_figure`, which takes its bounds from
    `series.x_range()`; a domain of the wrong *density* is caught by nothing here, and by the
    eye instead.
    """
    series = series_on_curve()
    fit = PolynomialFit.fit(series, degree=1)
    figure = figure_for_fit(series, fit)

    drawn = np.asarray(figure.axes[0].lines[0].get_xydata())
    domain = curve_domain(series)

    assert len(drawn) == len(domain)
    assert np.allclose(drawn[:, 0], domain, rtol=0, atol=0)
    assert np.allclose(
        drawn[:, 1], [fit.evaluate(float(x)) for x in domain], rtol=1e-12, atol=1e-12
    )


def test_the_drawn_curve_stays_within_the_data_on_the_figure() -> None:
    """The figure's own line, not just `curve_domain`, ends where the data ends.

    The distinction carries the weight: `curve_domain` was bounded and `figure_for_fit` was
    not, so a line drawn five units past each end passed every test in this file.
    """
    series = series_on_curve()
    low, high = series.x_range()
    figure = figure_for_fit(series, PolynomialFit.fit(series, degree=2))

    drawn = np.asarray(figure.axes[0].lines[0].get_xydata())

    assert drawn[:, 0].min() == low
    assert drawn[:, 0].max() == high


def test_the_fit_is_a_different_colour_from_the_points() -> None:
    """The curve is told apart from the data by colour, not by the reader's patience.

    Compared as normalised RGBA rather than as whatever was passed in: `"r"`, `"red"` and
    `(1, 0, 0, 1)` are the same colour written three ways, and a string comparison would call
    two of them different while calling `"#1f77b4"` against itself equal for the wrong reason.
    """
    series = series_on_curve()
    axes = figure_for_fit(series, PolynomialFit.fit(series, degree=2)).axes[0]

    points = to_rgba(np.asarray(axes.collections[0].get_facecolor())[0])
    line = to_rgba(axes.lines[0].get_color())

    assert points != line


def test_the_fit_is_drawn_above_the_points() -> None:
    """The curve covers the data where they overlap, by `zorder` and not by call order.

    matplotlib resolves overlap by `zorder` and falls back to call order only within one
    value, so a figure that happens to draw the line second is not a figure that keeps it on
    top. The assertion is on the number the renderer actually consults.
    """
    series = series_on_curve()
    axes = figure_for_fit(series, PolynomialFit.fit(series, degree=2)).axes[0]

    assert axes.lines[0].get_zorder() > axes.collections[0].get_zorder()


def test_the_figure_carries_no_legend() -> None:
    """One curve has nothing to tell apart; the legend arrives with the comparison figures."""
    series = series_on_curve()
    axes = figure_for_fit(series, PolynomialFit.fit(series, degree=2)).axes[0]

    assert axes.get_legend() is None


def test_axis_labels_name_the_quantity_and_its_unit() -> None:
    """Labels come out as ``name [unit]``, the form the catalogue uses."""
    series = series_on_curve()
    axes = figure_for_fit(series, PolynomialFit.fit(series, degree=2)).axes[0]

    assert axes.get_xlabel() == "Kv [m³/h]"
    assert axes.get_ylabel() == "n [-]"


def test_curve_spans_exactly_the_range_of_the_data() -> None:
    """The domain ends where the data ends — neither short of it nor past it.

    One test, not two: equality implies the inequality on the same data, so a pair asserting
    `>= low, <= high` beside `== low, == high` has a member that can never be red while the
    other is green, and a test that cannot fail alone is not a test.
    """
    series = series_on_curve()
    low, high = series.x_range()

    drawn = curve_domain(series)

    assert drawn.min() == low
    assert drawn.max() == high
