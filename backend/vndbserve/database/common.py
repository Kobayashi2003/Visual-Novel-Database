"""A row as a plain dict, for a JSON response.

Only the column values need converting; there are no relationships to walk, by
design — see README.md.
"""

import json
from datetime import date, datetime

from sqlalchemy import inspect


def convert_model_to_dict(model):
    return {column.key: convert_value(getattr(model, column.key))
            for column in inspect(model).mapper.column_attrs}


def convert_value(value):
    """One column value in a form `jsonify` will take.

    JSONB and array columns need no case of their own: their values arrive as
    dicts and lists, which the branches below already cover.
    """
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [convert_value(item) for item in value]
    if isinstance(value, dict):
        return {key: convert_value(item) for key, item in value.items()}
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError):
        # Whatever it is, the response still has to carry something.
        return str(value)
