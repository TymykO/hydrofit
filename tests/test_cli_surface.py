"""Surface tests: the whole of what a command prints, compared against a file.

The unit tests in `test_cli.py` ask whether particular facts appear in the output. These ask a
different question — whether the output is *exactly* what it was — and that is the one that
catches a column silently renamed, a field dropped, a unit rendered without its brackets, or a
row order that quietly stopped being sorted. A test that only looks for substrings cannot see
any of those, because they all leave the substrings intact.

The store is built here from literal values rather than read from a spreadsheet, so nothing in
these files depends on openpyxl, on a clock, or on where the test happened to run.
"""

from pathlib import Path

import pytest

from hydrofit.cli import main
from hydrofit.models import AxisSpec, DataKind, Series, SourceRef
from hydrofit.store import SeriesStore

REFERENCE = Path(__file__).parent / "reference"

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


@pytest.mark.parametrize(
    ("name", "argv"),
    [
        ("list.txt", ["list"]),
        ("list-product.txt", ["list", "--product", "ta-bvs"]),
        ("show.txt", ["show", "stad-10-52-851-010"]),
        ("show-points.txt", ["show", "stad-10-52-851-010", "--points"]),
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
    assert printed == (REFERENCE / name).read_text(encoding="utf-8")


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
