"""Polynomial fits, and the numbers that say how closely one follows its points."""

import math
import warnings
from dataclasses import dataclass

import numpy as np

from hydrofit.errors import HydrofitError
from hydrofit.models import Series

DEFAULT_DEGREE = 6
"""Degree the legacy tool uses for valve curves, and the one measured against."""


@dataclass(frozen=True, slots=True)
class FitMetrics:
    """How closely a fit follows the points it was made from.

    Attributes:
        r_squared: Share of the variation in y the fit accounts for. ``nan`` when the series
            is flat: R² is measured against the spread of y around its mean, and a series
            with no spread offers nothing to measure against.
        max_abs_error: Largest absolute residual, in the unit of y. The number an engineer
            reads first, because it bounds the worst single point rather than averaging it
            away.
        rmse: Root mean square of the residuals, in the unit of y.
    """

    r_squared: float
    max_abs_error: float
    rmse: float


@dataclass(frozen=True, slots=True)
class PolynomialFit:
    """A polynomial fitted to a series.

    Attributes:
        degree: Degree the fit was asked for.
        coefficients: Powers in descending order, ``x^n`` down to ``x^0``. This is the order
            the spreadsheet formulas consuming them expect; reversing it would pass every
            test of the fit itself and fail against the legacy numbers.
        rank: Rank numpy's least-squares solution reported. Data that supports the degree
            asked of it gives ``degree + 1``; anything lower is numpy's own criterion for
            warning about conditioning. The number is passed on as it came — there is no
            threshold here, because a threshold would be our opinion about someone else's
            data, and the curves this package must reproduce were fitted without one.
        numpy_warnings: What numpy said during the fit, if anything, captured rather than
            silenced. Kept so a caller can repeat it in its own words instead of letting a
            warning surface as noise, or vanish.
    """

    degree: int
    coefficients: tuple[float, ...]
    rank: int
    numpy_warnings: tuple[str, ...]

    @classmethod
    def fit(cls, series: Series, degree: int = DEFAULT_DEGREE) -> "PolynomialFit":
        """Fit a polynomial of the given degree to a series.

        The points are used as they stand — not centred, not scaled. A better-conditioned
        transformation would give a different answer, and matching the numbers already in use
        is the point of this package.

        Args:
            series: The curve to fit.
            degree: Degree of the polynomial.

        Returns:
            The fitted polynomial.

        Raises:
            HydrofitError: If the series holds fewer than ``degree + 1`` points. The check
                lives here and not in ``Series``, which cannot know at construction time what
                degree will later be asked of it.
        """
        available = len(series.x)
        if available < degree + 1:
            raise HydrofitError(
                f"a degree-{degree} fit needs at least {degree + 1} points, "
                f"and {series.product} has {available}"
            )
        # full=True is what carries the rank out; measured 2026-08-29, numpy raises its
        # RankWarning only when full is False, so the two facts cannot be had from one call.
        # The recorder stays anyway: whatever a future numpy emits is kept, not leaked.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            coefficients, _residuals, rank, _singular_values, _rcond = np.polyfit(
                np.asarray(series.x), np.asarray(series.y), degree, full=True
            )
        return cls(
            degree=degree,
            coefficients=tuple(float(value) for value in coefficients),
            rank=int(rank),
            numpy_warnings=tuple(str(entry.message) for entry in caught),
        )

    def evaluate(self, x: float) -> float:
        """Evaluate the polynomial at one x.

        Args:
            x: Where to evaluate. Nothing here checks that it lies within the data: a caller
                that can extrapolate has to say so itself.

        Returns:
            The value of the polynomial at ``x``.
        """
        return float(np.polyval(np.asarray(self.coefficients), x))

    def residuals(self, series: Series) -> tuple[float, ...]:
        """Signed differences between the fit and the points, in the order of the series.

        Args:
            series: The curve to measure against.

        Returns:
            ``fit(x) - y`` for every point.
        """
        predicted = np.polyval(np.asarray(self.coefficients), np.asarray(series.x))
        return tuple(float(value) for value in predicted - np.asarray(series.y))

    def metrics(self, series: Series) -> FitMetrics:
        """Measure the fit against a series.

        Args:
            series: The curve to measure against.

        Returns:
            The three numbers of :class:`FitMetrics`.
        """
        residuals = np.asarray(self.residuals(series))
        y = np.asarray(series.y)
        sum_squared_residuals = float(np.sum(residuals**2))
        sum_squared_deviation = float(np.sum((y - y.mean()) ** 2))
        return FitMetrics(
            r_squared=(
                math.nan
                if sum_squared_deviation == 0.0
                else 1.0 - sum_squared_residuals / sum_squared_deviation
            ),
            max_abs_error=float(np.max(np.abs(residuals))),
            rmse=math.sqrt(sum_squared_residuals / len(residuals)),
        )
