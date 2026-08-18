"""Packaging tests: the distribution installs and the package imports.

These guard the three names of the project (distribution, import package, command)
at the two points that already exist in P1.3. The command is added in P3.3.
"""

import importlib
import re
from importlib.metadata import version


def test_distribution_is_installed() -> None:
    """The distribution is installed and reports a three-part version."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", version("hydrofit"))


def test_package_imports() -> None:
    """The import package is importable under its own name."""
    module = importlib.import_module("hydrofit")
    assert module.__name__ == "hydrofit"
