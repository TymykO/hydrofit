"""Parity with the coefficients already in use.

Everything else hydrofit does is judged by whether it is convenient. This is judged by
whether it is *the same*: the fourteen catalogue curves, fitted here, have to reproduce the
numbers that have sat in the spreadsheets for years. A failure here is not a regression in a
feature, it is the tool ceasing to be trustworthy.

Two tests measure that, and one contains the other on purpose. The per-series comparison is the
statement of record — one case per valve, failing under the valve's own name, at the tolerance
the numbers are promised to. The drift guard holds every series ten times tighter, so any
per-series failure implies a guard failure but not the reverse; what the guard buys is warning
of a slow slide long before it reaches the promise, and what the per-series cases buy is a
report that names the curve rather than the worst of them.

The comparison runs with `atol=0`. `np.allclose` otherwise adds an absolute term defaulting to
`1e-8`, which against coefficients of this size would decide every comparison and leave the
stated relative tolerance measuring nothing. With no absolute slack the check is strictest
exactly where the coefficients are smallest, which is where several of the worst deviations
sit — one published coefficient is 2.7e-16 and still has to match relatively.

**These fits run on the fixtures exactly as they stand.** One of them, TA-BVS DN200 at a
setting of 1.5, carries a Kv that is plainly wrong; the published coefficients were fitted
through it, so correcting the data would break every comparison here. `tests/data/README.md`
records why, and a test beside the fixtures guards the value. If parity fails right after
someone tidied the data, that is the first place to look.
"""

from pathlib import Path

import numpy as np
import pytest

from hydrofit.fitting import DEFAULT_DEGREE, PolynomialFit
from legacy_data import point_table_paths, read_expected, read_series

PATHS = point_table_paths()
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


# Parametrised per file, so a failure names the valve instead of counting the ones that broke.
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


def test_fourteen_fixtures_are_found() -> None:
    """The parametrisation is fed fourteen point tables.

    This checks its input, not its output: a case that pytest skips or deselects leaves this
    assertion green, and the run's own summary is what shows that. What it does catch is a
    fixture disappearing from the directory, which would otherwise shrink the comparison
    silently to whatever remained.
    """
    assert len(PATHS) == 14


NARROWEST_SPAN = "STAD_DN10"

# Ten times inside the parity tolerance, and 32x above the largest deviation measured on
# 2026-08-29 (3.148e-12, on TA-BVS DN125). Drift shows up here as a failing test long before it
# could reach 1e-9; tighter would start measuring the machine's LAPACK rather than the code.
DRIFT_BOUND = 1e-10


def test_the_narrowest_span_is_fitted_at_full_rank() -> None:
    """The series with the tightest Kv span carries a degree-6 fit at full rank.

    A narrow span was expected to be the hardest thing to fit here, and that expectation came
    from the shape of the data rather than from any measurement of it. Measured, this series
    returns rank 7 of 7. It stays as a case because it is where a change in conditioning would
    surface first, and it asserts the rank rather than the coefficients: the comparison is made
    for every series already, this one included.

    Which series is narrowest is asserted too, not assumed — a new fixture with a tighter span
    would otherwise leave this test passing under a name that had stopped being true.
    """
    matching = [path for path in PATHS if path.stem == NARROWEST_SPAN]
    if not matching:
        pytest.fail(f"no fixture named {NARROWEST_SPAN} — was it renamed?")
    series = read_series(matching[0])
    narrowest = min(
        (read_series(path) for path in PATHS),
        key=lambda candidate: max(candidate.x) - min(candidate.x),
    )
    assert narrowest.product == series.product
    fit = PolynomialFit.fit(series, DEFAULT_DEGREE)
    assert fit.rank == DEFAULT_DEGREE + 1


def test_no_series_has_drifted_towards_the_tolerance() -> None:
    """The worst deviation across all fourteen stays far under the parity tolerance.

    The per-series tests answer "do we still match?"; this one answers "are we getting worse?"
    — a question no single comparison asks. A numpy release, a different LAPACK, or a change in
    how the points are read could move every series a little without breaking any of them, and
    that is precisely the drift worth catching while there is still room to investigate it.
    """
    # Keyed by the pair that identifies a series everywhere else in this file. Product names
    # happen to be unique across the fourteen today; keying on one of them would make that
    # accident load-bearing, and a collision would drop a series from the comparison in silence.
    deviations: dict[tuple[str, str], float] = {}
    for path in PATHS:
        series = read_series(path)
        expected = read_expected()[(series.product, series.article_no)]
        fit = PolynomialFit.fit(series, DEFAULT_DEGREE)
        deviations[(series.product, series.article_no)] = worst_relative_deviation(
            fit.coefficients, expected.coefficients
        )
    # Asserted here as well as against PATHS, so this test states the whole claim by itself:
    # fourteen series compared, none lost to a key collision on the way.
    assert len(deviations) == len(PATHS) == 14
    # Written as "not below" rather than "above" so that a non-finite value counts as an
    # offender. The deviation is a ratio: a published coefficient of zero yields inf, and 0/0
    # yields nan, both with a RuntimeWarning from numpy. No coefficient is zero today — the
    # smallest is 5.1e-17 — and this phrasing is what keeps that from becoming a silent
    # assumption, since `value > bound` would let a nan through.
    offenders = {
        name: value for name, value in deviations.items() if not value < DRIFT_BOUND
    }
    assert not offenders, "; ".join(
        f"{product}: {value:.3e} against the early-warning bound {DRIFT_BOUND:.0e}, "
        f"parity tolerance {TOLERANCE:.0e}"
        for (product, _), value in sorted(offenders.items())
    )
