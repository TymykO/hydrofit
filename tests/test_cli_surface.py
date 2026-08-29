"""Surface tests: the whole of what a command prints, compared against a file.

The unit tests in `test_cli.py` ask whether particular facts appear in the output. These ask a
different question — whether the output is *exactly* what it was — and that is the one that
catches a column silently renamed, a field dropped, a unit rendered without its brackets, or a
row order that quietly stopped being sorted. A test that only looks for substrings cannot see
any of those, because they all leave the substrings intact.

The store is built here from literal values rather than read from a spreadsheet, so nothing in
these files depends on openpyxl, on a clock, or on where the test happened to run.
"""

import re
from pathlib import Path

import pytest

from hydrofit.cli import main
from hydrofit.models import AxisSpec, DataKind, Series, SourceRef
from hydrofit.store import SeriesStore

REFERENCE = Path(__file__).parent / "reference"

# Reference files whose numbers a machine computes instead of storing. Their last digits do not
# travel: one commit, one numpy version and one operating system produced different ones on two
# CI runs minutes apart, because numpy picks a vectorised path from the processor it finds. What
# is pinned for these is everything except the digits.
COMPUTED = frozenset(
    {
        "fit.txt",
        "fit-residuals.txt",
        "eval.txt",
        "eval-outside.txt",
        "eval-outside-stderr.txt",
    }
)

# Both tolerances are measured rather than chosen, and they answer different problems.
#
# The relative one covers values that are answers: the widest spread observed between two runs
# was 3.5e-15, on the extrapolated -212.33. At 1e-12 there are three orders of margin, and a
# change that mattered would be far larger — the scattered-data tests move a point by 0.5.
#
# The absolute one exists because near zero the relative bound cannot work: one residual went
# from +4.4e-16 to -6.7e-16 between the same two runs, a change of sign. Its scale comes from
# the data rather than from the noise: y runs to 1.5 in this store, where one ulp is 2.2e-16, so
# 1e-12 is some four thousand ulps — nine hundred times the 1.1e-15 that was actually seen, and
# still far below any residual that would mean the fit itself had moved.
NUMBER_RELATIVE = 1e-12
NUMBER_ABSOLUTE = 1e-12

_NUMBER = re.compile(r"-?\d+\.\d+(?:e[+-]\d+)?|-?\d+e[+-]\d+")


def assert_matches(printed: str, expected: str, computed: bool) -> None:
    """Compare output against its reference file.

    Args:
        printed: What the command wrote.
        expected: What the reference file holds.
        computed: Whether the numbers in this output are computed. When they are, they are
            compared as numbers and everything around them byte for byte; when they are not —
            when they come from the store, as in `list` and `show` — the whole text is compared
            byte for byte, because there is nothing in it a machine could round differently.
    """
    if not computed:
        assert printed == expected
        return
    # The skeleton keeps every column name, every field in its order, the width each value
    # starts at, and markers such as [extrapolated]. Only the digits are set aside.
    assert _NUMBER.sub("<number>", printed) == _NUMBER.sub("<number>", expected)
    assert [
        float(match.group()) for match in _NUMBER.finditer(printed)
    ] == pytest.approx(
        [float(match.group()) for match in _NUMBER.finditer(expected)],
        rel=NUMBER_RELATIVE,
        abs=NUMBER_ABSOLUTE,
    )


KV = AxisSpec("Kv", "m³/h")
OPENING = AxisSpec("n", "-")


def build_store(root: Path) -> Path:
    """Write a fixed two-series store.

    Both families of the real catalogue are represented, so the reference output shows a
    generated series beside a raw one and the sort order has something to sort.

    Args:
        root: Directory to build the store in.

    Returns:
        The store directory.
    """
    store = SeriesStore(root)
    store.save(
        Series(
            product="STAD 10",
            article_no="52 851-010",
            x_axis=KV,
            y_axis=OPENING,
            x=(0.054, 0.136, 0.533),
            y=(0.5, 1.0, 1.5),
            kind=DataKind.GENERATED,
            source=SourceRef(
                "BV - IMI.xlsx", "STAD 10 | 52 851-010", "2026-08-19T10:00:00+00:00"
            ),
        )
    )
    store.save(
        Series(
            product="TA-BVS 243 DN65",
            article_no="6-52 240-065",
            x_axis=KV,
            y_axis=OPENING,
            x=(2.52, 61.2),
            y=(1.0, 9.0),
            kind=DataKind.RAW,
            source=SourceRef(
                "BV - IMI.xlsx",
                "TA-BVS 243 DN65 | 6-52 240-065",
                "2026-08-19T10:00:00+00:00",
            ),
        )
    )
    return root


def crowded_store(root: Path) -> Path:
    """Write a store whose only series cannot carry a degree-6 fit.

    Seven points spanning 6e-7, a step of 1e-7 apart: ordinary floats, but the Vandermonde
    matrix over so narrow an interval is singular to any precision a solver can work in — its
    determinant is around 2.5e-140 — and numpy reports that by returning a rank below the number
    of coefficients.

    Args:
        root: Directory to build the store in.

    Returns:
        The store directory.
    """
    SeriesStore(root).save(
        Series(
            product="TIGHT 10",
            article_no="000",
            x_axis=KV,
            y_axis=OPENING,
            x=tuple(1.0 + index * 1e-7 for index in range(7)),
            y=(0.1, 0.2, 0.15, 0.3, 0.25, 0.4, 0.35),
            kind=DataKind.RAW,
            source=SourceRef("built in the test", "", "2026-01-01T00:00:00"),
        )
    )
    return root


def test_the_conditioning_report_keeps_its_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The report a warned-about fit produces, checked by shape and not by digits.

    Every other case in this file is pinned byte for byte, and this one deliberately is not.
    These coefficients are the minimum-norm solution of a system that is singular at working
    precision, and that solution is not unique: an SVD selects one, and what LAPACK does when
    singular values tie is unspecified.
    Two builds agreeing would show that they agree, not that the digits are portable, so
    pinning them would pin an accident of one machine.

    What is deterministic is the shape, and the shape is what the notice changes: `conditioning`
    is the longest label in the report, so every field above it shifts into a wider column. That
    reflow arrives exactly when the numbers deserve least trust.

    Args:
        tmp_path: Directory for this test's store.
        capsys: Captured streams.
    """
    store = crowded_store(tmp_path / "store")

    code = main(["fit", "tight-10-000", "--store", str(store)])

    assert code == 0
    lines = capsys.readouterr().out.splitlines()
    labels = [line.split("  ")[0] for line in lines]
    assert labels == [
        "series",
        "degree",
        *(f"x{power}" for power in range(6, -1, -1)),
        "r squared",
        "max error",
        "rmse",
        "conditioning",
    ]
    assert lines[-1].endswith(
        "rank 3 of the 7 coefficients a degree-6 fit needs: the data does not support it"
    )
    # Every value starts where the longest label ends, the notice included.
    column = len("conditioning") + 2
    assert all(line[column - 1] == " " and line[column] != " " for line in lines)
    # An order of magnitude rather than a value: what makes this report worth a warning is that
    # the coefficients are enormous for a curve whose y runs from 0.1 to 0.4.
    coefficients = [float(line.split()[1]) for line in lines[2:9]]
    assert max(abs(value) for value in coefficients) > 1e6


@pytest.mark.parametrize(
    ("name", "argv"),
    [
        ("list.txt", ["list"]),
        ("list-product.txt", ["list", "--product", "ta-bvs"]),
        ("show.txt", ["show", "stad-10-52-851-010"]),
        ("show-points.txt", ["show", "stad-10-52-851-010", "--points"]),
        # Degree 2, because the pinned store holds three points: enough for degree + 1 and no
        # more. The real curves are fitted at 6, and what is pinned here is the shape of the
        # report rather than the arithmetic, which the reference tests measure on real data.
        ("fit.txt", ["fit", "stad-10-52-851-010", "--degree", "2"]),
        (
            "fit-residuals.txt",
            ["fit", "stad-10-52-851-010", "--degree", "2", "--residuals"],
        ),
        ("eval.txt", ["eval", "stad-10-52-851-010", "--degree", "2", "--x", "0.2"]),
        (
            "eval-outside.txt",
            ["eval", "stad-10-52-851-010", "--degree", "2", "--x", "5"],
        ),
    ],
)
def test_output_matches_its_reference(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    name: str,
    argv: list[str],
) -> None:
    """Whole stdout equals the reference file, byte for byte.

    Args:
        tmp_path: Directory for this test's store.
        capsys: Captured streams.
        name: Reference file to compare against.
        argv: Command to run, without the store option.
    """
    store = build_store(tmp_path / "store")

    code = main([*argv, "--store", str(store)])
    printed = capsys.readouterr().out

    assert code == 0
    assert_matches(
        printed, (REFERENCE / name).read_text(encoding="utf-8"), name in COMPUTED
    )


def test_the_reference_output_shows_units_in_brackets() -> None:
    """The rendered labels are in the pinned output, not merely producible on request.

    This is the assertion that fails if any output path ever prints `unit` while bypassing
    `label` — the brackets belong to the model, and nothing downstream may assemble them.
    """
    shown = (REFERENCE / "show.txt").read_text(encoding="utf-8")

    assert "Kv [m³/h]" in shown
    assert "n [-]" in shown


def test_reference_files_are_stored_with_lf() -> None:
    """A stray CR would fail these tests on a Windows checkout for no reason of its own.

    `.gitattributes` pins `tests/reference/**` to LF; this checks the files on disk actually
    carry it, because the pin only helps if it was in place before the files were written.
    """
    for path in sorted(REFERENCE.glob("*.txt")):
        assert b"\r" not in path.read_bytes(), path.name


def test_the_extrapolation_detail_matches_its_reference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The sentence on stderr is pinned too, not only the marked answer on stdout.

    Both halves of that split are a surface a user reads, and a warning silently reworded is
    exactly the change these tests exist to catch. The marker rides in the answer; the sentence
    explains it; neither is allowed to drift unnoticed.

    Args:
        tmp_path: Directory for this test's store.
        capsys: Captured streams.
    """
    store = build_store(tmp_path / "store")

    code = main(
        [
            "eval",
            "stad-10-52-851-010",
            "--degree",
            "2",
            "--x",
            "5",
            "--store",
            str(store),
        ]
    )

    assert code == 0
    assert_matches(
        capsys.readouterr().err,
        (REFERENCE / "eval-outside-stderr.txt").read_text(encoding="utf-8"),
        computed=True,
    )


def test_every_non_ascii_character_in_the_references_comes_from_a_unit() -> None:
    """Nothing decorative may reach a console that cannot render it.

    The rule is not "avoid non-ASCII" — the data carries a cubic metre sign and must keep it.
    The rule is that hydrofit adds none of its own, and the set below is pinned rather than
    derived: a fixture introducing a second unit is supposed to fail here and be added
    deliberately. What this covers is the pinned output; argparse's own screens are not in it.
    """
    found = {
        character
        for path in REFERENCE.glob("*.txt")
        for character in path.read_text(encoding="utf-8")
        if ord(character) > 127
    }
    assert found == {"³"}
