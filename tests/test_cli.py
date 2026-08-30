"""Unit tests for the command line surface.

`main(argv)` is called in process, so these tests read exit codes and streams rather than
spawning a shell. What they mostly guard is the promise that a problem the user can fix arrives
as one line and exit code 1 — never as a traceback, which is a bug report aimed at the wrong
person.
"""

import warnings
from pathlib import Path

import pytest
from openpyxl import Workbook

from hydrofit.cli import main
from hydrofit.models import AxisSpec, DataKind, Series, SourceRef
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


def bumpy_store(root: Path, points: int = 24) -> Path:
    """Write a store holding one series no low-degree polynomial reproduces.

    A parabola is fitted identically by degree 2 and degree 4 — measured at 1.3e-13 apart —
    so a figure comparing those two degrees of it shows one curve drawn twice. Any test that
    means to see the second degree used needs data that disagrees.

    Args:
        root: Directory to build the store in.
        points: How many points the series gets.

    Returns:
        The store directory.
    """
    import math

    x = tuple(1.0 + index * 0.125 for index in range(points))
    SeriesStore(root).save(
        Series(
            product="BUMPY 10",
            article_no="555",
            x_axis=AxisSpec("Kv", "m³/h"),
            y_axis=AxisSpec("n", "-"),
            x=x,
            y=tuple(math.sin(3.0 * value) + 0.5 * value for value in x),
            kind=DataKind.RAW,
            source=SourceRef("built in the test", "", "2026-01-01T00:00:00"),
        )
    )
    return root


def parabola_store(root: Path, points: int = 20) -> Path:
    """Write a store holding one series that lies exactly on y = x^2.

    Built from literal values rather than imported, so nothing here depends on a spreadsheet or
    on which curve the catalogue happens to carry.

    Args:
        root: Directory to build the store in.
        points: How many points the series gets.

    Returns:
        The store directory.
    """
    x = tuple(1.0 + index * 0.5 for index in range(points))
    SeriesStore(root).save(
        Series(
            product="TEST 10",
            article_no="000",
            x_axis=AxisSpec("Kv", "m³/h"),
            y_axis=AxisSpec("n", "-"),
            x=x,
            y=tuple(value**2 for value in x),
            kind=DataKind.RAW,
            source=SourceRef("built in the test", "", "2026-01-01T00:00:00"),
        )
    )
    return root


def test_fit_prints_the_coefficients_and_the_metrics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A degree-2 fit of a parabola recovers it, and says so in three numbers.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store")
    assert main(["fit", "test-10-000", "--degree", "2", "--store", str(store)]) == 0
    out = capsys.readouterr().out
    assert "degree     2" in out
    assert "r squared  1.0" in out
    printed = dict(line.split(maxsplit=1) for line in out.splitlines() if line)
    # The series is y = x^2, so the coefficients are 1, 0, 0 — read against their own labels
    # rather than by position. Descending order is an interface, not a preference: these
    # numbers are pasted into a spreadsheet formula that reads the highest power first, and a
    # reversed tuple would put every value under the wrong name while the report still looked
    # perfectly ordinary.
    assert float(printed["x2"]) == pytest.approx(1.0)
    assert float(printed["x1"]) == pytest.approx(0.0, abs=1e-9)
    assert float(printed["x0"]) == pytest.approx(0.0, abs=1e-9)


def test_fit_says_nothing_about_conditioning_when_the_rank_is_full(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fit the data supports carries no notice.

    A line that appears every time is a line nobody reads, which is exactly how a real warning
    gets missed.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store")
    assert main(["fit", "test-10-000", "--degree", "2", "--store", str(store)]) == 0
    out = capsys.readouterr().out
    # Anchored on something present: without this the assertion below would also hold for a
    # command that printed nothing at all.
    assert "r squared" in out
    assert "conditioning" not in out


def crowded_store(root: Path) -> Path:
    """Write a store whose only series cannot carry a degree-6 fit.

    Seven points spanning 6e-7: ordinary floats, and the Vandermonde matrix over that interval
    is not singular either — its determinant is around 2.5e-140 — but it is indistinguishable
    from singular at the precision a solver works to, and numpy answers with a rank below the
    number of coefficients.

    Args:
        root: Directory to build the store in.

    Returns:
        The store directory.
    """
    SeriesStore(root).save(
        Series(
            product="TIGHT 10",
            article_no="000",
            x_axis=AxisSpec("Kv", "m³/h"),
            y_axis=AxisSpec("n", "-"),
            x=tuple(1.0 + index * 1e-7 for index in range(7)),
            y=(0.1, 0.2, 0.15, 0.3, 0.25, 0.4, 0.35),
            kind=DataKind.RAW,
            source=SourceRef("built in the test", "", "2026-01-01T00:00:00"),
        )
    )
    return root


def test_fit_refuses_a_series_that_is_too_short(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Too few points is one line and exit code 1, never a traceback.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store", points=4)
    assert main(["fit", "test-10-000", "--store", str(store)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.strip().splitlines()) == 1
    assert "at least 7 points" in captured.err


def test_fit_prints_a_residual_for_every_point_on_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--residuals` adds one line per point and nothing else.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store")
    main(["fit", "test-10-000", "--degree", "2", "--residuals", "--store", str(store)])
    listed = capsys.readouterr().out.split("\n\n")[-1].strip().splitlines()
    assert len(listed) == 20


def test_eval_answers_inside_the_data_without_a_marker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Inside the range the answer stands alone.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store")
    assert (
        main(
            ["eval", "test-10-000", "--x", "3", "--degree", "2", "--store", str(store)]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert float(captured.out.strip()) == pytest.approx(9.0)
    assert "extrapolated" not in captured.out
    assert captured.err == ""


def test_eval_marks_the_answer_when_it_comes_from_outside_the_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Outside the range the marker rides in the answer line and the detail goes to stderr.

    Both halves matter and for opposite reasons. Redirecting stdout to a file must not lose the
    caveat, which is why the marker is in the line; and it must not fill a file of numbers with
    prose, which is why the sentence is not. Extrapolating is not an error, so the exit code
    stays 0.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store")
    assert (
        main(
            ["eval", "test-10-000", "--x", "40", "--degree", "2", "--store", str(store)]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.out.strip().endswith("[extrapolated]")
    assert float(captured.out.split()[0]) == pytest.approx(1600.0)
    assert "diverges" in captured.err
    # The answer line is the number and the marker, and nothing else: the range, the units and
    # the sentence belong to the other stream. Asserted on the whole line, because a check
    # against one token can only be true.
    assert len(captured.out.split()) == 2
    assert "10.5" not in captured.out


def test_eval_marks_an_answer_from_below_the_data_too(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Outside is two sides. The data starts at x = 1.0; this asks for 0.25.

    Covering only the upper side would leave `x > high` passing every test in this file while
    silently answering below the data with no marker at all.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store")
    assert (
        main(
            [
                "eval",
                "test-10-000",
                "--x",
                "0.25",
                "--degree",
                "2",
                "--store",
                str(store),
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.out.strip().endswith("[extrapolated]")
    assert "diverges" in captured.err


def test_eval_treats_the_ends_of_the_data_as_inside_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The first and last points are data, not extrapolation.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store")
    for edge in ("1.0", "10.5"):
        main(
            ["eval", "test-10-000", "--x", edge, "--degree", "2", "--store", str(store)]
        )
        captured = capsys.readouterr()
        assert "extrapolated" not in captured.out
        assert captured.err == ""


def test_the_conditioning_line_travels_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A rank-deficient fit says its piece and nothing else says anything.

    numpy raises its own RankWarning for this class of fit when asked for the short form of the
    result; the fitting layer asks for the long one, so the rank arrives as a number and no
    warning is raised at all. Both halves are asserted, and they need different instruments:
    `capsys` sees what is written to the streams and is blind to `warnings.warn`, which pytest
    intercepts before it reaches stderr — measured by planting one, which left an
    stderr-only assertion green.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = crowded_store(tmp_path / "store")
    with warnings.catch_warnings(record=True) as raised:
        warnings.simplefilter("always")
        assert main(["fit", "tight-10-000", "--store", str(store)]) == 0
    captured = capsys.readouterr()
    # The half this test is named for. Without it the silence below would also be reported by a
    # run that had stopped saying anything at all.
    assert "conditioning" in captured.out
    assert [str(entry.message) for entry in raised] == []
    assert captured.err == ""


def test_eval_refuses_an_unknown_series(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unknown slug is one line and exit code 1.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store")
    assert main(["eval", "nope", "--x", "1", "--store", str(store)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.strip().splitlines()) == 1


def test_the_warning_names_the_degree_it_was_asked_for(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The sentence describes the fit that was made, not the default one.

    A hard-coded degree would read correctly on every run that used the default and lie on
    every other, in a detail small enough that nobody would check it.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store")
    main(["eval", "test-10-000", "--x", "40", "--degree", "3", "--store", str(store)])
    assert "degree-3 polynomial" in capsys.readouterr().err


def test_plot_writes_the_png_it_was_asked_for(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The file named by `-o` exists afterwards, carries PNG bytes, and is what gets printed.

    The magic number is checked rather than the size alone: an empty file and a file holding
    an error page both have a size, and neither is a figure.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store")
    target = tmp_path / "out.png"

    assert main(["plot", "test-10-000", "-o", str(target), "--store", str(store)]) == 0

    assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert capsys.readouterr().out.strip() == str(target)


def test_plot_on_an_unknown_series_is_one_line_and_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A slug nobody stored is a problem the user can fix, so it never becomes a traceback.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store")
    target = tmp_path / "out.png"

    assert main(["plot", "nothing-here", "-o", str(target), "--store", str(store)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.strip().splitlines()) == 1
    assert not target.exists()


def test_plot_into_a_missing_directory_is_one_line_and_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A directory that does not exist reaches the user as a sentence, not as an OSError.

    Named for what it covers: "unwritable path" would promise permissions and locked files
    as well, and this test knows only about ENOENT. The other two causes have no test at all.

    matplotlib is several layers below the command the user typed, so its exception names
    things the user never called; the message has to be ours.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store")
    target = tmp_path / "no-such-directory" / "out.png"

    assert main(["plot", "test-10-000", "-o", str(target), "--store", str(store)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.strip().splitlines()) == 1
    assert "cannot write" in captured.err


def test_plot_honours_the_degree_it_is_given(tmp_path: Path) -> None:
    """`--degree` reaches the fit, so two degrees produce two different figures.

    The README says the flag works here exactly as it does for `fit` and `eval`; before this
    test nothing checked that it was passed on at all, and a `plot` that silently ignored it
    would have looked correct in every other assertion.

    Args:
        tmp_path: Working directory for this test.
    """
    store = parabola_store(tmp_path / "store")
    first = tmp_path / "d1.png"
    second = tmp_path / "d2.png"

    assert (
        main(
            [
                "plot",
                "test-10-000",
                "--degree",
                "1",
                "-o",
                str(first),
                "--store",
                str(store),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "plot",
                "test-10-000",
                "--degree",
                "2",
                "-o",
                str(second),
                "--store",
                str(store),
            ]
        )
        == 0
    )

    # A parabola fitted straight is not the parabola fitted as a parabola, so the two drawings
    # differ in content. Comparing the bytes is safe here in a way a golden file is not: both
    # sides were produced by this run, on this machine, seconds apart.
    assert first.read_bytes() != second.read_bytes()


def test_plot_refuses_a_degree_the_series_cannot_carry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Too few points for the degree asked is one line and exit 1, as it is for `fit`.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store", points=4)
    target = tmp_path / "out.png"

    assert (
        main(
            [
                "plot",
                "test-10-000",
                "--degree",
                "8",
                "-o",
                str(target),
                "--store",
                str(store),
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.strip().splitlines()) == 1
    assert "at least 9 points" in captured.err
    assert not target.exists()


def test_plot_refuses_a_format_matplotlib_does_not_know(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An extension matplotlib cannot write is a sentence, not a ValueError traceback.

    Measured before this test existed: `-o out.dat` raised `Format 'dat' is not supported`
    through `main` and printed a traceback naming `backend_bases.py`, a file the user never
    called. The refusal happens before anything is opened, so it is not an OSError and the
    first version of this command let it through.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store")
    target = tmp_path / "out.dat"

    assert main(["plot", "test-10-000", "-o", str(target), "--store", str(store)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.strip().splitlines()) == 1
    assert "cannot write" in captured.err
    # The docstring says the refusal happens before anything is opened; without this the
    # sentence is a claim nobody checks, and an implementation that wrote a few bytes first
    # would pass.
    assert not target.exists()


def vessel_store(root: Path) -> Path:
    """Add a series on different axes to an existing store.

    A pressurisation vessel carries different quantities from a balancing valve, which is the
    case the overlay has to refuse rather than draw.

    Args:
        root: Directory of the store to extend.

    Returns:
        The store directory.
    """
    x = tuple(1.0 + index * 0.5 for index in range(20))
    SeriesStore(root).save(
        Series(
            product="VESSEL 80",
            article_no="111",
            x_axis=AxisSpec("q", "m³/h"),
            y_axis=AxisSpec("Δp", "kPa"),
            x=x,
            y=tuple(value * 3.0 for value in x),
            kind=DataKind.RAW,
            source=SourceRef("built in the test", "", "2026-01-01T00:00:00"),
        )
    )
    return root


def test_plot_compare_degree_writes_a_figure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The *value* of the flag reaches the drawing, not merely the fact that it was given.

    Three figures, and the third is what makes this worth asserting. A run that read the flag
    and ignored its number would still differ from the plain figure, because a legend alone
    changes the bytes — so degree 4 is compared against degree 5, which can differ only if the
    number itself was used.

    Comparing bytes is sound here in a way a stored image is not: every side is produced by
    this run on this machine, and identical figures were measured to give identical bytes.
    What this repository forbids is a golden file compared against a later run.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = bumpy_store(tmp_path / "store")
    plain = tmp_path / "plain.png"
    fourth = tmp_path / "fourth.png"
    fifth = tmp_path / "fifth.png"
    twin = tmp_path / "twin.png"

    args = ["plot", "bumpy-10-555", "--degree", "2", "--store", str(store)]
    assert main([*args, "-o", str(plain)]) == 0
    assert main([*args, "--compare-degree", "4", "-o", str(fourth)]) == 0
    assert main([*args, "--compare-degree", "5", "-o", str(fifth)]) == 0
    assert main([*args, "--compare-degree", "4", "-o", str(twin)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        str(plain),
        str(fourth),
        str(fifth),
        str(twin),
    ]

    assert fourth.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert fourth.read_bytes() != plain.read_bytes()
    assert fourth.read_bytes() != fifth.read_bytes()
    # The premise those two inequalities rest on, asserted rather than assumed: the same
    # request twice writes the same bytes. Without this they would stay green for ever if
    # matplotlib ever began stamping its output, and an inequality that cannot fail is not a
    # test. `splitlines` rather than `split`, because a temporary directory may hold a space.
    assert fourth.read_bytes() == twin.read_bytes()


def test_plot_overlay_writes_a_figure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The overlaid slug reaches the drawing: overlaying one series differs from another.

    The plain figure alone would not settle it — a run that read the flag and drew the first
    series twice would differ from plain by its legend. A second overlay is what pins the
    value rather than the presence of the flag.

    Comparing bytes is sound here in a way a golden file is not: every side is produced by
    this run, on this machine, and identical figures were measured to give identical bytes.
    What this repository forbids is a *stored* image compared against a later one.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store")
    for product, article, slope in (("TEST 20", "222", 1.5), ("TEST 30", "333", 2.5)):
        SeriesStore(store).save(
            Series(
                product=product,
                article_no=article,
                x_axis=AxisSpec("Kv", "m³/h"),
                y_axis=AxisSpec("n", "-"),
                x=tuple(1.0 + index * 0.5 for index in range(20)),
                y=tuple((1.0 + index * 0.5) * slope for index in range(20)),
                kind=DataKind.RAW,
                source=SourceRef("built in the test", "", "2026-01-01T00:00:00"),
            )
        )
    plain = tmp_path / "plain.png"
    with_twenty = tmp_path / "twenty.png"
    with_thirty = tmp_path / "thirty.png"

    args = ["plot", "test-10-000", "--degree", "2", "--store", str(store)]
    assert main([*args, "-o", str(plain)]) == 0
    assert main([*args, "--overlay", "test-20-222", "-o", str(with_twenty)]) == 0
    assert main([*args, "--overlay", "test-30-333", "-o", str(with_thirty)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        str(plain),
        str(with_twenty),
        str(with_thirty),
    ]

    assert with_twenty.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert with_twenty.read_bytes() != plain.read_bytes()
    assert with_twenty.read_bytes() != with_thirty.read_bytes()


def test_plot_overlay_across_different_axes_is_one_line_and_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two units on one axis is refused, and the message names both.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = vessel_store(parabola_store(tmp_path / "store"))
    target = tmp_path / "out.png"

    assert (
        main(
            [
                "plot",
                "test-10-000",
                "--degree",
                "2",
                "--overlay",
                "vessel-80-111",
                "-o",
                str(target),
                "--store",
                str(store),
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.strip().splitlines()) == 1
    assert "Kv [m³/h]" in captured.err
    assert "q [m³/h]" in captured.err
    assert not target.exists()


def test_plot_refuses_both_comparison_flags_at_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The two flags answer different questions, so asking both is refused before drawing.

    argparse itself enforces the exclusion, which means exit code 2 rather than 1 — the code
    it uses for a command line it could not parse, as opposed to one it parsed and could not
    carry out.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    target = tmp_path / "out.png"

    with pytest.raises(SystemExit) as exit_code:
        main(
            [
                "plot",
                "test-10-000",
                "--compare-degree",
                "4",
                "--overlay",
                "test-10-000",
                "-o",
                str(target),
            ]
        )

    # Exit 2 already proves nothing was drawn: argparse leaves before any code in this package
    # runs, so `not target.exists()` could never be red here while this line is green. No store
    # is built for the same reason — the refusal happens before one would be read.
    assert exit_code.value.code == 2
    # Both names, not one: the usage line of this subcommand mentions every flag it accepts, so
    # a single name would also be present after an unknown-argument failure and the assertion
    # would hold for a parser that never registered the exclusion at all. On names rather than
    # on argparse's wording, because its messages go through gettext and a translation
    # catalogue on the machine would redden this for a reason that is not the code.
    message = capsys.readouterr().err
    assert "--overlay" in message
    assert "--compare-degree" in message


def test_plot_refuses_a_series_compared_with_itself(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One request twice is not a comparison, and it is refused rather than drawn.

    Reachable from the command line in two ways, both covered here: the same degree given to
    `--compare-degree`, and the plotted slug given to `--overlay`.

    Args:
        tmp_path: Working directory for this test.
        capsys: Captured streams.
    """
    store = parabola_store(tmp_path / "store")
    target = tmp_path / "out.png"
    base = ["plot", "test-10-000", "--degree", "2", "--store", str(store)]

    for flag, value in (("--compare-degree", "2"), ("--overlay", "test-10-000")):
        assert main([*base, flag, value, "-o", str(target)]) == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert len(captured.err.strip().splitlines()) == 1
        assert "one request twice" in captured.err
        assert not target.exists()
