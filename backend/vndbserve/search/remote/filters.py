"""Build the Kana API's filter trees from flat query parameters.

Upstream takes filters as nested `["and", [...], [...]]` lists; callers here pass
plain `?lang=ja&length=>2` style parameters. This module does the translation,
including the `,`/`+` expression grammar (see search/parse) and the tag and trait
name to id lookups the API requires.

`get_*_additional_filters` holds the parameters this project adds on top of the
upstream vocabulary; the main `get_*_filters` stay faithful to the Kana API.
"""

import re
from typing import Any, Callable
from enum import Enum, auto
from ..parse import validate_logical_expression
from vndbserve.errors import Failed


class FilterType(Enum):
    STRING = auto()
    INTEGER = auto()
    FLOAT = auto()
    BOOLEAN = auto()
    DATE = auto()
    VNDBID = auto()
    ARRAY = auto()
    NESTED = auto()

class VNDBFilter:
    def __init__(self, name: str, filter_type: FilterType, flags: str = "", associated_domain: str | None = None):
        self.name = name
        self.filter_type = filter_type
        self.flags = flags
        self.associated_domain = associated_domain

class VNDBFilters:
    VN = {
        "id": VNDBFilter("id", FilterType.VNDBID, "o"),
        "search": VNDBFilter("search", FilterType.STRING, "m"),
        "lang": VNDBFilter("lang", FilterType.STRING, "m"),
        "olang": VNDBFilter("olang", FilterType.STRING),
        "platform": VNDBFilter("platform", FilterType.STRING, "m"),
        "length": VNDBFilter("length", FilterType.INTEGER, "o"),
        "released": VNDBFilter("released", FilterType.DATE, "o,n"),
        "rating": VNDBFilter("rating", FilterType.INTEGER, "o,i"),
        "votecount": VNDBFilter("votecount", FilterType.INTEGER, "o"),
        "has_description": VNDBFilter("has_description", FilterType.BOOLEAN),
        "has_anime": VNDBFilter("has_anime", FilterType.BOOLEAN),
        "has_screenshot": VNDBFilter("has_screenshot", FilterType.BOOLEAN),
        "has_review": VNDBFilter("has_review", FilterType.BOOLEAN),
        "devstatus": VNDBFilter("devstatus", FilterType.INTEGER),
        "tag": VNDBFilter("tag", FilterType.ARRAY, "m"),
        "dtag": VNDBFilter("dtag", FilterType.ARRAY, "m"),
        "anime_id": VNDBFilter("anime_id", FilterType.INTEGER),
        "label": VNDBFilter("label", FilterType.ARRAY, "m"),
        "release": VNDBFilter("release", FilterType.NESTED, "m", associated_domain="RELEASE"),
        "character": VNDBFilter("character", FilterType.NESTED, "m", associated_domain="CHARACTER"),
        "staff": VNDBFilter("staff", FilterType.NESTED, "m", associated_domain="STAFF"),
        "developer": VNDBFilter("developer", FilterType.NESTED, "m", associated_domain="PRODUCER"),
    }

    CHARACTER = {
        "id": VNDBFilter("id", FilterType.VNDBID, "o"),
        "search": VNDBFilter("search", FilterType.STRING, "m"),
        "role": VNDBFilter("role", FilterType.STRING, "m"),
        "blood_type": VNDBFilter("blood_type", FilterType.STRING),
        "sex": VNDBFilter("sex", FilterType.STRING),
        "sex_spoil": VNDBFilter("sex_spoil", FilterType.STRING),
        "gender": VNDBFilter("gender", FilterType.STRING),
        "gender_spoil": VNDBFilter("gender_spoil", FilterType.STRING),
        "height": VNDBFilter("height", FilterType.INTEGER, "o,n,i"),
        "weight": VNDBFilter("weight", FilterType.INTEGER, "o,n,i"),
        "bust": VNDBFilter("bust", FilterType.INTEGER, "o,n,i"),
        "waist": VNDBFilter("waist", FilterType.INTEGER, "o,n,i"),
        "hips": VNDBFilter("hips", FilterType.INTEGER, "o,n,i"),
        "cup": VNDBFilter("cup", FilterType.STRING, "o,n,i"),
        "age": VNDBFilter("age", FilterType.INTEGER, "o,n,i"),
        "trait": VNDBFilter("trait", FilterType.ARRAY, "m"),
        "dtrait": VNDBFilter("dtrait", FilterType.ARRAY, "m"),
        "birthday": VNDBFilter("birthday", FilterType.ARRAY, "n"),
        "seiyuu": VNDBFilter("seiyuu", FilterType.NESTED, "m", associated_domain="STAFF"),
        "vn": VNDBFilter("vn", FilterType.NESTED, "m", associated_domain="VN"),
    }

    PRODUCER = {
        "id": VNDBFilter("id", FilterType.VNDBID, "o"),
        "search": VNDBFilter("search", FilterType.STRING, "m"),
        "lang": VNDBFilter("lang", FilterType.STRING),
        "type": VNDBFilter("type", FilterType.STRING),
        "extlink": VNDBFilter("extlink", FilterType.STRING, "m"),
    }

    STAFF = {
        "id": VNDBFilter("id", FilterType.VNDBID, "o"),
        "aid": VNDBFilter("aid", FilterType.INTEGER),
        "search": VNDBFilter("search", FilterType.STRING, "m"),
        "lang": VNDBFilter("lang", FilterType.STRING),
        "gender": VNDBFilter("gender", FilterType.STRING),
        "role": VNDBFilter("role", FilterType.STRING, "m"),
        "extlink": VNDBFilter("extlink", FilterType.STRING, "m"),
        "ismain": VNDBFilter("ismain", FilterType.BOOLEAN),
    }

    TAG = {
        "id": VNDBFilter("id", FilterType.VNDBID, "o"),
        "search": VNDBFilter("search", FilterType.STRING, "m"),
        "category": VNDBFilter("category", FilterType.STRING),
    }

    TRAIT = {
        "id": VNDBFilter("id", FilterType.VNDBID, "o"),
        "search": VNDBFilter("search", FilterType.STRING, "m"),
    }

    RELEASE = {
        "id": VNDBFilter("id", FilterType.VNDBID, "o"),
        "search": VNDBFilter("search", FilterType.STRING, "m"),
        "lang": VNDBFilter("lang", FilterType.STRING, "m"),
        "platform": VNDBFilter("platform", FilterType.STRING, "m"),
        "released": VNDBFilter("released", FilterType.DATE, "o"),
        "resolution": VNDBFilter("resolution", FilterType.ARRAY, "o,i"),
        "resolution_aspect": VNDBFilter("resolution_aspect", FilterType.ARRAY, "o,i"),
        "minage": VNDBFilter("minage", FilterType.INTEGER, "o,n,i"),
        "medium": VNDBFilter("medium", FilterType.STRING, "m,n"),
        "voiced": VNDBFilter("voiced", FilterType.INTEGER, "n"),
        "engine": VNDBFilter("engine", FilterType.STRING, "n"),
        "rtype": VNDBFilter("rtype", FilterType.STRING, "m"),
        "extlink": VNDBFilter("extlink", FilterType.STRING, "m"),
        "drm": VNDBFilter("drm", FilterType.STRING, "m"),
        "image": VNDBFilter("image", FilterType.STRING, "m,n"),
        "patch": VNDBFilter("patch", FilterType.BOOLEAN),
        "freeware": VNDBFilter("freeware", FilterType.BOOLEAN),
        "uncensored": VNDBFilter("uncensored", FilterType.BOOLEAN, "i"),
        "official": VNDBFilter("official", FilterType.BOOLEAN),
        "has_ero": VNDBFilter("has_ero", FilterType.BOOLEAN),
        "vn": VNDBFilter("vn", FilterType.NESTED, "m", associated_domain="VN"),
        "producer": VNDBFilter("producer", FilterType.NESTED, "m", associated_domain="PRODUCER"),
    }


def build_filter(filter_set: dict[str, VNDBFilter], key: str, value: Any) -> list:
    if key not in filter_set:
        raise ValueError(f"Invalid key: {key}")

    filter_def = filter_set[key]

    operator, filter_value = '=', value

    if 'o' in filter_def.flags and isinstance(value, str):
        pattern = r'^(>=|<=|>|<|=|!=)(.+)$'
        match = re.match(pattern, value.strip())
        if match:
            operator, filter_value = match.groups()

    if not filter_value:
        raise ValueError(f"Invalid value: {value}")

    if isinstance(filter_value, str):
        filter_value = filter_value.strip()

    if filter_def.filter_type == FilterType.NESTED:
        if not isinstance(filter_value, dict):
            raise ValueError(f"Invalid value: {value}")
        if filter_def.associated_domain:
            associated_filter_set = getattr(VNDBFilters, filter_def.associated_domain)
            nested_filters = build_filters(associated_filter_set, filter_value)
        else:
            nested_filters = build_filters(filter_set, filter_value)
        return [key, "=", nested_filters]

    if filter_def.filter_type == FilterType.ARRAY:
        if key in ('tag', 'dtag'):
            # Either a bare tag id ("g505"), or the spoiler-aware array form
            # [id, max_spoiler (0-2), min_tag_level (0-3)] that the Kana API
            # accepts. The array is built upstream by parse_tag_expression.
            if isinstance(filter_value, list) and len(filter_value) != 3:
                raise ValueError(f"Invalid value: {value}")
        elif key in ('trait', 'dtrait'):
            # Either a bare trait id ("i123"), or the array form
            # [id, max_spoiler (0-2)].
            if isinstance(filter_value, list) and len(filter_value) != 2:
                raise ValueError(f"Invalid value: {value}")
        elif not isinstance(filter_value, list):
            raise ValueError(f"Invalid value: {value}")

    if filter_def.filter_type == FilterType.BOOLEAN:
        if isinstance(filter_value, bool):
            operator = '=' if filter_value else '!='
        elif isinstance(filter_value, str):
            if filter_value.lower() == 'false' or filter_value.lower() == '0':
                operator = '!='
            elif filter_value.lower() == 'true' or filter_value.lower() == '1':
                operator = '='
            else:
                raise ValueError(f"Invalid value: {value}")
        elif isinstance(filter_value, int):
            if filter_value == 0:
                operator = '!='
            elif filter_value == 1:
                operator = '='
            else:
                raise ValueError(f"Invalid value: {value}")
        else:
            raise ValueError(f"Invalid value: {value}")
        filter_value = 1

    if filter_def.filter_type == FilterType.INTEGER:
        if isinstance(filter_value, str):
            int(filter_value)
        elif not isinstance(filter_value, int):
            raise ValueError(f"Invalid value: {value}")

    if filter_def.filter_type == FilterType.FLOAT:
        if isinstance(filter_value, str):
            float(filter_value)
        elif not isinstance(filter_value, float):
            raise ValueError(f"Invalid value: {value}")

    if filter_def.filter_type == FilterType.VNDBID:
        pattern = r'^([v|r|c|p|s|g|i]\d+|\d+)$'
        match = re.match(pattern, filter_value)
        if not match:
            raise ValueError(f"Invalid value: {value}")
        filter_value = match.group(1)

    if not isinstance(filter_value, list):
        filter_value = str(filter_value)

    return [key, operator, filter_value]

def negate_filters(node: list) -> list:
    """Push a logical NOT down to the leaves of a built Kana filter.

    The Kana API has no top-level negation, but every tag/trait leaf supports
    the `!=` operator ("does not have this tag/trait"). De Morgan lets us negate
    an arbitrary AND/OR tree by swapping the combinators and inverting each leaf
    operator. Only valid for trees whose leaves are plain `[name, op, value]`
    predicates (true for tag/trait expressions, which never contain NESTED
    filters).
    """
    if not node:
        return node
    if node[0] in ('and', 'or'):
        flipped = 'or' if node[0] == 'and' else 'and'
        return [flipped] + [negate_filters(child) for child in node[1:]]
    name, operator, value = node
    return [name, '!=' if operator == '=' else '=', value]

def build_filters(filter_set: dict[str, VNDBFilter], filters: dict[str, Any]) -> list:
    result = []
    for key, value in filters.items():
        if key in ['and', 'or']:
            result.append([key] + [build_filters(filter_set, item) for item in value])
        elif key == '_not':
            # `value` is a normal filter subtree; build it, then negate the
            # whole built expression via De Morgan (see negate_filters).
            result.append(negate_filters(build_filters(filter_set, value)))
        else:
            result.append(build_filter(filter_set, key, value))
    return [] if not result else result[0] if len(result) == 1 else ["and"] + result


def parse_logical_expression(expression: str, field: str,
                             value_wrapper: Callable[[str], Any] | None = None) -> dict[str, Any]:
    """
    Parse logical expression using two stacks.
    Operators: OR (',', lower precedence) and AND ('+', higher precedence)

    `value_wrapper`, when given, transforms each leaf value before it is stored
    (e.g. wrapping a bare tag id into the `[id, spoiler, level]` array form).
    """
    if not validate_logical_expression(expression):
        raise ValueError(f"Invalid expression: {expression}")

    wrap = value_wrapper if value_wrapper is not None else (lambda v: v)

    def or_operation(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        """Merge OR operations"""
        if isinstance(left, dict) and "or" in left:
            if isinstance(right, dict) and "or" in right:
                return {"or": left["or"] + right["or"]}
            left["or"].append(right)
            return left
        elif isinstance(right, dict) and "or" in right:
            right["or"].insert(0, left)
            return right
        return {"or": [left, right]}

    def and_operation(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        """Merge AND operations"""
        if isinstance(left, dict) and "and" in left:
            if isinstance(right, dict) and "and" in right:
                return {"and": left["and"] + right["and"]}
            left["and"].append(right)
            return left
        elif isinstance(right, dict) and "and" in right:
            right["and"].insert(0, left)
            return right
        return {"and": [left, right]}

    def evaluate(ops: list, vals: list) -> None:
        if len(ops) > 0 and len(vals) >= 2:
            op = ops.pop()
            right = vals.pop()
            left = vals.pop()

            if op == "or":
                vals.append(or_operation(left, right))
            elif op == "and":
                vals.append(and_operation(left, right))

    ops = []
    vals = []
    current = ""

    for char in expression:
        if char == '(':
            ops.append(char)
        elif char == ')':
            if current:
                vals.append({field: wrap(current.strip())})
                current = ""
            while ops and ops[-1] != '(':
                evaluate(ops, vals)
            if ops and ops[-1] == '(':
                ops.pop()
        elif char in '+,':
            if current:
                vals.append({field: wrap(current.strip())})
                current = ""
            while ops and ops[-1] != '(' and char == ',' and ops[-1] == '+':
                evaluate(ops, vals)
            ops.append('and' if char == '+' else 'or')
        else:
            current += char

    if current:
        vals.append({field: wrap(current.strip())})

    while ops:
        evaluate(ops, vals)

    return vals[0] if vals else {}

def parse_tag_expression(expression: str, directly: bool = False, spoil: bool = False) -> dict[str, Any]:
    from .search import api
    url = "https://api.vndb.org/kana/tag"
    client = api.client

    def get_tag_ids(tag: str) -> list[str]:
        """Resolve a tag name to tag IDs, or return it as-is when already an
        id (`g<number>`) so no extra request to the Kana API is needed."""
        if re.match(r'^g\d+$', tag):
            return [tag]
        results = []
        page = 1
        more = True
        while more:
            payload = {
                "filters": ["search", "=", tag],
                "fields": "id",
                "page": page,
                "results": 100
            }
            response = client.post(url, json=payload)
            results.extend(response.json().get('results', []))
            more = response.json().get('more', False)
            page += 1
        return [result['id'] for result in results]

    def process_tags(expr: str) -> str:
        """Extract and process tags from expression"""
        # Store positions of brackets for reconstruction
        brackets = []
        current_pos = 0
        while current_pos < len(expr):
            if expr[current_pos] in '()':
                brackets.append((current_pos, expr[current_pos]))
            current_pos += 1

        # Split by operators and process each tag
        tags = re.split(r'[+,()]', expr)
        tags = [tag.strip() for tag in tags if tag.strip()]

        tag_map = {}
        for tag in tags:
            if tag not in tag_map:
                ids = get_tag_ids(tag)
                if ids:
                    # If multiple IDs found, combine them with OR
                    tag_map[tag] = f"({','.join(ids)})" if len(ids) > 1 else ids[0]
                else:
                    tag_map[tag] = "g0"  # Placeholder for non-existent tag

        # Reconstruct expression with IDs
        new_expr = expr
        for tag, tag_ids in tag_map.items():
            new_expr = re.sub(r'\b' + re.escape(tag) + r'\b', tag_ids, new_expr)

        return new_expr

    new_expression = process_tags(expression.strip())

    field = 'dtag' if directly else 'tag'
    # Spoiler-aware variants request at the Major spoiler level (2); the bare
    # form keeps the Kana API default (spoiler 0). Min tag level stays 0.
    wrapper = (lambda tag_id: [tag_id, 2, 0]) if spoil else None
    return parse_logical_expression(new_expression, field, wrapper)

def parse_trait_expression(expression: str, directly: bool = False, spoil: bool = False) -> dict[str, Any]:
    from .search import api
    url = "https://api.vndb.org/kana/trait"
    client = api.client

    def get_trait_ids(trait: str) -> list[str]:
        """Get trait IDs from trait name or return as-is if already an ID."""
        if re.match(r'^i\d+$', trait):
            return [trait]
        results = []
        page = 1
        more = True
        while more:
            payload = {
                "filters": ["search", "=", trait],
                "fields": "id",
                "page": page,
                "results": 100
            }
            response = client.post(url, json=payload)
            results.extend(response.json().get('results', []))
            more = response.json().get('more', False)
            page += 1
        return [result['id'] for result in results]

    def process_traits(expr: str) -> str:
        """Extract and process traits from expression"""
        traits = re.split(r'[+,()]', expr)
        traits = [trait.strip() for trait in traits if trait.strip()]

        trait_map = {}
        for trait in traits:
            if trait not in trait_map:
                ids = get_trait_ids(trait)
                if ids:
                    trait_map[trait] = f"({','.join(ids)})" if len(ids) > 1 else ids[0]
                else:
                    trait_map[trait] = "i0"  # Placeholder for non-existent trait

        new_expr = expr
        for trait, trait_ids in trait_map.items():
            new_expr = re.sub(r'\b' + re.escape(trait) + r'\b', trait_ids, new_expr)

        return new_expr

    new_expression = process_traits(expression.strip())

    field = 'dtrait' if directly else 'trait'
    # Spoiler-aware variants request at the Major spoiler level (2); the bare
    # form keeps the Kana API default (spoiler 0). Traits have no level field.
    wrapper = (lambda trait_id: [trait_id, 2]) if spoil else None
    return parse_logical_expression(new_expression, field, wrapper)

def parse_int(value: str | None, comparable: bool = False) -> str | None:
    value = value.replace(" ", "")
    pattern = r'^(>=|<=|>|<|=|!=)?(\d+)$' if comparable else r'^(\d+)$'
    match = re.match(pattern, value)
    if match:
        return value
    return None

def parse_birthday(value: str) -> list[int] | None:
    value = value.replace(" ", "")
    pattern = r'^(\d{1,2})-(\d{1,2})$'
    match = re.match(pattern, value)
    if match:
        month, day = map(int, match.groups())
        if 1 <= month <= 12 and 1 <= day <= 31:
            return [month, day]
    return None


def get_vn_additional_filters(params: dict[str, Any]) -> dict[str, Any]:
    filters = []

    if release_id := params.get('release_id'):
        filters.append({"release": ["id", "=", release_id]})

    if character_id := params.get('character_id'):
        filters.append({"character": ["id", "=", character_id]})

    if staff_id := params.get('staff_id'):
        filters.append({"staff": ["id", "=", staff_id]})

    if developer_id := params.get('developer_id'):
        filters.append({"developer": ["id", "=", developer_id]})

    # Spoiler-aware tag variants: map onto the API `tag`/`dtag` filter using
    # its [id, max_spoiler, min_level] array form (max_spoiler = 2).
    if tag_spoil := params.get('tag_spoil'):
        filters.append(parse_tag_expression(tag_spoil, spoil=True))

    if dtag_spoil := params.get('dtag_spoil'):
        filters.append(parse_tag_expression(dtag_spoil, directly=True, spoil=True))

    # tag exclusion. Kana has no top-level NOT, so wrap the parsed tag tree in
    # a `_not` marker that build_filters negates (per-leaf `!=`, see
    # negate_filters). `tag_exclude` caps at spoiler 0, `tag_exclude_spoil` at 2.
    if tag_exclude := params.get('tag_exclude'):
        if parsed := parse_tag_expression(tag_exclude):
            filters.append({"_not": parsed})

    if tag_exclude_spoil := params.get('tag_exclude_spoil'):
        if parsed := parse_tag_expression(tag_exclude_spoil, spoil=True):
            filters.append({"_not": parsed})

    return filters

def get_release_additional_filters(params: dict[str, Any]) -> dict[str, Any]:
    filters = []

    if vn_id := params.get('vn_id'):
        filters.append({"vn": ["id", "=", vn_id]})

    if producer_id := params.get('producer_id'):
        filters.append({"producer": ["id", "=", producer_id]})

    return filters

def get_character_additional_filters(params: dict[str, Any]) -> dict[str, Any]:
    filters = []

    if vn_id := params.get('vn_id'):
        filters.append({"vn": ["id", "=", vn_id]})

    # Spoiler-aware trait variants: map onto the API `trait`/`dtrait` filter
    # using its [id, max_spoiler] array form (max_spoiler = 2).
    if trait_spoil := params.get('trait_spoil'):
        filters.append(parse_trait_expression(trait_spoil, spoil=True))

    if dtrait_spoil := params.get('dtrait_spoil'):
        filters.append(parse_trait_expression(dtrait_spoil, directly=True, spoil=True))

    # trait exclusion. Same `_not` mechanism as tag exclusion above.
    # `trait_exclude` caps at spoiler 0, `trait_exclude_spoil` at 2.
    if trait_exclude := params.get('trait_exclude'):
        if parsed := parse_trait_expression(trait_exclude):
            filters.append({"_not": parsed})

    if trait_exclude_spoil := params.get('trait_exclude_spoil'):
        if parsed := parse_trait_expression(trait_exclude_spoil, spoil=True):
            filters.append({"_not": parsed})

    return filters

def get_producer_additional_filters(params: dict[str, Any]) -> dict[str, Any]:
    filters = []

    return filters

def get_staff_additional_filters(params: dict[str, Any]) -> dict[str, Any]:
    filters = []

    return filters

def get_tag_additional_filters(params: dict[str, Any]) -> dict[str, Any]:
    filters = []

    return filters

def get_trait_additional_filters(params: dict[str, Any]) -> dict[str, Any]:
    filters = []

    return filters


def get_vn_filters(params: dict[str, Any]) -> dict[str, Any]:
    """The Kana API filter list for a visual novel search, built from `params`."""
    filters = []

    if id := params.get('id'):
        filters.append(parse_logical_expression(id, 'id'))

    if search := params.get('search'):
        filters.append({"search": search})

    if tag := params.get('tag'):
        filters.append(parse_tag_expression(tag))

    if dtag := params.get('dtag'):
        filters.append(parse_tag_expression(dtag, directly=True))

    multi_value_fields = ['lang', 'platform', 'released', 'olang']
    for field in multi_value_fields:
        if value := params.get(field):
            if parsed := parse_logical_expression(value, field):
                filters.append(parsed)

    nested_fields = ['character', 'staff', 'developer', 'release']
    for field in nested_fields:
        if value := params.get(field):
            if parsed := parse_logical_expression(value, 'search'):
                filters.append({field: parsed})

    uncomparable_numeric_fields = ['devstatus']
    for field in uncomparable_numeric_fields:
        if value := params.get(field):
            if parsed := parse_int(value):
                filters.append({field: parsed})

    comparable_numeric_fields = ['length', 'rating', 'votecount']
    for field in comparable_numeric_fields:
        if value := params.get(field):
            if parsed := parse_int(value, True):
                filters.append({field: parsed})

    boolean_fields = ['has_description', 'has_anime', 'has_screenshot', 'has_review']
    for field in boolean_fields:
        if value := params.get(field):
            filters.append({field: str(value).lower() == 'true' or str(value) == '1'})

    filters.extend(get_vn_additional_filters(params))

    # Wrap in 'and' if there are multiple filters
    return {"and": filters} if len(filters) > 1 else filters[0] if filters else {}

def get_release_filters(params: dict[str, Any]) -> dict[str, Any]:
    """The Kana API filter list for a release search, built from `params`."""
    filters = []

    if id := params.get('id'):
        filters.append(parse_logical_expression(id, 'id'))

    if search := params.get('search'):
        filters.append({"search": search})

    multi_value_fields = ['lang', 'platform', 'medium', 'drm', 'image']
    for field in multi_value_fields:
        if value := params.get(field):
            if parsed := parse_logical_expression(value, field):
                filters.append(parsed)

    if released := params.get('released'):
        filters.append({"released": released})

    for field in ['resolution', 'resolution_aspect']:
        if value := params.get(field):
            try:
                width, height = map(int, value.strip('[]').split(','))
                filters.append({field: [width, height]})
            except ValueError:
                pass  # Invalid format, skip this filter

    uncomparable_numeric_fields = ['voiced']
    for field in uncomparable_numeric_fields:
        if value := params.get(field):
            if parsed := parse_int(value):
                filters.append({field: parsed})

    comparable_numeric_fields = ['minage']
    for field in comparable_numeric_fields:
        if value := params.get(field):
            if parsed := parse_int(value, True):
                filters.append({field: parsed})

    string_fields = ['engine', 'rtype']
    for field in string_fields:
        if value := params.get(field):
            filters.append({field: value})

    boolean_fields = ['patch', 'freeware', 'uncensored', 'official', 'has_ero']
    for field in boolean_fields:
        if value := params.get(field):
            filters.append({field: str(value).lower() == 'true' or str(value) == '1'})

    nested_fields = ['vn', 'producer']
    for field in nested_fields:
        if value := params.get(field):
            if parsed := parse_logical_expression(value, 'search'):
                filters.append({field: parsed})

    if extlink := params.get('extlink'):
        filters.append({"extlink": extlink})

    filters.extend(get_release_additional_filters(params))

    return {"and": filters} if len(filters) > 1 else filters[0] if filters else {}

def get_character_filters(params: dict[str, Any]) -> dict[str, Any]:
    """The Kana API filter list for a character search, built from `params`."""
    filters = []

    if id := params.get('id'):
        filters.append(parse_logical_expression(id, 'id'))

    if search := params.get('search'):
        filters.append({"search": search})

    if birthday := params.get('birthday'):
        if parsed := parse_birthday(birthday):
            filters.append({"birthday": parsed})

    if trait := params.get('trait'):
        filters.append(parse_trait_expression(trait))

    if dtrait := params.get('dtrait'):
        filters.append(parse_trait_expression(dtrait, directly=True))

    multi_value_fields = ['role']
    for field in multi_value_fields:
        if value := params.get(field):
            if parsed := parse_logical_expression(value, field):
                filters.append(parsed)

    nested_fields = ['seiyuu', 'vn']
    for field in nested_fields:
        if value := params.get(field):
            if parsed := parse_logical_expression(value, 'search'):
                filters.append({field: parsed})

    single_value_fields = ['blood_type', 'sex', 'sex_spoil', 'gender', 'gender_spoil', 'cup']
    for field in single_value_fields:
        if value := params.get(field):
            filters.append({field: value})

    comparable_numeric_fields = ['height', 'weight', 'bust', 'waist', 'hips', 'age']
    for field in comparable_numeric_fields:
        if value := params.get(field):
            if parsed := parse_int(value, True):
                filters.append({field: parsed})

    filters.extend(get_character_additional_filters(params))

    return {"and": filters} if len(filters) > 1 else filters[0] if filters else {}

def get_producer_filters(params: dict[str, Any]) -> dict[str, Any]:
    """The Kana API filter list for a producer search, built from `params`."""
    filters = []

    if id := params.get('id'):
        filters.append(parse_logical_expression(id, 'id'))

    if search := params.get('search'):
        filters.append({"search": search})

    multi_value_fields = ['lang', 'type']
    for field in multi_value_fields:
        if value := params.get(field):
            if parsed := parse_logical_expression(value, field):
                filters.append(parsed)

    if extlink := params.get('extlink'):
        filters.append({"extlink": extlink})

    filters.extend(get_producer_additional_filters(params))

    return {"and": filters} if len(filters) > 1 else filters[0] if filters else {}

def get_staff_filters(params: dict[str, Any]) -> dict[str, Any]:
    """The Kana API filter list for a staff search, built from `params`."""
    filters = []

    if id := params.get('id'):
        filters.append(parse_logical_expression(id, 'id'))

    if aid := params.get('aid'):
        if parsed := parse_int(aid):
            filters.append({"aid": parsed})

    if search := params.get('search'):
        filters.append({"search": search})

    multi_value_fields = ['lang', 'role']
    for field in multi_value_fields:
        if value := params.get(field):
            if parsed := parse_logical_expression(value, field):
                filters.append(parsed)

    if gender := params.get('gender'):
        filters.append({"gender": gender})

    if ismain := params.get('ismain'):
        filters.append({"ismain": str(ismain).lower() == 'true' or str(ismain) == '1'})

    if extlink := params.get('extlink'):
        filters.append({"extlink": extlink})

    filters.extend(get_staff_additional_filters(params))

    return {"and": filters} if len(filters) > 1 else filters[0] if filters else {}

def get_tag_filters(params: dict[str, Any]) -> dict[str, Any]:
    """The Kana API filter list for a tag search, built from `params`."""
    filters = []

    if id := params.get('id'):
        filters.append(parse_logical_expression(id, 'id'))

    if search := params.get('search'):
        filters.append({"search": search})

    if category := params.get('category'):
        if parsed := parse_logical_expression(category, 'category'):
            filters.append(parsed)

    filters.extend(get_tag_additional_filters(params))

    return {"and": filters} if len(filters) > 1 else filters[0] if filters else {}

def get_trait_filters(params: dict[str, Any]) -> dict[str, Any]:
    """The Kana API filter list for a trait search, built from `params`."""
    filters = []

    if id := params.get('id'):
        filters.append(parse_logical_expression(id, 'id'))

    if search := params.get('search'):
        filters.append({"search": search})

    filters.extend(get_trait_additional_filters(params))

    return {"and": filters} if len(filters) > 1 else filters[0] if filters else {}


def get_remote_filters(search_type: str, params: dict[str, Any]) -> list:
    """Dispatch to the per-type builder. Raises ValueError on an unknown type."""

    if search_type == 'vn':
        return build_filters(VNDBFilters.VN, get_vn_filters(params))
    elif search_type == 'release':
        return build_filters(VNDBFilters.RELEASE, get_release_filters(params))
    elif search_type == 'character':
        return build_filters(VNDBFilters.CHARACTER, get_character_filters(params))
    elif search_type == 'producer':
        return build_filters(VNDBFilters.PRODUCER, get_producer_filters(params))
    elif search_type == 'staff':
        return build_filters(VNDBFilters.STAFF, get_staff_filters(params))
    elif search_type == 'tag':
        return build_filters(VNDBFilters.TAG, get_tag_filters(params))
    elif search_type == 'trait':
        return build_filters(VNDBFilters.TRAIT, get_trait_filters(params))
    else:
        raise Failed('internal_error', f"Invalid search_type: {search_type}")


if __name__ == '__main__':
    print(get_remote_filters(
        search_type='vn',
        params={
            'id': '17',
            # 'search': 'ai kiss',
            # 'id': '((v1,v2)+(v6,v7,v8))',
            # 'tag': 'Gang Rape + Unavoidable Rape',
        }
    ))