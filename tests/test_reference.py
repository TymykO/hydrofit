"""Parity with the coefficients already in use.

This is the file the phase exists for. Everything else hydrofit does is judged by whether it
is convenient; this is judged by whether it is *the same* — the fourteen catalogue curves,
fitted here, have to reproduce the numbers that have sat in the spreadsheets for years. A
failure here is not a regression in a feature, it is the tool ceasing to be trustworthy.

The comparison runs with `atol=0`. `np.allclose` otherwise adds an absolute term defaulting to
`1e-8`, which against coefficients of this size would decide every comparison and leave the
stated relative tolerance measuring nothing.
"""

from pathlib import Path

import numpy as np
import pytest

from hydrofit.fitting import DEFAULT_DEGREE, PolynomialFit
from legacy_data import point_table_paths, read_expected, read_series

PATHS = point_table_paths()
# Parametrised per file, so a failure names the valve instead of counting the ones that broke.
IDS = [path.stem for path in PATHS]

TOLERANCE = 1e-9


def worst_relative_deviation(
    fitted: tuple[float, ...], expected: tuple[float, ...]
) -> float:
    """Largest relative difference between two coefficient sets.

    Args:
        fitted: Coefficients this package produced.
        expected: Coefficients the legacy tool published.

    Returns:
        The largest ``|fitted - expected| / |expected|`` over the pair.
    """
    got, want = np.asarray(fitted), np.asarray(expected)
    return float(np.max(np.abs((got - want) / want)))


@pytest.mark.parametrize("path", PATHS, ids=IDS)
def test_the_fit_reproduces_the_legacy_coefficients(path: Path) -> None:
    """Each catalogue curve, fitted at the default degree, lands on its published row."""
    series = read_series(path)
    expected = read_expected()[(series.product, series.article_no)]
    fit = PolynomialFit.fit(series, DEFAULT_DEGREE)
    deviation = worst_relative_deviation(fit.coefficients, expected.coefficients)
    assert np.allclose(
        fit.coefficients, expected.coefficients, rtol=TOLERANCE, atol=0
    ), (
        f"{series.product}: worst relative deviation {deviation:.3e} against {TOLERANCE:.0e}"
    )


def test_every_fixture_is_compared() -> None:
    """Fourteen comparisons, none quietly skipped.

    A parametrised suite that silently loses a case reports the same green as one that runs
    them all, so the count is asserted where it can be seen.
    """
    assert len(PATHS) == 14
