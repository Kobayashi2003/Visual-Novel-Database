"""The parameter names a search accepts.

The local and remote backends implement overlapping but unequal filter sets, so
a name only one of them implements is still legitimate; the accepted set is the
union of both. That set is taken from the builders rather than listed here: each
is run once against an empty parameter dict, where every lookup returns None and
so nothing is built and nothing is queried, leaving a record of the names it
asked for.
"""

from typing import Any

from .local import filters as local_filters
from .remote import filters as remote_filters


class TrackedParams(dict):
    """A parameter dict that records which names were looked up."""

    def __init__(self, data: dict):
        super().__init__(data)
        self.read: set[str] = set()

    def get(self, key, default=None):
        self.read.add(key)
        return super().get(key, default)

    def __contains__(self, key):
        self.read.add(key)
        return super().__contains__(key)

    def __getitem__(self, key):
        self.read.add(key)
        return super().__getitem__(key)


_known: dict[str, set[str]] = {}


def known_params(search_type: str) -> set[str]:
    if search_type not in _known:
        names: set[str] = set()
        for module in (local_filters, remote_filters):
            if builder := getattr(module, f'get_{search_type}_filters', None):
                probe = TrackedParams({})
                builder(probe)
                names |= probe.read
        _known[search_type] = names
    return _known[search_type]


def validate_params(search_type: str, params: dict[str, Any]) -> None:
    """Raise ValueError naming any parameter neither backend understands."""

    if unknown := set(params) - known_params(search_type):
        raise ValueError(f"Unknown search parameter(s): {', '.join(sorted(unknown))}")
