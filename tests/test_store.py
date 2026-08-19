"""Unit tests for the series store.

The heart of this file is the lossless round-trip: a stored series must come back bit for bit,
because the coefficients fitted to it are asserted against the legacy results at rtol 1e-9, and
rounding at storage time would break that far from its cause. Comparisons are made on `repr`
rather than on `==` — for floats that is the comparison that actually means "the same number".
"""

import json
import math
from pathlib import Path

import pytest

from hydrofit.errors import HydrofitError
from hydrofit.models import AxisSpec, DataKind, Series, SourceRef
from hydrofit.store import SeriesStore

KV = AxisSpec("kv", "m3/h")
OPENING = AxisSpec("n", "%")
SOURCE = SourceRef("BV - IMI.xlsx", "STAD DN15 | 52 151-015", "2026-08-19T10:00:00")


def make_series(
    x: tuple[float, ...] = (1.0, 2.0),
    y: tuple[float, ...] = (10.0, 20.0),
    product: str = "STAD DN15",
    article_no: str = "52 151-015",
    kind: DataKind = DataKind.RAW,
) -> Series:
    """Build a valid series, letting a test override only what it is about.

    Args:
        x: x values.
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


def lossless_points(count: int = 701) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Build points whose decimal form needs every significant digit.

    The second x sits one ULP above the first: any formatting to a fixed number of places
    would merge the two into one value, which is exactly the failure this suite must catch.

    Args:
        count: How many points to build. 701 is the size of a generated STAD series.

    Returns:
        The x values and the y values.
    """
    x = [1.0 + index / 7.0 for index in range(count)]
    x[1] = math.nextafter(x[0], math.inf)
    y = [math.pi * (index + 1) / 3.0 for index in range(count)]
    return tuple(x), tuple(y)


def test_round_trip_is_lossless_for_a_701_point_series(tmp_path: Path) -> None:
    """A 701-point series comes back with every value unchanged, bit for bit.

    Args:
        tmp_path: Directory for this test's store.
    """
    x, y = lossless_points()
    series = make_series(x=x, y=y)
    store = SeriesStore(tmp_path)

    store.save(series)
    loaded = store.load(series.slug)

    assert len(loaded.x) == 701
    assert [repr(value) for value in loaded.x] == [repr(value) for value in series.x]
    assert [repr(value) for value in loaded.y] == [repr(value) for value in series.y]


def test_one_ulp_neighbours_stay_distinct(tmp_path: Path) -> None:
    """Two x values one ULP apart survive as two values, not one.

    Args:
        tmp_path: Directory for this test's store.
    """
    lower = 1.0
    upper = math.nextafter(lower, math.inf)
    series = make_series(x=(lower, upper, 2.0), y=(10.0, 11.0, 20.0))
    store = SeriesStore(tmp_path)

    store.save(series)
    loaded = store.load(series.slug)

    assert loaded.x[0] != loaded.x[1]
    assert repr(loaded.x[1]) == repr(upper)


def test_points_file_holds_reprs_and_lf_endings(tmp_path: Path) -> None:
    """The points file is plain, LF-terminated and written value for value.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    series = make_series()

    store.save(series)

    assert store.points_path(series.slug).read_bytes() == b"x,y\n1.0,10.0\n2.0,20.0\n"


def test_metadata_survives_the_round_trip(tmp_path: Path) -> None:
    """Axes, kind and source come back as they went in.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    series = make_series(kind=DataKind.GENERATED)

    store.save(series)
    loaded = store.load(series.slug)

    assert loaded.product == series.product
    assert loaded.article_no == series.article_no
    assert loaded.x_axis == KV
    assert loaded.y_axis == OPENING
    assert loaded.kind is DataKind.GENERATED
    assert loaded.source == SOURCE


def test_catalogue_text_is_sorted_and_indented(tmp_path: Path) -> None:
    """The catalogue is written in a shape a git diff can read line by line.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)

    store.save(make_series())

    assert (
        store.catalog_path.read_text(encoding="utf-8")
        == """{
  "stad-dn15-52-151-015": {
    "article_no": "52 151-015",
    "kind": "raw",
    "product": "STAD DN15",
    "source": {
      "file": "BV - IMI.xlsx",
      "imported_at": "2026-08-19T10:00:00",
      "sheet": "STAD DN15 | 52 151-015"
    },
    "x_axis": {
      "name": "kv",
      "unit": "m3/h"
    },
    "x_range": [
      1.0,
      2.0
    ],
    "y_axis": {
      "name": "n",
      "unit": "%"
    },
    "y_range": [
      10.0,
      20.0
    ]
  }
}
"""
    )


def test_catalogue_is_byte_stable_across_saves(tmp_path: Path) -> None:
    """Saving the same series twice produces the same file, to the byte.

    Nothing in the store reads the clock, so there is no field that could differ.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    series = make_series()

    store.save(series)
    first = store.catalog_path.read_bytes()
    store.save(series)
    second = store.catalog_path.read_bytes()

    assert first == second
    assert b"\r\n" not in first


def test_catalogue_orders_its_slugs(tmp_path: Path) -> None:
    """Entries are written in slug order regardless of the order they were saved in.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    store.save(make_series(product="TA-BVS DN15", article_no="52 191-015"))
    store.save(make_series(product="STAD DN15", article_no="52 151-015"))

    catalog = json.loads(store.catalog_path.read_text(encoding="utf-8"))

    assert list(catalog) == ["stad-dn15-52-151-015", "ta-bvs-dn15-52-191-015"]


def test_a_range_that_disagrees_with_the_points_is_an_error(tmp_path: Path) -> None:
    """A hand-edited catalogue cannot quietly contradict the points it describes.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    series = make_series()
    store.save(series)

    catalog = json.loads(store.catalog_path.read_text(encoding="utf-8"))
    catalog[series.slug]["x_range"] = [1.0, 99.0]
    store.catalog_path.write_text(json.dumps(catalog), encoding="utf-8", newline="\n")

    with pytest.raises(HydrofitError, match="claims x runs"):
        store.load(series.slug)


def test_slug_collision_between_different_series_is_an_error(tmp_path: Path) -> None:
    """Two different series that slugify the same are refused, not silently merged.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    store.save(make_series(product="STAD DN15", article_no="52 151-015"))

    with pytest.raises(HydrofitError, match="already belongs to"):
        store.save(make_series(product="stad dn15", article_no="52-151-015"))


def test_resaving_the_same_series_replaces_its_points(tmp_path: Path) -> None:
    """Re-importing a series is a normal operation, not a collision.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    store.save(make_series(x=(1.0, 2.0), y=(10.0, 20.0)))

    store.save(make_series(x=(1.0, 2.0, 3.0), y=(11.0, 21.0, 31.0)))
    loaded = store.load("stad-dn15-52-151-015")

    assert loaded.x == (1.0, 2.0, 3.0)
    assert loaded.y == (11.0, 21.0, 31.0)


def test_unknown_slug_is_an_error(tmp_path: Path) -> None:
    """Asking for a series that was never stored is an input error.

    Args:
        tmp_path: Directory for this test's store.
    """
    with pytest.raises(HydrofitError, match="no series named 'nothing'"):
        SeriesStore(tmp_path).load("nothing")


def test_unreadable_catalogue_is_an_error(tmp_path: Path) -> None:
    """A corrupted catalogue is reported, not raised as a JSON traceback.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    store.catalog_path.write_text("{ this is not json", encoding="utf-8")

    with pytest.raises(HydrofitError, match="not readable JSON"):
        store.load("anything")


def test_missing_points_file_is_an_error(tmp_path: Path) -> None:
    """A catalogue entry without its points is reported against that series.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    series = make_series()
    store.save(series)
    store.points_path(series.slug).unlink()

    with pytest.raises(HydrofitError, match="is missing"):
        store.load(series.slug)


def test_list_series_is_sorted_by_slug(tmp_path: Path) -> None:
    """Listing returns every series, in slug order.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    store.save(make_series(product="TA-BVS DN15", article_no="52 191-015"))
    store.save(make_series(product="STAD DN15", article_no="52 151-015"))

    assert [series.slug for series in store.list_series()] == [
        "stad-dn15-52-151-015",
        "ta-bvs-dn15-52-191-015",
    ]


def test_an_empty_store_lists_nothing(tmp_path: Path) -> None:
    """A directory with no catalogue is an empty store, not an error.

    Args:
        tmp_path: Directory for this test's store.
    """
    assert SeriesStore(tmp_path).list_series() == []


def corrupt_catalog(store: SeriesStore, slug: str, key: str, value: object) -> None:
    """Overwrite one field of one catalogue entry, the way a hand edit would.

    Args:
        store: The store to damage.
        slug: Entry to damage.
        key: Field to overwrite.
        value: Value to write in its place.
    """
    catalog = json.loads(store.catalog_path.read_text(encoding="utf-8"))
    catalog[slug][key] = value
    store.catalog_path.write_text(json.dumps(catalog), encoding="utf-8", newline="\n")


def test_catalogue_entry_that_is_not_an_object_is_an_error(tmp_path: Path) -> None:
    """A record replaced by a string is reported, not unpacked blindly.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    series = make_series()
    store.save(series)
    store.catalog_path.write_text(
        json.dumps({series.slug: "not a record"}), encoding="utf-8", newline="\n"
    )

    with pytest.raises(HydrofitError, match="is not a JSON object"):
        store.load(series.slug)


def test_catalogue_entry_missing_a_field_is_an_error(tmp_path: Path) -> None:
    """A record without its product cannot rebuild a series.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    series = make_series()
    store.save(series)
    catalog = json.loads(store.catalog_path.read_text(encoding="utf-8"))
    del catalog[series.slug]["product"]
    store.catalog_path.write_text(json.dumps(catalog), encoding="utf-8", newline="\n")

    with pytest.raises(HydrofitError, match="has no text field 'product'"):
        store.load(series.slug)


@pytest.mark.parametrize("bad_range", ["1.0 to 2.0", [1.0], [True, 2.0], ["a", "b"]])
def test_catalogue_range_that_is_not_two_numbers_is_an_error(
    tmp_path: Path, bad_range: object
) -> None:
    """A range that is not a pair of numbers is refused.

    Args:
        tmp_path: Directory for this test's store.
        bad_range: The malformed value to write.
    """
    store = SeriesStore(tmp_path)
    series = make_series()
    store.save(series)
    corrupt_catalog(store, series.slug, "x_range", bad_range)

    with pytest.raises(HydrofitError, match="'x_range'"):
        store.load(series.slug)


def test_catalogue_kind_that_is_unknown_is_an_error(tmp_path: Path) -> None:
    """A kind outside the enum names the offending value.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    series = make_series()
    store.save(series)
    corrupt_catalog(store, series.slug, "kind", "invented")

    with pytest.raises(HydrofitError, match="unknown kind 'invented'"):
        store.load(series.slug)


def test_points_file_without_the_header_is_an_error(tmp_path: Path) -> None:
    """A points file that does not start with the header is refused.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    series = make_series()
    store.save(series)
    store.points_path(series.slug).write_text(
        "1.0,10.0\n", encoding="utf-8", newline="\n"
    )

    with pytest.raises(HydrofitError, match="does not start with an 'x,y' header"):
        store.load(series.slug)


def test_points_row_that_is_not_a_pair_is_an_error(tmp_path: Path) -> None:
    """A row with the wrong number of fields is reported with its line number.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    series = make_series()
    store.save(series)
    store.points_path(series.slug).write_text(
        "x,y\n1.0,10.0\n2.0,20.0,extra\n", encoding="utf-8", newline="\n"
    )

    with pytest.raises(HydrofitError, match="line 3 does not hold two values"):
        store.load(series.slug)


def test_points_row_that_is_not_numeric_is_an_error(tmp_path: Path) -> None:
    """Text in a points file is an input error, not a traceback.

    Args:
        tmp_path: Directory for this test's store.
    """
    store = SeriesStore(tmp_path)
    series = make_series()
    store.save(series)
    store.points_path(series.slug).write_text(
        "x,y\n1.0,10.0\nnonsense,20.0\n", encoding="utf-8", newline="\n"
    )

    with pytest.raises(HydrofitError, match="line 3 is not a pair of numbers"):
        store.load(series.slug)


def filled_store(root: Path) -> SeriesStore:
    """Build a store holding three series across two products and both kinds.

    Args:
        root: Directory for the store.

    Returns:
        The populated store.
    """
    store = SeriesStore(root)
    store.save(make_series(product="STAD DN10", article_no="52 151-010"))
    store.save(
        make_series(
            product="STAD DN15", article_no="52 151-015", kind=DataKind.GENERATED
        )
    )
    store.save(make_series(product="TA-BVS DN15", article_no="52 191-015"))
    return store


def test_product_filter_matches_part_of_the_name(tmp_path: Path) -> None:
    """A product filter selects every series whose name contains it.

    Args:
        tmp_path: Directory for this test's store.
    """
    matched = filled_store(tmp_path).list_series(product="STAD")

    assert [series.product for series in matched] == ["STAD DN10", "STAD DN15"]


def test_product_filter_ignores_case(tmp_path: Path) -> None:
    """The filter is spelled the way the user types it, not the way the catalogue does.

    Args:
        tmp_path: Directory for this test's store.
    """
    matched = filled_store(tmp_path).list_series(product="stad")

    assert [series.product for series in matched] == ["STAD DN10", "STAD DN15"]


def test_kind_filter_selects_one_kind(tmp_path: Path) -> None:
    """A kind filter keeps only series of that kind.

    Args:
        tmp_path: Directory for this test's store.
    """
    matched = filled_store(tmp_path).list_series(kind=DataKind.GENERATED)

    assert [series.product for series in matched] == ["STAD DN15"]


def test_filters_combine(tmp_path: Path) -> None:
    """Both filters apply at once.

    Args:
        tmp_path: Directory for this test's store.
    """
    matched = filled_store(tmp_path).list_series(product="DN15", kind=DataKind.RAW)

    assert [series.product for series in matched] == ["TA-BVS DN15"]


def test_a_filter_that_matches_nothing_returns_an_empty_list(tmp_path: Path) -> None:
    """No match is an answer, not an error.

    Args:
        tmp_path: Directory for this test's store.
    """
    assert filled_store(tmp_path).list_series(product="no such valve") == []
