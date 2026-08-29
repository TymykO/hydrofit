"""Unit tests for the fitting layer.

Every assertion here stands on a polynomial whose coefficients are known by construction, so
the expected answer comes from arithmetic rather than from a second run of the same code. The
fits against the legacy numbers live elsewhere; these tests are about the layer itself.
"""

import math

import numpy as np
import pytest

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
    assert np.allclose(fit.coefficients, expected, rtol=1e-9)


@pytest.mark.parametrize("degree", sorted(CURVES))
def test_an_exact_fit_reports_a_perfect_score(degree: int) -> None:
    """On points with no scatter the metrics have nothing left to report."""
    series = series_from(CURVES[degree])
    metrics = PolynomialFit.fit(series, degree).metrics(series)
    # Exactly 1.0, not approximately: the residual sum is ~1e-28 against a deviation sum of
    # order 100, so the subtraction lands on the float itself. Measured at all three degrees.
    assert metrics.r_squared == 1.0
    assert metrics.max_abs_error == pytest.approx(0.0, abs=1e-9)
    assert metrics.rmse == pytest.approx(0.0, abs=1e-9)


def test_the_default_degree_is_six() -> None:
    """The degree the legacy tool uses for valves is the one taken without asking."""
    assert DEFAULT_DEGREE == 6
    assert PolynomialFit.fit(series_from(CURVES[6])).degree == 6


def test_scatter_lowers_every_metric_it_should() -> None:
    """A displaced point shows up in all three numbers, and in the residual that caused it."""
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
    metrics = PolynomialFit.fit(scattered, 2).metrics(scattered)
    assert metrics.r_squared < 1.0
    assert metrics.max_abs_error > 0.1
    assert metrics.rmse < metrics.max_abs_error


def test_evaluate_agrees_with_the_coefficients() -> None:
    """`evaluate` is the polynomial, not an interpolation between stored points."""
    coefficients = CURVES[5]
    fit = PolynomialFit.fit(series_from(coefficients), 5)
    assert fit.evaluate(2.5) == pytest.approx(
        float(np.polyval(np.asarray(coefficients), 2.5)), rel=1e-9
    )


def test_evaluate_extrapolates_without_complaint() -> None:
    """Outside the data the fit still answers; warning about it belongs to the caller."""
    fit = PolynomialFit.fit(series_from(CURVES[2]), 2)
    assert math.isfinite(fit.evaluate(400.0))


def test_residuals_keep_the_order_of_the_series() -> None:
    """One residual per point, positioned as the points are."""
    series = series_from(CURVES[2])
    residuals = PolynomialFit.fit(series, 2).residuals(series)
    assert len(residuals) == len(series.x)
    assert all(abs(value) < 1e-9 for value in residuals)


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
