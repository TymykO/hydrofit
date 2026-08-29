"""Reader for the legacy fixture tables under ``tests/data``.

This lives beside the tests and not in :mod:`hydrofit` on purpose: it is an instrument for
checking the package, not something the package offers. Hydrofit reads spreadsheets; these CSV
files are output of the legacy tool it replaces, and nothing but the tests should know their
shape.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from hydrofit.models import AxisSpec, DataKind, Series, SourceRef

DATA = Path(__file__).parent / "data"
EXPECTED_PATH = DATA / "valve_data_aquapresso.csv"

SETTING = AxisSpec("n", "-")
KV = AxisSpec("Kv", "m³/h")

# SourceRef demands a timestamp and the fixtures carry none. Any fixed value serves; a constant
# is what keeps every test that touches these files deterministic.
IMPORTED_AT = "2026-01-01T00:00:00"

# STAD was generated at 701 points, TA-BVS read from the catalogue at 17, so point count alone
# separates the two families here. The threshold repeats the importer's own number rather than
# importing it: a tool that checks the package by borrowing the package's constants stops being
# an independent measurement, and these files keep their shape whatever the importer decides
# later.
GENERATED_FROM = 100


def parse_number(text: str) -> float:
    """Parse one numeric cell.

    Args:
        text: Cell as it stands in the file, possibly with a decimal comma and quotes already
            removed by the CSV reader.

    Returns:
        The value as a float. ``"61,200"`` is 61.2 — a comma is a decimal separator in these
        files, never a grouping mark.
    """
    return float(text.strip().replace(",", "."))


@dataclass(frozen=True, slots=True)
class ExpectedFit:
    """One row of the legacy coefficient table.

    Attributes:
        product: Product name, as the catalogue spells it.
        article_no: Catalogue article number.
        coefficients: ``x6`` down to ``x0``, the power basis in descending order.
        kv_bounds: Lowest and highest Kv the curve was fitted over.
        setting_bounds: Lowest and highest valve setting the curve was fitted over.
    """

    product: str
    article_no: str
    coefficients: tuple[float, ...]
    kv_bounds: tuple[float, float]
    setting_bounds: tuple[float, float]


def point_table_paths() -> list[Path]:
    """List the 14 point tables, sorted, with the coefficient table left out.

    Returns:
        Paths of the per-valve point tables.
    """
    return sorted(path for path in DATA.glob("*.csv") if path != EXPECTED_PATH)


def read_series(path: Path) -> Series:
    """Read one legacy point table into a validated series.

    The first line carries the product and the article number rather than column labels. Every
    following line is one point, and the columns run **setting first, Kv second** — which makes
    the second column x, because the polynomial answers "which setting gives this Kv".

    Seven of the fourteen files run from the highest setting down. They are handed over in file
    order; the ascending order of the result is :class:`~hydrofit.models.Series` sorting its
    points, not this reader doing it.

    Args:
        path: Path of one point table under ``tests/data``.

    Returns:
        The curve as a :class:`~hydrofit.models.Series`.

    Raises:
        HydrofitError: If the points do not satisfy the invariants of a series.
        ValueError: If a cell does not parse as a number.
        IndexError: If a line holds fewer fields than the format requires.
    """
    with path.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.reader(handle) if row]
    product, article_no = rows[0][0].strip(), rows[0][1].strip()
    settings = tuple(parse_number(row[0]) for row in rows[1:])
    kv = tuple(parse_number(row[1]) for row in rows[1:])
    kind = DataKind.GENERATED if len(kv) >= GENERATED_FROM else DataKind.RAW
    return Series(
        product=product,
        article_no=article_no,
        x_axis=KV,
        y_axis=SETTING,
        x=kv,
        y=settings,
        kind=kind,
        # A CSV file has no sheet. An empty name says that; inventing one would put a fact in
        # the catalogue that never existed.
        source=SourceRef(file=path.name, sheet="", imported_at=IMPORTED_AT),
    )


def read_expected() -> dict[tuple[str, str], ExpectedFit]:
    """Read the legacy coefficient table.

    The columns named ``kv_min``/``kv_max`` hold the **setting** range, and those named
    ``setting_min``/``setting_max`` hold the **Kv** range: the names stayed put when the legacy
    tool inverted its axes. This reader corrects the names and leaves the numbers alone, so the
    mistake stops at the file boundary instead of travelling into every test that reads it.

    Returns:
        One entry per row, keyed by product name and article number.
    """
    expected: dict[tuple[str, str], ExpectedFit] = {}
    with EXPECTED_PATH.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            fit = ExpectedFit(
                product=row["name"].strip(),
                article_no=row["product_number"].strip(),
                coefficients=tuple(
                    parse_number(row[f"x{power}"]) for power in range(6, -1, -1)
                ),
                kv_bounds=(
                    parse_number(row["setting_min"]),
                    parse_number(row["setting_max"]),
                ),
                setting_bounds=(
                    parse_number(row["kv_min"]),
                    parse_number(row["kv_max"]),
                ),
            )
            expected[(fit.product, fit.article_no)] = fit
    return expected
