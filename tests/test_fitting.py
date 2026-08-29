"""Unit tests for the fitting layer.

Most expected values here come from arithmetic rather than from a second run of the same
code: a polynomial whose coefficients are known by construction, or a case small enough to work
out by hand. Two exceptions are deliberate and worth naming. `evaluate` is compared against
`numpy.polyval`, which is what it calls — what that checks is that the stored coefficients are
the fitted ones and are used as a polynomial, not that polyval is correct. And the
ill-conditioned case is built from points chosen for the conditioning of their Vandermonde
matrix, not to lie on any curve. The fits against the legacy numbers live elsewhere; these
tests are about the layer itself.
"""

import math

import numpy as np
import pytest

from hydrofit.errors import HydrofitError
from hydrofit.fitting import DEFAULT_DEGREE, PolynomialFit
from hydrofit.models import AxisSpec, DataKind, Series, SourceRef

KV = AxisSpec("Kv", "m³/h")
OPENING = AxisSpec("n", "-")
SOURCE = SourceRef("built in the test", "", "2026-01-01T00:00:00")

# Coefficients descending, x^n…x^0, so the tuple reads the way the spreadsheet formula does.
CURVES: dict[int, tuple[float, ...]] = {
    2: (0.5, -1.25, 3.0),
    5: (0.1, -0.4, 1.2, -2.0, 0.75, 4.0),
    6: (-0.02, 0.3, -1.1, 2.4, -3.3, 1.7, 0.6),
}


def series_from(coefficients: tuple[float, ...], count: int = 40) -> Series:
    """Build a series lying exactly on the polynomial with these coefficients."""
    x = np.linspace(1.0, 4.0, count)
    y = np.polyval(np.asarray(coefficients), x)
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


@pytest.mark.parametrize("degree", sorted(CURVES))
def test_an_exact_polynomial_is_recovered(degree: int) -> None:
    """Fitting points that lie on a polynomial returns that polynomial."""
    expected = CURVES[degree]
    fit = PolynomialFit.fit(series_from(expected), degree)
    assert fit.degree == degree
    # atol=0 on purpose: allclose defaults it to 1e-8, which for coefficients of this size
    # would decide every comparison and make the stated rtol decorative. Margin measured on the
    # worst coefficient of each degree: 5.5e-15 at degree 2, 1.8e-12 at 5, 5.7e-12 at 6 — some
    # 170x inside the tolerance where it is tightest, which is degree 6.
    assert np.allclose(fit.coefficients, expected, rtol=1e-9, atol=0)


@pytest.mark.parametrize("degree", sorted(CURVES))
def test_an_exact_fit_reports_a_perfect_score(degree: int) -> None:
    """On points with no scatter the metrics have nothing left to report."""
    series = series_from(CURVES[degree])
    metrics = PolynomialFit.fit(series, degree).metrics(series)
    # Exactly 1.0, not approximately. Measured at all three degrees, the ratio of the
    # residual sum to the deviation sum is ~1e-29 — the residual sums themselves run 1e-27 to
    # 1.8e-25 against deviation sums of 54 to 8.3e3 — so subtracting it from 1.0 lands on 1.0.
    assert metrics.r_squared == 1.0
    # 1e-12, not 1e-9: the worst measured across the three degrees is 1.28e-13, and a bound
    # three orders above what the code delivers stops being a measurement of anything.
    assert metrics.max_abs_error == pytest.approx(0.0, abs=1e-12)
    assert metrics.rmse == pytest.approx(0.0, abs=1e-12)


def test_the_default_degree_is_six() -> None:
    """The degree the legacy tool uses for valves is the one taken without asking."""
    assert PolynomialFit.fit(series_from(CURVES[6])).degree == DEFAULT_DEGREE == 6


def test_scatter_lowers_every_metric_it_should() -> None:
    """A displaced point shows up in all three numbers, and in the residual that caused it.

    The residual carries the sign the docstring of `residuals` promises, `fit(x) - y`, and
    that signed number is what a caller prints. Two other tests hold the same line — the one
    worked out by hand and the one about ordering — and reversing the sign deliberately fails
    all three.
    """
    coefficients = CURVES[2]
    series = series_from(coefficients)
    moved = list(series.y)
    moved[10] += 0.5
    scattered = Series(
        product=series.product,
        article_no=series.article_no,
        x_axis=series.x_axis,
        y_axis=series.y_axis,
        x=series.x,
        y=tuple(moved),
        kind=series.kind,
        source=series.source,
    )
    fit = PolynomialFit.fit(scattered, 2)
    metrics = fit.metrics(scattered)
    assert metrics.r_squared < 1.0
    assert metrics.max_abs_error > 0.1
    # No comparison of rmse against max_abs_error: rms <= max holds for every residual vector,
    # so it would pass whatever this code computed. The arithmetic of rmse is pinned by the
    # hand-worked case below.
    # The point was moved up, so the curve passes below it and the residual is negative.
    assert fit.residuals(scattered)[10] < -0.4


def test_evaluate_agrees_with_the_coefficients() -> None:
    """`evaluate` is the polynomial, not an interpolation between stored points."""
    coefficients = CURVES[5]
    fit = PolynomialFit.fit(series_from(coefficients), 5)
    assert fit.evaluate(2.5) == pytest.approx(
        float(np.polyval(np.asarray(coefficients), 2.5)), rel=1e-9
    )


def test_evaluate_extrapolates_without_complaint() -> None:
    """Outside the data the fit still answers, with the polynomial rather than an edge value.

    Asserted against the value itself: a fit that clamped x into the range of its data would
    return something finite too, and finiteness alone would call that correct.
    """
    # 0.5*400^2 - 1.25*400 + 3 = 79503, worked out rather than taken from the call under test.
    fit = PolynomialFit.fit(series_from(CURVES[2]), 2)
    assert fit.evaluate(400.0) == pytest.approx(79503.0, rel=1e-9)


def test_residuals_keep_the_order_of_the_series() -> None:
    """One residual per point, positioned as the points are.

    Two points are displaced by different amounts at known indices, because on a series lying
    exactly on its curve every residual is ~1e-14 and a reversal — or any permutation — would
    pass unnoticed. Displaced, a reordering moves the large values away from the indices that
    caused them.
    """
    base = series_from(CURVES[2])
    moved = list(base.y)
    moved[5] += 0.5
    moved[20] -= 0.9
    scattered = Series(
        product=base.product,
        article_no=base.article_no,
        x_axis=base.x_axis,
        y_axis=base.y_axis,
        x=base.x,
        y=tuple(moved),
        kind=base.kind,
        source=base.source,
    )
    residuals = PolynomialFit.fit(scattered, 2).residuals(scattered)
    assert len(residuals) == len(scattered.x)
    assert residuals[5] < -0.4
    assert residuals[20] > 0.8
    elsewhere = [value for index, value in enumerate(residuals) if index not in (5, 20)]
    assert max(abs(value) for value in elsewhere) < 0.1


def test_a_flat_series_has_no_r_squared() -> None:
    """R² measures against the spread of y; with no spread there is nothing to measure.

    `nan` rather than 1.0: a fit through a horizontal line explains none of the variation,
    because there is no variation to explain, and reporting a perfect score would say the
    opposite of what happened.
    """
    flat = Series(
        product="TEST",
        article_no="000",
        x_axis=KV,
        y_axis=OPENING,
        x=(1.0, 2.0, 3.0, 4.0),
        y=(7.0, 7.0, 7.0, 7.0),
        kind=DataKind.RAW,
        source=SOURCE,
    )
    metrics = PolynomialFit.fit(flat, 2).metrics(flat)
    assert math.isnan(metrics.r_squared)
    assert metrics.max_abs_error == pytest.approx(0.0, abs=1e-9)


def series_of(count: int) -> Series:
    """Build a series of exactly this many points, on a curve of no particular interest."""
    x = np.linspace(1.0, 2.0, count)
    return Series(
        product="SHORT",
        article_no="000",
        x_axis=KV,
        y_axis=OPENING,
        x=tuple(float(value) for value in x),
        y=tuple(float(value) for value in x**2),
        kind=DataKind.RAW,
        source=SOURCE,
    )


def test_a_series_shorter_than_the_degree_is_refused() -> None:
    """`degree` points cannot carry a degree-`degree` fit; `degree + 1` can.

    The boundary is asserted from both sides, because an off-by-one here would surface as a
    silently over-fitted curve rather than as an error.
    """
    with pytest.raises(HydrofitError) as refusal:
        PolynomialFit.fit(series_of(6), 6)
    assert "7 points" in str(refusal.value)
    assert "has 6" in str(refusal.value)
    assert len(PolynomialFit.fit(series_of(7), 6).coefficients) == 7


def test_the_refusal_names_the_series() -> None:
    """The message says which curve was too short, not merely that one was."""
    with pytest.raises(HydrofitError, match="SHORT"):
        PolynomialFit.fit(series_of(3), 6)


def test_a_supported_fit_reports_full_rank() -> None:
    """Data that carries the degree asked of it gives rank `degree + 1`."""
    fit = PolynomialFit.fit(series_from(CURVES[6]), 6)
    assert fit.rank == 7


def test_an_ill_conditioned_fit_reports_its_rank() -> None:
    """Points packed into a span too narrow to support degree 6 come back rank-deficient.

    The points themselves are ordinary floats, and not remarkably close ones: 1e-7 apart is
    some 4.5e8 ulps, with room for many more points between any two of them. The Vandermonde
    matrix over so narrow an interval is not singular either — its determinant is around
    2.5e-140 — but that is indistinguishable from singular at the cutoff a solver works to, and
    the rank is where numpy says so.
    The fit passes no judgement on it: no threshold of ours and no rescaling of the points,
    because the curves this package has to reproduce were fitted without either.
    """
    crowded = Series(
        product="CROWDED",
        article_no="000",
        x_axis=KV,
        y_axis=OPENING,
        x=tuple(1.0 + index * 1e-7 for index in range(7)),
        y=(0.1, 0.2, 0.15, 0.3, 0.25, 0.4, 0.35),
        kind=DataKind.RAW,
        source=SOURCE,
    )
    fit = PolynomialFit.fit(crowded, 6)
    assert fit.rank < fit.degree + 1
    assert len(fit.coefficients) == 7


def test_the_metrics_match_a_case_worked_out_by_hand() -> None:
    """Two points, a constant fit, and every number known before the code runs.

    The best degree-0 fit through 0 and 2 is their mean, so the residuals are exactly +1 and
    -1. That pins what no other test here can: `rmse` divides by the number of points, not by
    a degrees-of-freedom correction — the classic "unbiased" edit would give 1.414 and pass
    every other assertion in this file. R² is exactly 0: a constant explains none of the
    variation, and the residual sum equals the deviation sum.
    """
    two_points = Series(
        product="HAND",
        article_no="000",
        x_axis=KV,
        y_axis=OPENING,
        x=(1.0, 2.0),
        y=(0.0, 2.0),
        kind=DataKind.RAW,
        source=SOURCE,
    )
    fit = PolynomialFit.fit(two_points, 0)
    # Within one ulp rather than exact: the least-squares solver returns the mean as
    # 0.99999999999999989. The tolerance is nowhere near wide enough to blur the distinction
    # this test exists for — a degrees-of-freedom divisor would put rmse at 1.414.
    assert fit.coefficients[0] == pytest.approx(1.0, rel=1e-15)
    assert fit.residuals(two_points) == pytest.approx((1.0, -1.0), rel=1e-15)
    metrics = fit.metrics(two_points)
    assert metrics.max_abs_error == pytest.approx(1.0, rel=1e-15)
    assert metrics.rmse == pytest.approx(1.0, rel=1e-15)
    assert metrics.r_squared == pytest.approx(0.0, abs=1e-15)


def test_a_negative_degree_is_refused() -> None:
    """A negative degree is an input error, not something to hand to numpy.

    Without the check `available < degree + 1` waves it through and the user meets numpy's
    own `ValueError` as a traceback, which this package does not do to people.
    """
    with pytest.raises(HydrofitError, match="negative"):
        PolynomialFit.fit(series_of(10), -1)
