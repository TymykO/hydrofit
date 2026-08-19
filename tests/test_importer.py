"""Unit tests for the spreadsheet importer.

Every workbook here is built in the test, so nothing depends on the catalogue file the owner
imports by hand. Two assertions carry more weight than their size suggests: that column A
becomes the *y* axis and column B the *x* axis, and that a broken sheet is reported against
itself while its neighbours still import. Both encode contract decisions that would otherwise
be invisible until a fit came out mirrored or an import went silently short.
"""

from pathlib import Path

import pytest
from openpyxl import Workbook

from hydrofit.errors import HydrofitError
from hydrofit.importer import (
    ImportResult,
    classify_kind,
    has_uniform_step,
    import_workbook,
    parse_label,
    parse_number,
    split_sheet_name,
)
from hydrofit.models import DataKind

SHEET = "STAD 15 | 52 851-015"
STAMP = "2026-08-19T10:00:00"

# The labels the real catalogue carries, superscript included. Anything ASCII here would test a
# file that does not exist.
LABELS: tuple[object, object] = ("n [-]", "Kv [m³/h]")


def write_workbook(path: Path, sheets: dict[str, list[tuple[object, ...]]]) -> Path:
    """Build a workbook from literal cell values.

    Args:
        path: Where to write the file.
        sheets: Sheet name to its rows, each row a tuple of cell values.

    Returns:
        The path written, for use in a call.
    """
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        worksheet = workbook.create_sheet(title=name)
        for row in rows:
            worksheet.append(list(row))
    workbook.save(path)
    return path


def one_sheet(path: Path, rows: list[tuple[object, ...]], name: str = SHEET) -> Path:
    """Build a single-sheet workbook.

    Args:
        path: Where to write the file.
        rows: Rows of that sheet, header included.
        name: Sheet name.

    Returns:
        The path written.
    """
    return write_workbook(path, {name: rows})


def imported(path: Path, **kwargs: object) -> ImportResult:
    """Import a workbook with the fixed timestamp these tests share.

    No kind is forced, so every call here also exercises the classification.

    Args:
        path: Workbook to read.
        **kwargs: Passed straight through to the importer.

    Returns:
        The import result.
    """
    sheet = kwargs.get("sheet")
    assert sheet is None or isinstance(sheet, str)
    return import_workbook(path, imported_at=STAMP, sheet=sheet)


def grid(count: int, step: float = 0.005, start: float = 0.5) -> list[float]:
    """Build settings on an even grid, the way a generated sheet lists them.

    Args:
        count: How many settings to produce.
        step: Distance between neighbours.
        start: First setting.

    Returns:
        The settings, ascending.
    """
    return [start + index * step for index in range(count)]


def curve_rows(settings: list[float]) -> list[tuple[object, ...]]:
    """Pair settings with kv values that are never evenly spaced.

    The squaring matters: a generated catalogue computes kv from the setting, so kv lands
    wherever the curve puts it. A fixture with evenly spaced kv would let a classifier that
    reads the wrong column pass.

    Args:
        settings: Setting values for column A.

    Returns:
        Rows ready for a sheet, header excluded.
    """
    return [(value, round(value**2 + 0.05, 10)) for value in settings]


def inverse_curve_rows(flows: list[float]) -> list[tuple[object, ...]]:
    """Pair an even grid on **x** with a y computed from it.

    The mirror image of `curve_rows`, and the shape the next instrument family will arrive in:
    there the free variable is the one that gets turned, so the even column is x.

    Args:
        flows: x values on an even grid.

    Returns:
        Rows ready for a sheet, header excluded.
    """
    return [(round(value**2 + 0.05, 10), value) for value in flows]


def test_sheet_name_splits_into_product_and_article() -> None:
    """The convention `<product> | <article no.>` yields both fields, stripped."""
    assert split_sheet_name(SHEET) == ("STAD 15", "52 851-015")


@pytest.mark.parametrize(
    "name",
    ["STAD 15", "STAD | 15 | 52", " | 52 851-015", "STAD 15 | "],
)
def test_sheet_name_without_the_convention_is_rejected(name: str) -> None:
    """A missing, doubled, or one-sided separator is an error, not a guess.

    Args:
        name: Sheet name that does not follow the convention.
    """
    with pytest.raises(HydrofitError):
        split_sheet_name(name)


def test_label_keeps_the_unit_without_its_brackets() -> None:
    """The parser strips the brackets and `label` puts them back."""
    axis = parse_label("Kv [m³/h]", "B1")
    assert (axis.name, axis.unit) == ("Kv", "m³/h")
    assert axis.label == "Kv [m³/h]"


def test_dimensionless_label_carries_a_dash() -> None:
    """A dimensionless quantity reads as `-`, which is a unit like any other."""
    axis = parse_label("n [-]", "A1")
    assert (axis.name, axis.unit) == ("n", "-")
    assert axis.label == "n [-]"


@pytest.mark.parametrize("text", ["Kv", "Kv m3/h", "Kv []", "[m3/h]", "Kv [m3/h"])
def test_label_without_a_unit_in_brackets_is_rejected(text: str) -> None:
    """No brackets, no unit, no name — each is an error naming the cell.

    Args:
        text: Label text that does not follow the convention.
    """
    with pytest.raises(HydrofitError, match="B1"):
        parse_label(text, "B1")


def test_label_cell_that_is_not_text_is_rejected() -> None:
    """A numeric or empty header cell cannot be an axis label."""
    with pytest.raises(HydrofitError, match="A1"):
        parse_label(None, "A1")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, 1.0),
        (1.5, 1.5),
        ("1.5", 1.5),
        ("1,5", 1.5),
        (" 1,5 ", 1.5),
        ("-0,054", -0.054),
    ],
)
def test_numbers_accept_the_decimal_comma(value: object, expected: float) -> None:
    """Text cells written with a decimal comma are read as numbers.

    Args:
        value: Cell value as a spreadsheet would return it.
        expected: The number it stands for.
    """
    assert parse_number(value, "B2") == expected


@pytest.mark.parametrize("value", ["", "  ", "n/a", None, True, False, object()])
def test_non_numeric_cells_are_rejected(value: object) -> None:
    """Anything that is not a number is an error naming the cell.

    `True` is in this list on purpose: bool subclasses int, so without an explicit check it
    would import as 1.0 and the series would look healthy.

    Args:
        value: Cell value that is not a number.
    """
    with pytest.raises(HydrofitError, match="B2"):
        parse_number(value, "B2")


def test_column_a_is_the_y_axis_and_column_b_is_the_x_axis(tmp_path: Path) -> None:
    """The axes are not interchangeable: A carries the setting, B carries kv."""
    path = one_sheet(
        tmp_path / "bv.xlsx",
        [LABELS, (0.5, 0.054), (1.0, 0.136), (1.5, 0.533)],
    )
    (series,) = imported(path).series

    assert series.y_axis.label == "n [-]"
    assert series.x_axis.label == "Kv [m³/h]"
    assert series.y == (0.5, 1.0, 1.5)
    assert series.x == (0.054, 0.136, 0.533)


def test_series_carries_the_sheet_identity_and_the_given_timestamp(
    tmp_path: Path,
) -> None:
    """Product, article, source and kind come from the call, never from the clock."""
    path = one_sheet(tmp_path / "bv.xlsx", [LABELS, (0.5, 0.054), (1.0, 0.136)])
    (series,) = import_workbook(path, imported_at=STAMP, kind=DataKind.GENERATED).series

    assert (series.product, series.article_no) == ("STAD 15", "52 851-015")
    assert series.kind is DataKind.GENERATED
    assert series.source.file == "bv.xlsx"
    assert series.source.sheet == SHEET
    assert series.source.imported_at == STAMP


def test_points_are_sorted_by_x(tmp_path: Path) -> None:
    """The catalogue lists TA-BVS from the top setting down; the series sorts by x."""
    path = one_sheet(tmp_path / "bv.xlsx", [LABELS, (9, 61.2), (8.5, 53.5), (8, 46.0)])
    (series,) = imported(path).series

    assert series.x == (46.0, 53.5, 61.2)
    assert series.y == (8.0, 8.5, 9.0)


def test_decimal_commas_survive_a_whole_sheet(tmp_path: Path) -> None:
    """A sheet exported with decimal commas imports to the same numbers."""
    path = one_sheet(tmp_path / "bv.xlsx", [LABELS, ("0,5", "0,054"), ("1,0", "0,136")])
    (series,) = imported(path).series

    assert series.x == (0.054, 0.136)
    assert series.y == (0.5, 1.0)


def test_trailing_blank_rows_are_slack_not_points(tmp_path: Path) -> None:
    """Padding at the bottom of a sheet is skipped rather than reported."""
    path = one_sheet(
        tmp_path / "bv.xlsx",
        [LABELS, (0.5, 0.054), (1.0, 0.136), (None, None), (None, None)],
    )
    (series,) = imported(path).series

    assert len(series.x) == 2


def test_a_row_missing_one_coordinate_is_a_problem(tmp_path: Path) -> None:
    """Half a point is not a point, and the message names the row."""
    path = one_sheet(tmp_path / "bv.xlsx", [LABELS, (0.5, 0.054), (1.0, None)])
    result = imported(path)

    assert result.series == ()
    assert "row 3" in result.problems[0].message


def test_a_stray_third_column_is_ignored(tmp_path: Path) -> None:
    """A note parked beside the data does not make a healthy sheet a problem."""
    path = one_sheet(
        tmp_path / "bv.xlsx",
        [(*LABELS, "note"), (0.5, 0.054, "checked"), (1.0, 0.136, None)],
    )
    result = imported(path)

    assert result.problems == ()
    assert len(result.series[0].x) == 2


def test_a_sheet_with_only_a_header_is_a_problem(tmp_path: Path) -> None:
    """A sheet with no points is reported, not imported as an empty series."""
    path = one_sheet(tmp_path / "bv.xlsx", [LABELS])
    result = imported(path)

    assert result.series == ()
    assert result.problems[0].sheet == SHEET
    assert "no points" in result.problems[0].message


def test_a_broken_sheet_does_not_stop_its_neighbours(tmp_path: Path) -> None:
    """Failure granularity: the problem is reported against the sheet that has it."""
    path = write_workbook(
        tmp_path / "bv.xlsx",
        {
            "STAD 10 | 52 851-010": [LABELS, (0.5, 0.054), (1.0, 0.136)],
            "no separator here": [LABELS, (0.5, 0.054)],
            "STAD 20 | 52 851-020": [LABELS, (0.5, 0.533), (1.0, 0.6)],
        },
    )
    result = imported(path)

    assert [series.product for series in result.series] == ["STAD 10", "STAD 20"]
    assert [problem.sheet for problem in result.problems] == ["no separator here"]


def test_a_duplicated_x_is_reported_against_its_sheet(tmp_path: Path) -> None:
    """The domain rejects a repeated x; the importer reports it, never a traceback."""
    path = one_sheet(tmp_path / "bv.xlsx", [LABELS, (0.5, 0.054), (1.0, 0.054)])
    result = imported(path)

    assert result.series == ()
    assert "repeats" in result.problems[0].message


def test_one_sheet_can_be_selected_by_name(tmp_path: Path) -> None:
    """Selecting a sheet imports that sheet and leaves the rest unread."""
    path = write_workbook(
        tmp_path / "bv.xlsx",
        {
            "STAD 10 | 52 851-010": [LABELS, (0.5, 0.054), (1.0, 0.136)],
            "STAD 20 | 52 851-020": [LABELS, (0.5, 0.533), (1.0, 0.6)],
        },
    )
    result = imported(path, sheet="STAD 20 | 52 851-020")

    assert [series.product for series in result.series] == ["STAD 20"]


def test_asking_for_a_sheet_that_is_not_there_stops_the_import(tmp_path: Path) -> None:
    """A selector that matches nothing is the caller's error, so it stops the operation."""
    path = one_sheet(tmp_path / "bv.xlsx", [LABELS, (0.5, 0.054)])

    with pytest.raises(HydrofitError, match="no sheet named"):
        imported(path, sheet="STAD 99 | nope")


def test_a_dense_even_grid_reads_as_generated(tmp_path: Path) -> None:
    """701 settings stepped by 0.005 is the shape of a curve someone generated."""
    path = one_sheet(tmp_path / "bv.xlsx", [LABELS, *curve_rows(grid(701))])
    (series,) = imported(path).series

    assert series.kind is DataKind.GENERATED


def test_a_short_table_reads_as_raw(tmp_path: Path) -> None:
    """17 points is a catalogue table, however evenly its settings are spaced."""
    path = one_sheet(tmp_path / "bv.xlsx", [LABELS, *curve_rows(grid(17, step=0.5))])
    (series,) = imported(path).series

    assert series.kind is DataKind.RAW


@pytest.mark.parametrize(
    ("count", "expected"), [(99, DataKind.RAW), (100, DataKind.GENERATED)]
)
def test_the_density_threshold_sits_between_99_and_100(
    tmp_path: Path, count: int, expected: DataKind
) -> None:
    """The boundary is pinned, so a change to it cannot pass unnoticed.

    Args:
        tmp_path: Directory for this test's workbook.
        count: How many points the sheet carries.
        expected: The kind that count should produce.
    """
    path = one_sheet(tmp_path / "bv.xlsx", [LABELS, *curve_rows(grid(count))])
    (series,) = imported(path).series

    assert series.kind is expected


def test_a_dense_but_irregular_series_reads_as_raw(tmp_path: Path) -> None:
    """Density alone is not the test: one broken step makes the grid a table."""
    settings = grid(200)
    settings[120] += 0.002
    path = one_sheet(tmp_path / "bv.xlsx", [LABELS, *curve_rows(settings)])
    (series,) = imported(path).series

    assert series.kind is DataKind.RAW


def test_uneven_kv_does_not_make_a_generated_series_raw(tmp_path: Path) -> None:
    """The uniformity is measured on the setting axis; kv is never evenly spaced.

    This is the assertion that would fail if the classifier ever read column B again — which
    is what the earlier wording of the rule asked for, and what the real catalogue disproves.
    """
    path = one_sheet(tmp_path / "bv.xlsx", [LABELS, *curve_rows(grid(701))])
    (series,) = imported(path).series

    assert not has_uniform_step(series.x)
    assert series.kind is DataKind.GENERATED


def test_settings_listed_downwards_are_still_a_grid() -> None:
    """TA-BVS lists the top setting first; a descending grid is a grid."""
    settings = list(reversed(grid(200)))
    kv = [round(value**2 + 0.05, 10) for value in settings]

    assert has_uniform_step([9.0, 8.5, 8.0, 7.5])
    assert classify_kind(kv, settings) is DataKind.GENERATED


def test_an_even_grid_on_x_reads_as_generated(tmp_path: Path) -> None:
    """Evenness is not tied to an axis: a set stepped on x is generated too.

    This is the case the valve catalogue cannot show, and the one the next instrument family
    will arrive as — there the free variable is what gets turned. A rule pinned to the setting
    axis would read that family backwards, which is why the predicate takes either side.
    """
    path = one_sheet(
        tmp_path / "dp.xlsx", [LABELS, *inverse_curve_rows(grid(200, step=0.25))]
    )
    (series,) = imported(path).series

    assert has_uniform_step(series.x)
    assert not has_uniform_step(series.y)
    assert series.kind is DataKind.GENERATED


@pytest.mark.parametrize("forced", [DataKind.RAW, DataKind.GENERATED])
def test_an_explicit_kind_outranks_the_heuristic(
    tmp_path: Path, forced: DataKind
) -> None:
    """The person who knows the data wins over a rule of thumb about it — both ways.

    Args:
        tmp_path: Directory for this test's workbook.
        forced: The kind the caller demands.
    """
    path = one_sheet(tmp_path / "bv.xlsx", [LABELS, *curve_rows(grid(701))])
    (series,) = import_workbook(path, imported_at=STAMP, kind=forced).series

    assert series.kind is forced


def test_a_missing_file_stops_the_import(tmp_path: Path) -> None:
    """A file-level problem raises rather than returning an empty result."""
    with pytest.raises(HydrofitError, match="no such spreadsheet"):
        imported(tmp_path / "absent.xlsx")


def test_a_file_that_is_not_a_spreadsheet_stops_the_import(tmp_path: Path) -> None:
    """An unreadable file is a message, never a traceback out of openpyxl."""
    path = tmp_path / "bv.xlsx"
    path.write_text("this is not a workbook", encoding="utf-8")

    with pytest.raises(HydrofitError, match="cannot read"):
        imported(path)
