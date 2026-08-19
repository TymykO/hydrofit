"""The single error class hydrofit raises for problems the user can fix.

The CLI catches this class and prints its message with exit code 1. Anything that is not a
`HydrofitError` reaching the top level is a bug in hydrofit, and is allowed to show its
traceback — that distinction is the point of having exactly one class here.
"""


class HydrofitError(Exception):
    """An input or usage problem the user can act on.

    Raised for data that cannot describe a series, for a slug that collides with another
    series, and for a catalogue that disagrees with the points it claims to describe.
    """
