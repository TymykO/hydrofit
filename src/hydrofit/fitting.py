"""Polynomial fits, and the numbers that say how closely one follows its points."""

import math
from dataclasses import dataclass

import numpy as np

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
    """

    degree: int
    coefficients: tuple[float, ...]

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
        """
        coefficients = np.polyfit(np.asarray(series.x), np.asarray(series.y), degree)
        return cls(degree=degree, coefficients=tuple(float(c) for c in coefficients))

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
