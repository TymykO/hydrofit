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
import pytest
from matplotlib.colors import to_rgba

from hydrofit.errors import HydrofitError
from hydrofit.fitting import PolynomialFit
from hydrofit.models import AxisSpec, DataKind, Series, SourceRef
from hydrofit.plotting import (
    curve_domain,
    figure_comparing,
    figure_for_fit,
    legend_label,
)

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


def flat_series() -> Series:
    """Build a series whose y never varies, so `FitMetrics.r_squared` is `nan`.

    R² measures the share of variation a fit accounts for, and there is no variation here to
    account for. The value is `nan` by construction rather than by accident, which is what
    makes this a fixture and not a curiosity.
    """
    x = np.linspace(1.0, 4.0, 12)
    return Series(
        product="FLAT",
        article_no="000",
        x_axis=KV,
        y_axis=OPENING,
        x=tuple(float(value) for value in x),
        y=tuple(2.0 for _ in x),
        kind=DataKind.RAW,
        source=SOURCE,
    )


def other_series() -> Series:
    """A second series on the same axes, so it may legitimately share a figure."""
    x = np.linspace(1.0, 4.0, 12)
    y = np.polyval(np.asarray((0.2, -0.6, 5.0)), x)
    return Series(
        product="OTHER",
        article_no="001",
        x_axis=KV,
        y_axis=OPENING,
        x=tuple(float(value) for value in x),
        y=tuple(float(value) for value in y),
        kind=DataKind.RAW,
        source=SOURCE,
    )


def test_two_degrees_of_one_series_draw_two_different_curves() -> None:
    """The curves carry different ordinates, which is the only thing that makes them two."""
    series = series_on_curve()
    axes = figure_comparing(
        [
            (series, PolynomialFit.fit(series, degree=1)),
            (series, PolynomialFit.fit(series, degree=2)),
        ]
    ).axes[0]

    first = np.asarray(axes.lines[0].get_xydata())
    second = np.asarray(axes.lines[1].get_xydata())

    assert not np.allclose(first[:, 1], second[:, 1], rtol=1e-6, atol=1e-6)


def test_one_series_compared_with_itself_is_scattered_once() -> None:
    """Asking two degrees of one series does not double its points.

    Drawing the scatter per pair would put every point on the figure twice, which changes
    nothing a reader can see and everything a reader would conclude about the data.
    """
    series = series_on_curve()
    axes = figure_comparing(
        [
            (series, PolynomialFit.fit(series, degree=1)),
            (series, PolynomialFit.fit(series, degree=2)),
        ]
    ).axes[0]

    assert len(axes.collections) == 1
    offsets = np.asarray(axes.collections[0].get_offsets())
    assert np.allclose(offsets[:, 1], np.asarray(series.y), rtol=0, atol=0)


def test_two_series_each_bring_their_own_points() -> None:
    """An overlay scatters both series, and each scatter holds its own data — both coordinates.

    The second series spans a wider x range than the first on purpose. Comparing ordinates
    alone leaves the abscissae free, and with two fixtures sharing an x range even an abscissa
    check proves nothing: a scatter given the first series' x values would be indistinguishable
    from a correct one.
    """
    first_series = series_on_curve()
    second_series = wider_series()
    axes = figure_comparing(
        [
            (first_series, PolynomialFit.fit(first_series, degree=2)),
            (second_series, PolynomialFit.fit(second_series, degree=1)),
        ]
    ).axes[0]

    assert len(axes.collections) == 2
    for collection, series in zip(
        axes.collections, (first_series, second_series), strict=True
    ):
        offsets = np.asarray(collection.get_offsets())
        assert np.allclose(offsets[:, 0], np.asarray(series.x), rtol=0, atol=0)
        assert np.allclose(offsets[:, 1], np.asarray(series.y), rtol=0, atol=0)


def test_every_legend_entry_carries_the_metric_of_its_own_curve() -> None:
    """Each entry names its curve's own max error, not the other's.

    Two entries that both quote the first curve's numbers would satisfy a test that only
    counted them, and would misreport the comparison the figure exists to make.
    """
    series = series_on_curve()
    low = PolynomialFit.fit(series, degree=1)
    high = PolynomialFit.fit(series, degree=2)
    axes = figure_comparing([(series, low), (series, high)]).axes[0]

    legend = axes.get_legend()

    # Narrowed rather than ignored: a comparison figure without a legend is a figure whose two
    # curves cannot be told apart, so the absence is worth an assertion of its own.
    assert legend is not None
    texts = [entry.get_text() for entry in legend.get_texts()]

    assert len(texts) == 2
    assert f"{low.metrics(series).max_abs_error:.3g}" in texts[0]
    assert f"{high.metrics(series).max_abs_error:.3g}" in texts[1]
    assert texts[0] != texts[1]


def test_a_flat_series_gets_a_legend_without_r_squared() -> None:
    """`nan` is left out rather than printed: an absent term does not invite interpretation."""
    series = flat_series()

    label = legend_label(series, PolynomialFit.fit(series, degree=2))

    assert "nan" not in label
    assert "R2" not in label
    assert "max error" in label


def test_a_curved_series_gets_a_legend_with_r_squared() -> None:
    """The control for the test above: R² is present whenever it can be computed."""
    series = series_on_curve()

    label = legend_label(series, PolynomialFit.fit(series, degree=2))

    assert "R2=" in label


def series_on_other_axes() -> Series:
    """A series measuring different quantities, which may not share a figure with the rest."""
    x = np.linspace(1.0, 4.0, 12)
    return Series(
        product="VESSEL",
        article_no="002",
        x_axis=AxisSpec("q", "m³/h"),
        y_axis=AxisSpec("Δp", "kPa"),
        x=tuple(float(value) for value in x),
        y=tuple(float(value) ** 2 for value in x),
        kind=DataKind.RAW,
        source=SOURCE,
    )


def test_series_on_different_axes_are_refused() -> None:
    """Two units on one axis is a figure that lies, so it is never drawn.

    The message names both labels: a reader who is told only that something disagreed has to
    go and find out what, which is the part they came here for.
    """
    first_series = series_on_curve()
    stranger = series_on_other_axes()

    with pytest.raises(HydrofitError) as refusal:
        figure_comparing(
            [
                (first_series, PolynomialFit.fit(first_series, degree=2)),
                (stranger, PolynomialFit.fit(stranger, degree=2)),
            ]
        )

    message = str(refusal.value)
    assert "Kv [m³/h]" in message
    assert "q [m³/h]" in message


def test_two_overlaid_series_draw_two_different_curves() -> None:
    """Two series on shared axes are permitted, and their curves carry different ordinates.

    Doubles as the control for the refusal: it must not fire on the case it exists to permit.
    Asserting only that two lines exist would pass for a figure that drew one series twice,
    which is the shape a comparison figure exists to make visible.
    """
    first_series = series_on_curve()
    second_series = other_series()

    axes = figure_comparing(
        [
            (first_series, PolynomialFit.fit(first_series, degree=2)),
            (second_series, PolynomialFit.fit(second_series, degree=2)),
        ]
    ).axes[0]

    first = np.asarray(axes.lines[0].get_xydata())
    second = np.asarray(axes.lines[1].get_xydata())

    assert not np.allclose(first[:, 1], second[:, 1], rtol=1e-6, atol=1e-6)


def series_on_a_different_y_axis() -> Series:
    """Same x axis as the rest, different y axis — the case the x check cannot see.

    Every other mismatched fixture here differs on x, and the guard tests x first, so an
    implementation that had lost its y comparison entirely would pass on all of them.
    """
    x = np.linspace(1.0, 4.0, 12)
    return Series(
        product="OTHER-Y",
        article_no="003",
        x_axis=KV,
        y_axis=AxisSpec("Δp", "kPa"),
        x=tuple(float(value) for value in x),
        y=tuple(float(value) * 2.0 for value in x),
        kind=DataKind.RAW,
        source=SOURCE,
    )


def test_series_differing_only_on_the_y_axis_are_refused() -> None:
    """The y comparison is reached and used, not merely present in the source."""
    first_series = series_on_curve()
    stranger = series_on_a_different_y_axis()

    with pytest.raises(HydrofitError) as refusal:
        figure_comparing(
            [
                (first_series, PolynomialFit.fit(first_series, degree=2)),
                (stranger, PolynomialFit.fit(stranger, degree=2)),
            ]
        )

    message = str(refusal.value)
    assert "y axes" in message
    assert "n [-]" in message
    assert "Δp [kPa]" in message


def test_comparing_a_series_with_itself_at_one_degree_is_refused() -> None:
    """Two identical curves and two identical legend entries read as a comparison and are not."""
    series = series_on_curve()
    fit = PolynomialFit.fit(series, degree=2)

    with pytest.raises(HydrofitError) as refusal:
        figure_comparing([(series, fit), (series, PolynomialFit.fit(series, degree=2))])

    assert "compared with itself" in str(refusal.value)


def test_a_comparison_needs_exactly_two_curves() -> None:
    """Fewer or more than two is refused rather than drawn: only two are styled apart."""
    series = series_on_curve()
    fit = PolynomialFit.fit(series, degree=2)

    for pairs in ([], [(series, fit)], [(series, fit)] * 3):
        with pytest.raises(HydrofitError) as refusal:
            figure_comparing(pairs)
        assert "exactly two curves" in str(refusal.value)


def test_the_comparison_figure_labels_its_axes() -> None:
    """The axes say what they measure here too, in the same `name [unit]` form."""
    series = series_on_curve()
    axes = figure_comparing(
        [
            (series, PolynomialFit.fit(series, degree=1)),
            (series, PolynomialFit.fit(series, degree=2)),
        ]
    ).axes[0]

    assert axes.get_xlabel() == "Kv [m³/h]"
    assert axes.get_ylabel() == "n [-]"


def test_a_flat_series_reaches_the_figure_without_r_squared() -> None:
    """The omission survives the trip into the legend, not only the label helper.

    Testing `legend_label` alone leaves the one line that carries it into the figure unproven,
    and a figure built with some other label would pass that test untouched.
    """
    flat = flat_series()
    axes = figure_comparing(
        [
            (flat, PolynomialFit.fit(flat, degree=1)),
            (flat, PolynomialFit.fit(flat, degree=2)),
        ]
    ).axes[0]

    legend = axes.get_legend()
    assert legend is not None
    texts = [entry.get_text() for entry in legend.get_texts()]

    assert texts and all("nan" not in text and "R2" not in text for text in texts)


def wider_series() -> Series:
    """Same axes, a strictly wider x range — so a domain taken from the wrong series shows.

    Every other fixture here spans 1 to 4. With all of them identical, a comparison figure
    that drew both curves over the *first* series' domain would be indistinguishable from one
    that gave each curve its own.
    """
    x = np.linspace(1.0, 9.0, 12)
    return Series(
        product="WIDE",
        article_no="004",
        x_axis=KV,
        y_axis=OPENING,
        x=tuple(float(value) for value in x),
        y=tuple(float(value) * 0.5 for value in x),
        kind=DataKind.RAW,
        source=SOURCE,
    )


def bumpy_series() -> Series:
    """A shape no low-degree polynomial reproduces, so two degrees genuinely disagree.

    A series lying exactly on a parabola is fitted identically by degree 2 and degree 4 — to
    within 1e-13 — so it cannot tell a figure that used the second degree from one that
    ignored it. This one can.
    """
    x = np.linspace(1.0, 4.0, 24)
    y = np.sin(3.0 * x) + 0.5 * x
    return Series(
        product="BUMPY",
        article_no="005",
        x_axis=KV,
        y_axis=OPENING,
        x=tuple(float(value) for value in x),
        y=tuple(float(value) for value in y),
        kind=DataKind.RAW,
        source=SOURCE,
    )


def test_each_curve_is_its_own_fit_over_its_own_domain() -> None:
    """The second line carries the second fit, evaluated on the second series' range.

    Asserting only that the two curves differ leaves the second one unbound: a drawing that
    added a constant to it, or that spread it over the first series' domain, would still
    differ from the first and pass.
    """
    narrow = series_on_curve()
    wide = wider_series()
    narrow_fit = PolynomialFit.fit(narrow, degree=2)
    wide_fit = PolynomialFit.fit(wide, degree=1)

    axes = figure_comparing([(narrow, narrow_fit), (wide, wide_fit)]).axes[0]

    for line, series, fit in (
        (axes.lines[0], narrow, narrow_fit),
        (axes.lines[1], wide, wide_fit),
    ):
        drawn = np.asarray(line.get_xydata())
        domain = curve_domain(series)
        assert np.allclose(drawn[:, 0], domain, rtol=0, atol=0)
        assert np.allclose(
            drawn[:, 1],
            [fit.evaluate(float(value)) for value in domain],
            rtol=1e-12,
            atol=1e-12,
        )


def test_two_degrees_disagree_on_data_no_low_degree_reproduces() -> None:
    """On a shape a parabola cannot follow, degree 2 and degree 4 draw visibly apart.

    The separation is asserted against the spread of the data rather than against zero: two
    curves differing by 1e-13 satisfy `not allclose` and are one curve to any reader.
    """
    series = bumpy_series()
    axes = figure_comparing(
        [
            (series, PolynomialFit.fit(series, degree=2)),
            (series, PolynomialFit.fit(series, degree=4)),
        ]
    ).axes[0]

    low, high = series.y_range()
    first = np.asarray(axes.lines[0].get_ydata())
    second = np.asarray(axes.lines[1].get_ydata())

    assert np.max(np.abs(first - second)) > 0.05 * (high - low)


def test_the_second_curve_is_told_apart_from_the_first() -> None:
    """Colour, dash and stacking all differ, so neither curve hides inside the other."""
    series = bumpy_series()
    axes = figure_comparing(
        [
            (series, PolynomialFit.fit(series, degree=2)),
            (series, PolynomialFit.fit(series, degree=4)),
        ]
    ).axes[0]

    first, second = axes.lines[0], axes.lines[1]

    assert to_rgba(first.get_color()) != to_rgba(second.get_color())
    assert first.get_linestyle() != second.get_linestyle()
    assert first.get_zorder() != second.get_zorder()


def test_overlaid_series_keep_their_points_apart() -> None:
    """Two scatters, two colours: the points of one series are never read as the other's."""
    first_series = series_on_curve()
    second_series = other_series()
    axes = figure_comparing(
        [
            (first_series, PolynomialFit.fit(first_series, degree=2)),
            (second_series, PolynomialFit.fit(second_series, degree=2)),
        ]
    ).axes[0]

    first = to_rgba(np.asarray(axes.collections[0].get_facecolor())[0])
    second = to_rgba(np.asarray(axes.collections[1].get_facecolor())[0])

    assert first != second


def test_the_scatter_carries_abscissae_as_well_as_ordinates() -> None:
    """Both coordinates, because a scatter plotted against an index passes an ordinate check."""
    series = series_on_curve()
    axes = figure_comparing(
        [
            (series, PolynomialFit.fit(series, degree=1)),
            (series, PolynomialFit.fit(series, degree=2)),
        ]
    ).axes[0]

    offsets = np.asarray(axes.collections[0].get_offsets())

    assert np.allclose(offsets[:, 0], np.asarray(series.x), rtol=0, atol=0)
    assert np.allclose(offsets[:, 1], np.asarray(series.y), rtol=0, atol=0)
