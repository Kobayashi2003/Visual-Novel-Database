"""The VNDB id convention, shared by the route, search and database layers.

The prefix exists only for compatibility with the VNDB API — the resource type
is always known separately — so both '17' and 'v17' are accepted on input and
normalized to 'v17'.
"""

import re

ID_PREFIX = {
    'vn': 'v',
    'release': 'r',
    'character': 'c',
    'producer': 'p',
    'staff': 's',
    'tag': 'g',
    'trait': 'i',
}

TYPE_BY_PREFIX = {prefix: type for type, prefix in ID_PREFIX.items()}


def formatId(type: str, id: str) -> str:
    prefix = ID_PREFIX[type]
    match = re.fullmatch(rf'(?:{prefix})?(\d+)', str(id).lower())
    if not match:
        raise ValueError(f"Invalid ID: {id}")
    return f"{prefix}{match.group(1)}"
