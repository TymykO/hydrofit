"""Inventory of the legacy fixtures.

These tests check the oracle rather than the tool: fourteen point tables, fourteen coefficient
rows, each pair describing the same curve, before any fitting code is asserted against them. An
oracle nobody checks is an assumption with a filename.

The one piece of the package they do lean on is `Series`, which every fixture is read through —
so its validation and its sorting are underneath these assertions, and a failure here can also
be a failure there.
"""

import csv
from pathlib import Path

import numpy as np
import pytest

from hydrofit.models import DataKind
from legacy_data import (
    parse_number,
    point_table_paths,
    read_expected,
    read_series,
)

PATHS = point_table_paths()
# Each file gets its own test, so a failure names the valve instead of a count.
IDS = [path.stem for path in PATHS]


def test_fourteen_point_tables() -> None:
    """The fixture set holds one point table per valve size."""
    assert len(PATHS) == 14


def test_fourteen_expected_rows() -> None:
    """The coefficient table holds one row per point table."""
    assert len(read_expected()) == 14


def test_the_two_files_cover_the_same_valves() -> None:
    """Point tables and coefficient rows describe the same set of valves.

    Compared as sets rather than counts, so a fixture that goes missing is reported by name.
    A count says only that something is wrong; the name says which valve to go and look for.
    """
    from_tables = {
        (series.product, series.article_no) for series in map(read_series, PATHS)
    }
    assert from_tables == set(read_expected())


@pytest.mark.parametrize("path", PATHS, ids=IDS)
def test_the_reader_keeps_every_point_together(path: Path) -> None:
    """Reordering must not shuffle an x away from its own y.

    Seven of the fourteen files are written from the highest setting down, so the points really
    are reordered on the way in. The file is read a second time here, by hand: comparing the
    series against itself would prove nothing about the pairing.
    """
    with path.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.reader(handle) if row][1:]
    from_file = {(parse_number(row[1]), parse_number(row[0])) for row in rows}
    series = read_series(path)
    assert set(zip(series.x, series.y, strict=True)) == from_file


@pytest.mark.parametrize("path", PATHS, ids=IDS)
def test_ranges_agree_with_the_coefficient_table(path: Path) -> None:
    """The two files describe the same curve, measured on their shared bounds.

    This is the assertion that earns the inventory test: it compares two files written by
    different steps of the legacy tool, and it is what exposed that the bound columns carry
    swapped names.
    """
    series = read_series(path)
    fit = read_expected()[(series.product, series.article_no)]
    assert (min(series.x), max(series.x)) == fit.kv_bounds
    assert (min(series.y), max(series.y)) == fit.setting_bounds


@pytest.mark.parametrize("path", PATHS, ids=IDS)
def test_series_is_long_enough_to_fit_degree_six(path: Path) -> None:
    """Every curve carries at least the `degree + 1` points a degree-6 fit needs."""
    series = read_series(path)
    assert len(series.x) >= 7


def test_the_two_families_differ_in_shape() -> None:
    """Seven dense curves and seven sparse ones, which is what the reader labels.

    The files carry no such label; 701 points against 17 is the fact, and `GENERATED_FROM` is
    where this reader turns that fact into a `DataKind`.
    """
    kinds = [read_series(path).kind for path in PATHS]
    assert kinds.count(DataKind.GENERATED) == 7
    assert kinds.count(DataKind.RAW) == 7


def test_decimal_comma_is_a_decimal_separator() -> None:
    """A quoted comma in the TA-BVS tables separates decimals, never thousands."""
    assert parse_number("61,200") == 61.2


def test_decimal_comma_survives_into_the_series() -> None:
    """The largest Kv of TA-BVS DN65 is 61.2 m³/h, not 61200."""
    series = next(read_series(p) for p in PATHS if p.stem == "TA-BVS_DN65")
    assert max(series.x) == 61.2


@pytest.mark.parametrize("path", PATHS, ids=IDS)
def test_the_curve_runs_from_kv_to_setting(path: Path) -> None:
    """The published curve turns Kv into a setting, and not the reverse.

    Everything downstream rests on this orientation. Measured across the fourteen valves, on
    the worst point of each: read the right way round, the published coefficients reproduce the
    settings to within 0.27; read backwards, the error is never smaller than 2.2, and the
    tightest ratio between the two worst-point errors is 46. The bounds below sit well inside
    those margins and are scale-free, because Kv spans 1.36 on a DN10 and 1170 on a DN250.
    """
    series = read_series(path)
    coefficients = read_expected()[(series.product, series.article_no)].coefficients
    as_read = float(np.max(np.abs(np.polyval(coefficients, series.x) - series.y)))
    backwards = float(np.max(np.abs(np.polyval(coefficients, series.y) - series.x)))
    assert as_read < 0.5
    assert backwards > 10 * as_read


def test_the_known_bad_point_in_dn200_is_still_there() -> None:
    """TA-BVS DN200 gives 20.2 m³/h at a setting of 1.5, and has to keep giving it.

    The value is wrong — it is the one DN150 carries at that setting — but the published
    coefficients were fitted through it. Correcting it would turn the parity assertion red for
    a reason nobody would find from the failure. This test is the guard that stops the cleanup.
    """
    series = next(read_series(path) for path in PATHS if path.stem == "TA-BVS_DN200")
    assert (20.2, 1.5) in set(zip(series.x, series.y, strict=True))
