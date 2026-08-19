"""Local store: a JSON catalogue of metadata beside one CSV of points per series.

Numbers are written with `repr`, never with a fixed-precision format. In CPython the repr of a
float is the shortest text that parses back to the identical value, so a stored series is the
series that was saved — bit for bit. Rounding here would look harmless and would surface much
later, far from its cause, as fits that no longer match the legacy coefficients at `rtol=1e-9`.

The catalogue duplicates the ranges that the CSV already implies. That duplication is not a
second source of truth: `load` recomputes the ranges from the points and refuses a catalogue
that disagrees with them.
"""

import csv
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from hydrofit.errors import HydrofitError
from hydrofit.models import AxisSpec, DataKind, Series, SourceRef

_CATALOG_NAME = "catalog.json"
_SERIES_DIRNAME = "series"
_HEADER = ("x", "y")


def _as_mapping(value: object, what: str) -> Mapping[str, object]:
    """Narrow a value decoded from JSON to a mapping.

    Args:
        value: The decoded value.
        what: How to name it in an error message.

    Returns:
        The value as a mapping. JSON object keys are always strings, which is what the cast
        records — there is nothing to check at runtime.

    Raises:
        HydrofitError: If the value is not a JSON object.
    """
    if not isinstance(value, dict):
        raise HydrofitError(f"{what} is not a JSON object")
    return cast(Mapping[str, object], value)


def _text(entry: Mapping[str, object], key: str, what: str) -> str:
    """Read a required text field.

    Args:
        entry: The mapping to read from.
        key: Field name.
        what: How to name the mapping in an error message.

    Returns:
        The field value.

    Raises:
        HydrofitError: If the field is absent or is not text.
    """
    value = entry.get(key)
    if not isinstance(value, str):
        raise HydrofitError(f"{what} has no text field {key!r}")
    return value


def _axis(entry: Mapping[str, object], key: str, what: str) -> AxisSpec:
    """Read an axis specification.

    Args:
        entry: The mapping to read from.
        key: Field name.
        what: How to name the mapping in an error message.

    Returns:
        The axis specification.

    Raises:
        HydrofitError: If the field is absent or incomplete.
    """
    axis = _as_mapping(entry.get(key), f"{what} field {key!r}")
    return AxisSpec(
        name=_text(axis, "name", f"{what} field {key!r}"),
        unit=_text(axis, "unit", f"{what} field {key!r}"),
    )


def _range(entry: Mapping[str, object], key: str, what: str) -> tuple[float, float]:
    """Read a two-number range.

    Args:
        entry: The mapping to read from.
        key: Field name.
        what: How to name the mapping in an error message.

    Returns:
        The range as a pair of floats.

    Raises:
        HydrofitError: If the field is absent, is not a pair, or holds something other than
            numbers.
    """
    value = entry.get(key)
    if not isinstance(value, list) or len(value) != 2:
        raise HydrofitError(f"{what} has no two-number field {key!r}")
    low, high = cast(list[object], value)
    if isinstance(low, bool) or isinstance(high, bool):
        raise HydrofitError(f"{what} has a non-numeric {key!r}")
    if not isinstance(low, int | float) or not isinstance(high, int | float):
        raise HydrofitError(f"{what} has a non-numeric {key!r}")
    return float(low), float(high)


def _entry_for(series: Series) -> dict[str, object]:
    """Build the catalogue record of a series.

    Args:
        series: The series to describe.

    Returns:
        A JSON-ready mapping of its metadata and ranges.
    """
    return {
        "product": series.product,
        "article_no": series.article_no,
        "x_axis": {"name": series.x_axis.name, "unit": series.x_axis.unit},
        "y_axis": {"name": series.y_axis.name, "unit": series.y_axis.unit},
        "kind": str(series.kind),
        "source": {
            "file": series.source.file,
            "sheet": series.source.sheet,
            "imported_at": series.source.imported_at,
        },
        "x_range": list(series.x_range()),
        "y_range": list(series.y_range()),
    }


class SeriesStore:
    """A directory holding `catalog.json` and one CSV per series.

    The store is created lazily: nothing is written to disk until the first `save`.
    """

    def __init__(self, root: Path) -> None:
        """Point the store at a directory.

        Args:
            root: Directory that holds, or will hold, the catalogue and the series files.
        """
        self.root = root

    @property
    def catalog_path(self) -> Path:
        """Path of the catalogue file."""
        return self.root / _CATALOG_NAME

    def points_path(self, slug: str) -> Path:
        """Path of the CSV holding the points of one series.

        Args:
            slug: Series identifier.

        Returns:
            Path of the points file, whether or not it exists.
        """
        return self.root / _SERIES_DIRNAME / f"{slug}.csv"

    def save(self, series: Series) -> None:
        """Write a series to the store, replacing an earlier version of the same series.

        Args:
            series: The series to store.

        Raises:
            HydrofitError: If the slug already belongs to a different product or article
                number — silently overwriting there would lose a series.
        """
        catalog = self._read_catalog()
        existing = catalog.get(series.slug)
        if existing is not None:
            entry = _as_mapping(existing, f"catalogue entry {series.slug!r}")
            what = f"catalogue entry {series.slug!r}"
            stored = (_text(entry, "product", what), _text(entry, "article_no", what))
            if stored != (series.product, series.article_no):
                raise HydrofitError(
                    f"slug {series.slug!r} already belongs to {stored[0]!r} "
                    f"({stored[1]!r}) and cannot also name {series.product!r} "
                    f"({series.article_no!r})"
                )

        # Points first: a points file with no catalogue entry is recoverable, a catalogue entry
        # with no points is a store that lies about what it holds.
        self._write_points(series)
        catalog[series.slug] = _entry_for(series)
        self._write_catalog(catalog)

    def load(self, slug: str) -> Series:
        """Read one series back from the store.

        Args:
            slug: Series identifier, as listed in the catalogue.

        Returns:
            The stored series, with its points in the order they were saved.

        Raises:
            HydrofitError: If the slug is unknown, the catalogue is malformed, the points file
                is missing or unreadable, or the catalogue ranges disagree with the points.
        """
        catalog = self._read_catalog()
        record = catalog.get(slug)
        if record is None:
            raise HydrofitError(f"no series named {slug!r} in {self.catalog_path}")

        what = f"catalogue entry {slug!r}"
        entry = _as_mapping(record, what)
        source = _as_mapping(entry.get("source"), f"{what} field 'source'")
        kind_text = _text(entry, "kind", what)
        try:
            kind = DataKind(kind_text)
        except ValueError as exc:
            raise HydrofitError(f"{what} has an unknown kind {kind_text!r}") from exc

        x, y = self._read_points(slug)
        series = Series(
            product=_text(entry, "product", what),
            article_no=_text(entry, "article_no", what),
            x_axis=_axis(entry, "x_axis", what),
            y_axis=_axis(entry, "y_axis", what),
            x=x,
            y=y,
            kind=kind,
            source=SourceRef(
                file=_text(source, "file", f"{what} field 'source'"),
                sheet=_text(source, "sheet", f"{what} field 'source'"),
                imported_at=_text(source, "imported_at", f"{what} field 'source'"),
            ),
        )

        for axis, stored, computed in (
            ("x", _range(entry, "x_range", what), series.x_range()),
            ("y", _range(entry, "y_range", what), series.y_range()),
        ):
            if stored != computed:
                raise HydrofitError(
                    f"{what} claims {axis} runs {stored[0]!r}..{stored[1]!r} but the points "
                    f"run {computed[0]!r}..{computed[1]!r}"
                )
        return series

    def list_series(self) -> list[Series]:
        """Read every series in the store.

        Returns:
            All stored series, ordered by slug.

        Raises:
            HydrofitError: If any entry cannot be read.
        """
        return [self.load(slug) for slug in sorted(self._read_catalog())]

    def _read_catalog(self) -> dict[str, object]:
        """Read the catalogue, treating an absent file as an empty store.

        Returns:
            The catalogue as a mutable mapping of slug to record.

        Raises:
            HydrofitError: If the file exists but is not a JSON object.
        """
        if not self.catalog_path.exists():
            return {}
        text = self.catalog_path.read_text(encoding="utf-8")
        try:
            decoded: object = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HydrofitError(
                f"{self.catalog_path} is not readable JSON: {exc}"
            ) from exc
        return dict(_as_mapping(decoded, str(self.catalog_path)))

    def _write_catalog(self, catalog: Mapping[str, object]) -> None:
        """Write the catalogue in a form that diffs one line at a time.

        Args:
            catalog: Mapping of slug to record.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        # allow_nan=False is a second line of defence: json would otherwise emit a bare NaN,
        # which no other JSON reader accepts. Series validation already rules it out, so this
        # makes a regression there loud in a second place.
        text = json.dumps(
            catalog, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
        )
        self.catalog_path.write_text(text + "\n", encoding="utf-8", newline="\n")

    def _write_points(self, series: Series) -> None:
        """Write the points of a series, losslessly.

        Args:
            series: The series whose points to write.
        """
        path = self.points_path(series.slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        # newline="" hands line endings to the csv module, and lineterminator overrides its
        # CRLF default: store/ is a runtime directory that .gitattributes does not cover, so
        # nothing else would keep these files identical across platforms.
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(_HEADER)
            for x, y in zip(series.x, series.y, strict=True):
                writer.writerow((repr(x), repr(y)))

    def _read_points(self, slug: str) -> tuple[tuple[float, ...], tuple[float, ...]]:
        """Read the points of one series.

        Args:
            slug: Series identifier.

        Returns:
            The x values and the y values.

        Raises:
            HydrofitError: If the file is missing, lacks the expected header, or holds a row
                that is not a pair of numbers.
        """
        path = self.points_path(slug)
        if not path.exists():
            raise HydrofitError(f"the catalogue lists {slug!r} but {path} is missing")
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        if not rows or tuple(rows[0]) != _HEADER:
            raise HydrofitError(
                f"{path} does not start with an '{_HEADER[0]},{_HEADER[1]}' header"
            )

        x: list[float] = []
        y: list[float] = []
        for number, row in enumerate(rows[1:], start=2):
            if len(row) != 2:
                raise HydrofitError(f"{path} line {number} does not hold two values")
            try:
                x.append(float(row[0]))
                y.append(float(row[1]))
            except ValueError as exc:
                raise HydrofitError(
                    f"{path} line {number} is not a pair of numbers"
                ) from exc
        return tuple(x), tuple(y)
