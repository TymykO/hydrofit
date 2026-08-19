"""Unit tests for the command line surface.

`main(argv)` is called in process, so these tests read exit codes and streams rather than
spawning a shell. What they mostly guard is the promise that a problem the user can fix arrives
as one line and exit code 1 — never as a traceback, which is a bug report aimed at the wrong
person.
"""

from pathlib import Path

import pytest
from openpyxl import Workbook

from hydrofit.cli import main
from hydrofit.models import DataKind
from hydrofit.store import SeriesStore

LABELS = ("n [-]", "Kv [m³/h]")


def workbook(path: Path, sheets: dict[str, list[tuple[object, ...]]]) -> Path:
    """Write a workbook from literal cell values.

    Args:
        path: Where to write the file.
        sheets: Sheet name to its rows.

    Returns:
        The path written.
    """
    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(title=name)
        for row in rows:
            sheet.append(list(row))
    book.save(path)
    return path


def good_sheet(
    product: str = "STAD 15 | 52 851-015",
) -> dict[str, list[tuple[object, ...]]]:
    """One healthy sheet, small enough to classify as raw.

    Args:
        product: Sheet name in the catalogue convention.

    Returns:
        A sheet mapping ready for `workbook`.
    """
    return {product: [LABELS, (0.5, 0.054), (1.0, 0.136), (1.5, 0.533)]}


def test_import_stores_the_series(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A healthy workbook lands in the store and is reported.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    path = workbook(tmp_path / "bv.xlsx", good_sheet())
    store = tmp_path / "store"

    code = main(["import", str(path), "--store", str(store)])
    out = capsys.readouterr().out

    assert code == 0
    assert "imported 1 series from bv.xlsx" in out
    assert SeriesStore(store).list_series()[0].product == "STAD 15"


def test_import_reads_the_clock_at_this_edge(tmp_path: Path) -> None:
    """The timestamp is stamped by the CLI — nothing below it knows what time it is.

    Args:
        tmp_path: Working directory for this test.
    """
    path = workbook(tmp_path / "bv.xlsx", good_sheet())
    store = tmp_path / "store"

    main(["import", str(path), "--store", str(store)])
    (series,) = SeriesStore(store).list_series()

    assert series.source.imported_at.startswith("20")


def test_import_can_force_the_kind(tmp_path: Path) -> None:
    """`--kind` outranks the classification, which would call this sheet raw.

    Args:
        tmp_path: Working directory for this test.
    """
    path = workbook(tmp_path / "bv.xlsx", good_sheet())
    store = tmp_path / "store"

    main(["import", str(path), "--store", str(store), "--kind", "generated"])

    assert SeriesStore(store).list_series()[0].kind is DataKind.GENERATED


def test_a_broken_sheet_warns_but_the_rest_still_lands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sheet-level failure granularity, visible at the surface.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    sheets = good_sheet()
    sheets["no separator"] = [LABELS, (0.5, 0.054)]
    path = workbook(tmp_path / "bv.xlsx", sheets)

    code = main(["import", str(path), "--store", str(tmp_path / "store")])
    captured = capsys.readouterr()

    assert code == 0
    assert "warning: no separator:" in captured.err
    assert "skipped 1 sheet(s)" in captured.out


def test_a_workbook_that_yields_nothing_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Asking for an import and receiving no series is a failed operation.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    path = workbook(tmp_path / "bv.xlsx", {"no separator": [LABELS, (0.5, 0.054)]})

    code = main(["import", str(path), "--store", str(tmp_path / "store")])

    assert code == 1
    assert "warning:" in capsys.readouterr().err


def test_a_missing_file_is_one_message_and_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An input error reaches the user as a message, never as a traceback.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    code = main(["import", str(tmp_path / "absent.xlsx"), "--store", str(tmp_path)])
    captured = capsys.readouterr()

    assert code == 1
    assert captured.err.startswith("error: no such spreadsheet")
    assert captured.err.count("\n") == 1
    assert "Traceback" not in captured.err


def test_show_of_an_unknown_slug_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A slug that is not in the store is the user's mistake, reported as one.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    code = main(["show", "nope", "--store", str(tmp_path / "store")])

    assert code == 1
    assert capsys.readouterr().err.startswith("error: ")


def test_show_prints_axes_through_their_labels(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The brackets come from the model, so they are in the output.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    path = workbook(tmp_path / "bv.xlsx", good_sheet())
    store = str(tmp_path / "store")
    main(["import", str(path), "--store", store])
    capsys.readouterr()

    code = main(["show", "stad-15-52-851-015", "--store", store])
    out = capsys.readouterr().out

    assert code == 0
    assert "n [-]" in out
    assert "Kv [m³/h]" in out


def test_show_points_prints_every_pair(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--points` appends the pairs, written as reprs so nothing is rounded away.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    path = workbook(tmp_path / "bv.xlsx", good_sheet())
    store = str(tmp_path / "store")
    main(["import", str(path), "--store", store])
    capsys.readouterr()

    main(["show", "stad-15-52-851-015", "--store", store, "--points"])
    out = capsys.readouterr().out

    assert out.splitlines()[-3:] == ["  0.054,0.5", "  0.136,1.0", "  0.533,1.5"]


def test_list_of_an_empty_store_is_not_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nothing stored is an answer, not a failure.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    code = main(["list", "--store", str(tmp_path / "store")])

    assert code == 0
    assert capsys.readouterr().out == "no series match\n"


def test_list_filters_by_product_substring(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The product filter matches part of the name, ignoring case.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    sheets = good_sheet()
    sheets.update(good_sheet("TA-BVS 243 DN65 | 6-52 240-065"))
    path = workbook(tmp_path / "bv.xlsx", sheets)
    store = str(tmp_path / "store")
    main(["import", str(path), "--store", store])
    capsys.readouterr()

    main(["list", "--store", store, "--product", "stad"])
    out = capsys.readouterr().out

    assert "1 series" in out
    assert "TA-BVS" not in out


def test_the_product_help_explains_substring_matching(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The help text says so verbatim, or the behaviour looks like a bug.

    Whitespace is collapsed before the comparison: argparse wraps help text to the terminal
    width, so the sentence arrives split across lines. That is presentation, not content — but
    a naive substring check would pass or fail depending on how wide the window happened to be.

    Args:
        capsys: Captured streams.
    """
    with pytest.raises(SystemExit):
        main(["list", "--help"])
    printed = " ".join(capsys.readouterr().out.split())

    assert "matches any part of the product name, case-insensitive" in printed


def test_the_import_help_states_that_no_product_is_assumed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The axis convention is the one thing a user must get right, so it is on the screen.

    Args:
        capsys: Captured streams.
    """
    with pytest.raises(SystemExit):
        main(["import", "--help"])
    printed = " ".join(capsys.readouterr().out.split())

    assert "hydrofit knows no products" in printed
    assert "column A, the y axis: the computed quantity" in printed
    assert "column B, the x axis: the free variable" in printed
    assert "n [-] over Kv [m³/h]" in printed
    assert "Δp [kPa] over q [m³/h]" in printed


def test_help_survives_a_console_that_cannot_render_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--help` is printed from inside the parser, so the guard has to reach that far.

    The import help carries `³` and `Δ`. A legacy code page turns that into an encoder error,
    and the help screen is exactly where a stuck user goes first — so it gets the same one-line
    answer as every other command, never a traceback.

    Args:
        monkeypatch: Used to make printing fail the way a legacy console does.
        capsys: Captured streams.
    """

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise UnicodeEncodeError("charmap", "Δ", 0, 1, "character maps to <undefined>")

    monkeypatch.setattr("argparse.ArgumentParser.print_help", refuse)

    assert main(["import", "--help"]) == 1
    assert "set PYTHONIOENCODING=utf-8" in capsys.readouterr().err
