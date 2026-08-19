"""Unit tests for the domain model.

Every fixture is built here rather than read from disk: the model is the layer that decides
what a valid series is, so its tests must not depend on a file that happens to hold one.
"""

import math
from typing import cast

import pytest

from hydrofit.errors import HydrofitError
from hydrofit.models import AxisSpec, DataKind, Series, SourceRef

KV = AxisSpec("kv", "m3/h")
OPENING = AxisSpec("n", "%")
SOURCE = SourceRef("BV - IMI.xlsx", "STAD DN15 | 52 151-015", "2026-08-19T10:00:00")


def make_series(
    x: tuple[float, ...] = (1.0, 2.0, 3.0),
    y: tuple[float, ...] = (10.0, 20.0, 30.0),
    product: str = "STAD DN15",
    article_no: str = "52 151-015",
    kind: DataKind = DataKind.RAW,
) -> Series:
    """Build a valid series, letting a test override only what it is about.

    Args:
        x: x values, in any order.
        y: y values, paired with x by position.
        product: Product name.
        article_no: Catalogue article number.
        kind: Raw or generated.

    Returns:
        The constructed series.
    """
    return Series(
        product=product,
        article_no=article_no,
        x_axis=KV,
        y_axis=OPENING,
        x=x,
        y=y,
        kind=kind,
        source=SOURCE,
    )


def test_valid_series_keeps_its_points() -> None:
    """A series built from ordered points holds exactly those points."""
    series = make_series()
    assert series.x == (1.0, 2.0, 3.0)
    assert series.y == (10.0, 20.0, 30.0)


def test_points_are_stored_as_tuples() -> None:
    """Points are tuples even when the caller passes another sequence."""
    series = make_series(
        x=cast(tuple[float, ...], [3.0, 1.0]), y=cast(tuple[float, ...], [30.0, 10.0])
    )
    assert isinstance(series.x, tuple)
    assert isinstance(series.y, tuple)


def test_points_are_sorted_by_x_without_unpairing_y() -> None:
    """Unordered input comes back sorted, with each y still on its own x."""
    series = make_series(x=(3.0, 1.0, 2.0), y=(30.0, 10.0, 20.0))
    assert series.x == (1.0, 2.0, 3.0)
    assert series.y == (10.0, 20.0, 30.0)


def test_integers_become_floats() -> None:
    """Whole numbers are stored as floats, so the store writes one number format."""
    series = make_series(
        x=cast(tuple[float, ...], (1, 2)), y=cast(tuple[float, ...], (10, 20))
    )
    assert series.x == (1.0, 2.0)
    assert all(isinstance(value, float) for value in series.x)


def test_length_mismatch_is_an_error() -> None:
    """Axes of different lengths cannot describe a curve."""
    with pytest.raises(HydrofitError, match="x holds 3 values and y holds 2"):
        make_series(x=(1.0, 2.0, 3.0), y=(10.0, 20.0))


def test_empty_series_is_an_error() -> None:
    """A series with no points is rejected at creation, not later."""
    with pytest.raises(HydrofitError, match="at least one point"):
        make_series(x=(), y=())


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_x_is_an_error(value: float) -> None:
    """A non-finite x is rejected.

    Args:
        value: The offending value.
    """
    with pytest.raises(HydrofitError, match="x holds a value that is not finite"):
        make_series(x=(1.0, value), y=(10.0, 20.0))


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_y_is_an_error(value: float) -> None:
    """A non-finite y is rejected, and named as y rather than as x.

    Args:
        value: The offending value.
    """
    with pytest.raises(HydrofitError, match="y holds a value that is not finite"):
        make_series(x=(1.0, 2.0), y=(10.0, value))


def test_duplicate_x_is_an_error() -> None:
    """Two points sharing an x are rejected rather than silently averaged by a later fit."""
    with pytest.raises(HydrofitError, match="x repeats the value 2.0"):
        make_series(x=(1.0, 2.0, 2.0), y=(10.0, 20.0, 25.0))


def test_duplicate_x_is_caught_after_sorting() -> None:
    """The duplicate check survives unordered input — sorting is what makes it visible."""
    with pytest.raises(HydrofitError, match="x repeats the value 2.0"):
        make_series(x=(2.0, 1.0, 2.0), y=(20.0, 10.0, 25.0))


def test_non_numeric_value_is_an_error() -> None:
    """Text where a number belongs is an input error, not a traceback."""
    # The cast is deliberate: this is the runtime guard for values that reach the model from a
    # spreadsheet cell, where the type checker cannot help.
    with pytest.raises(HydrofitError, match="series points must be numbers"):
        make_series(x=cast(tuple[float, ...], ("nonsense", 2.0)), y=(10.0, 20.0))


def test_x_range_is_the_ends() -> None:
    """x_range reports the first and last x of the sorted points."""
    assert make_series(x=(3.0, 1.0, 2.0), y=(30.0, 10.0, 20.0)).x_range() == (1.0, 3.0)


def test_y_range_scans_rather_than_taking_the_ends() -> None:
    """y_range holds for a falling curve, where the ends are not the extremes."""
    series = make_series(x=(1.0, 2.0, 3.0), y=(30.0, 5.0, 20.0))
    assert series.y_range() == (5.0, 30.0)


def test_slug_is_lowercase_and_dashed() -> None:
    """The slug joins product and article number in a form a file name accepts."""
    assert (
        make_series(product="STAD DN15", article_no="52 151-015").slug
        == "stad-dn15-52-151-015"
    )


def test_slug_replaces_characters_windows_forbids() -> None:
    """A sheet-style name with a pipe or a slash still yields a usable file name."""
    series = make_series(product="TA-BVS DN15 | A", article_no='52/151:015?"<>*')
    assert series.slug == "ta-bvs-dn15-a-52-151-015"


def test_slug_without_usable_characters_is_an_error() -> None:
    """A product made only of separators cannot name a file."""
    with pytest.raises(HydrofitError, match="cannot build a slug"):
        _ = make_series(product="///", article_no="   ").slug


def test_axis_label_is_the_source_form() -> None:
    """An axis renders back into the label the spreadsheet carried."""
    assert KV.label == "kv [m3/h]"


def test_axis_without_a_unit_is_an_error() -> None:
    """A missing unit is an import problem worth hearing about, not an empty bracket."""
    with pytest.raises(HydrofitError, match="needs a unit"):
        AxisSpec("kv", "  ")


def test_axis_without_a_name_is_an_error() -> None:
    """An axis with no name is rejected."""
    with pytest.raises(HydrofitError, match="needs a name"):
        AxisSpec("", "m3/h")


def test_data_kind_carries_its_stored_spelling() -> None:
    """DataKind serialises as the string the catalogue holds, with no converter."""
    assert str(DataKind.RAW) == "raw"
    assert DataKind("generated") is DataKind.GENERATED


def test_source_rejects_a_timestamp_it_cannot_parse() -> None:
    """A junk timestamp is refused before it can reach the catalogue."""
    with pytest.raises(HydrofitError, match="not an ISO-8601 timestamp"):
        SourceRef("BV - IMI.xlsx", "STAD DN15", "yesterday")
