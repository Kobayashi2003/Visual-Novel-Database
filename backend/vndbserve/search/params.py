"""The parameter names a search accepts.

The local and remote backends implement overlapping but unequal filter sets, so
a name only one of them implements is still legitimate; the accepted set is the
union of both. That set is taken from the builders rather than listed here: each
is run once against an empty parameter dict, where every lookup returns None and
so nothing is built and nothing is queried, leaving a record of the names it
asked for.
"""

from typing import Any
from vndbserve.errors import Rejected

from .local import fields as local_fields
from .local import filters as local_filters
from .remote import fields as remote_fields
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


_read: dict[str, dict[str, set[str]]] = {}


def _read_by_backend(search_type: str) -> dict[str, set[str]]:
    """The names each backend's builder asks for, probed once per type."""

    if search_type not in _read:
        sets = {}
        for name, module in (('local', local_filters), ('remote', remote_filters)):
            probe = TrackedParams({})
            if builder := getattr(module, f'get_{search_type}_filters', None):
                builder(probe)
            sets[name] = probe.read
        _read[search_type] = sets
    return _read[search_type]


def known_params(search_type: str) -> set[str]:
    """Every name either backend understands."""

    sets = _read_by_backend(search_type)
    return sets['local'] | sets['remote']


def local_only_params(search_type: str) -> set[str]:
    """Names the mirror implements and Kana has no equivalent for.

    A query using one can only be answered by the mirror, so `both` serves it
    from there and the remote backend refuses it — the alternative is rows the
    filter was never applied to, returned as though it had been.
    """

    sets = _read_by_backend(search_type)
    return sets['local'] - sets['remote']


def sort_is_local_only(search_type: str, sort: str) -> bool:
    """Whether the mirror is the only side that can order by this.

    Settled by asking each backend what it accepts, the same way the parameter
    sets are — `average` and the lifecycle columns exist only here, `searchrank`
    only upstream, and neither list has to be maintained by hand.
    """
    try:
        local_fields.validate_sort(search_type, sort)
    except Exception:
        return False
    try:
        remote_fields.validate_sort(search_type, sort)
    except Exception:
        return True
    return False


def validate_params(search_type: str, params: dict[str, Any]) -> None:
    """Reject any parameter neither backend understands."""

    if unknown := set(params) - known_params(search_type):
        raise Rejected('invalid_request',
                       f"Unknown search parameter(s): {', '.join(sorted(unknown))}")
