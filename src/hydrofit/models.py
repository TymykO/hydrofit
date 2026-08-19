"""Domain model: an axis, a data kind, an import source, and the series itself.

`Series` normalises and validates on creation, so every consumer downstream — store, fitting,
plotting, export — may assume finite values and strictly increasing x without checking again.
The one invariant deliberately *not* enforced here is the number of points a fit needs: at
creation time nobody knows which degree will be asked for, so `len(points) >= degree + 1`
belongs to the fit.
"""

import math
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from hydrofit.errors import HydrofitError

# Whitespace plus the characters Windows forbids in a file name. Sheet names follow the
# convention "<product> | <article no.>", so a stray "|" is a realistic input; without this
# replacement it would surface as an OSError from the filesystem rather than a HydrofitError.
_UNSAFE_IN_SLUG = re.compile(r'[\\/:*?"<>|\s]+')
_REPEATED_DASHES = re.compile(r"-{2,}")


def _slugify(text: str) -> str:
    """Turn free-form product text into a file-system-safe identifier.

    Lowercasing is not cosmetic: NTFS is case-insensitive, so two series differing only in case
    would collide as files while still looking distinct in the catalogue — a collision the
    store could not explain.

    Args:
        text: Product and article text, in the spelling the catalogue uses.

    Returns:
        A lowercase slug with unsafe characters replaced by single dashes.

    Raises:
        HydrofitError: If no usable character survives the replacement.
    """
    slug = _REPEATED_DASHES.sub(
        "-", _UNSAFE_IN_SLUG.sub("-", text.strip().lower())
    ).strip("-")
    if not slug:
        raise HydrofitError(f"cannot build a slug from {text!r}")
    return slug


@dataclass(frozen=True, slots=True)
class AxisSpec:
    """One axis of a series: the quantity and the unit it is measured in.

    Attributes:
        name: Quantity name as it appears in the source label, for example ``Kv``.
        unit: Unit as it appears in the source label, for example ``m³/h``. A
            dimensionless quantity carries ``-``.
    """

    name: str
    unit: str

    def __post_init__(self) -> None:
        """Reject an incomplete label.

        Raises:
            HydrofitError: If the name or the unit is empty or blank.
        """
        if not self.name.strip():
            raise HydrofitError("an axis needs a name")
        if not self.unit.strip():
            raise HydrofitError(f"axis {self.name!r} needs a unit")

    @property
    def label(self) -> str:
        """The axis label in source form, for example ``Kv [m³/h]``."""
        return f"{self.name} [{self.unit}]"


class DataKind(StrEnum):
    """Whether the points were read from a catalogue or generated from a curve."""

    RAW = "raw"
    GENERATED = "generated"


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Where a series came from.

    Attributes:
        file: Name of the spreadsheet the series was imported from.
        sheet: Sheet name inside that file.
        imported_at: ISO-8601 timestamp supplied by the caller. Nothing in the domain reads the
            clock; the time is decided at the edge of the program and handed in, which is what
            keeps a stored catalogue byte-identical between runs.
    """

    file: str
    sheet: str
    imported_at: str

    def __post_init__(self) -> None:
        """Check that the timestamp is a date the catalogue can be trusted to carry.

        Raises:
            HydrofitError: If ``imported_at`` is not an ISO-8601 timestamp.
        """
        try:
            datetime.fromisoformat(self.imported_at)
        except ValueError as exc:
            raise HydrofitError(
                f"imported_at is not an ISO-8601 timestamp: {self.imported_at!r}"
            ) from exc


@dataclass(frozen=True, slots=True)
class Series:
    """An x/y curve for one product, valid by construction.

    The pairs are sorted by x and stored as tuples. Tuples rather than lists because a frozen
    dataclass holding a list is not actually immutable, and because the constructor reorders
    the points and therefore has to own its copy of them.

    Attributes:
        product: Product name in the spelling the catalogue uses, e.g. ``STAD DN15``.
        article_no: Catalogue article number.
        x_axis: What x measures, and in which unit.
        y_axis: What y measures, and in which unit.
        x: Strictly increasing x values.
        y: y values, paired with x by position.
        kind: Whether the points are raw readings or generated from a curve.
        source: Where the series was imported from.
    """

    product: str
    article_no: str
    x_axis: AxisSpec
    y_axis: AxisSpec
    x: tuple[float, ...]
    y: tuple[float, ...]
    kind: DataKind
    source: SourceRef

    def __post_init__(self) -> None:
        """Normalise the point order and enforce the invariants of a series.

        Raises:
            HydrofitError: If the values are not numbers, the two axes hold different counts,
                there are no points, a value is not finite, or an x value repeats.
        """
        try:
            x = tuple(float(value) for value in self.x)
            y = tuple(float(value) for value in self.y)
        except (TypeError, ValueError) as exc:
            raise HydrofitError(f"series points must be numbers: {exc}") from exc

        if len(x) != len(y):
            raise HydrofitError(f"x holds {len(x)} values and y holds {len(y)}")
        if not x:
            raise HydrofitError("a series needs at least one point")
        for axis, values in (("x", x), ("y", y)):
            for value in values:
                if not math.isfinite(value):
                    raise HydrofitError(
                        f"{axis} holds a value that is not finite: {value!r}"
                    )

        pairs = sorted(zip(x, y, strict=True))
        x = tuple(pair[0] for pair in pairs)
        y = tuple(pair[1] for pair in pairs)

        # Sorting leaves the values non-decreasing, so equal neighbours are the only way strict
        # increase can still fail. A duplicate x is rejected rather than tolerated because
        # polyfit would not reject it either — it would quietly average two different y into
        # one, and the series would go on looking healthy.
        for earlier, later in zip(x, x[1:], strict=False):
            if earlier == later:
                raise HydrofitError(f"x repeats the value {earlier!r}")

        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)

    @property
    def slug(self) -> str:
        """File-system-safe identifier built from the product and the article number."""
        return _slugify(f"{self.product} {self.article_no}")

    def x_range(self) -> tuple[float, float]:
        """The first and last x.

        Returns:
            The smallest and largest x. The points are sorted, so these are the ends.
        """
        return self.x[0], self.x[-1]

    def y_range(self) -> tuple[float, float]:
        """The extent of y.

        Returns:
            The smallest and largest y. Unlike x, y has no order — a curve may fall as x grows
            — so this is a min/max scan rather than the ends of the sequence.
        """
        return min(self.y), max(self.y)
