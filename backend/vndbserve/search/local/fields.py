"""Which columns to select for a local search, per entity type.

The local mirror of search/remote/fields: the same `small` / `large` split, so a
caller switching source gets the same shape back.
"""

from vndbserve.database.models import VN as VisualNovel, Tag, Producer, Staff, Character, Trait, Release

class LocalFields:
    VN = [column.key for column in VisualNovel.__table__.columns]
    RELEASE = [column.key for column in Release.__table__.columns]
    CHARACTER = [column.key for column in Character.__table__.columns]
    PRODUCER = [column.key for column in Producer.__table__.columns]
    STAFF = [column.key for column in Staff.__table__.columns]
    TAG = [column.key for column in Tag.__table__.columns]
    TRAIT = [column.key for column in Trait.__table__.columns]

    SMALL_VN = ['id', 'title', 'alttitle', 'titles', 'released', 'developers', 'image']
    SMALL_RELEASE = ['id', 'title', 'alttitle', 'released', 'minage', 'patch', 'official', 'uncensored', 'media', 'platforms', 'vns', 'producers', 'languages']
    SMALL_CHARACTER = ['id', 'name', 'sex', 'original', 'vns', 'image']
    SMALL_PRODUCER = ['id', 'name', 'original']
    SMALL_STAFF = ['id', 'name', 'original']
    SMALL_TAG = ['id', 'name', 'category']
    SMALL_TRAIT = ['id', 'name', 'group_id', 'group_name']

    @staticmethod
    def get_fields(model_name: str) -> list:
        return getattr(LocalFields, model_name.upper(), [])

SORTABLE_FIELDS = {
    'vn': [
        'id', 'title', 'released', 'length_minutes', 'length_votes',
        'average', 'rating', 'votecount', 'created_at', 'updated_at',
    ],
    'release': [
        'id', 'title', 'released', 'minage', 'created_at', 'updated_at',
    ],
    'character': [
        'id', 'name', 'original', 'height', 'weight',
        'bust', 'waist', 'hips', 'age', 'birthday',
        'created_at', 'updated_at',
    ],
    'producer': [
        'id', 'name', 'original', 'created_at', 'updated_at',
    ],
    'staff': [
        'id', 'name', 'original', 'created_at', 'updated_at',
    ],
    'tag': [
        'id', 'name', 'vn_count', 'created_at', 'updated_at',
    ],
    'trait': [
        'id', 'name', 'group_id', 'group_name', 'char_count',
        'created_at', 'updated_at',
    ]
}

def validate_sort(search_type: str, sort: str) -> str:
    if search_type not in SORTABLE_FIELDS:
        raise ValueError(f"Invalid search_type: {search_type}")
    if sort not in SORTABLE_FIELDS[search_type]:
        raise ValueError(f"Invalid sort: {sort} for search_type: {search_type}")
    return sort

def get_local_fields(search_type: str, response_size: str = 'small') -> list[str]:
    """The columns to select for a local search. `small` covers what a card
    needs, `large` the whole entity. Raises ValueError on an unknown type."""
    if response_size not in ['small', 'large']:
        raise ValueError(f"Invalid response_size: {response_size}. Must be 'small' or 'large'.")

    field_mapping = {
        'vn': (LocalFields.SMALL_VN, LocalFields.VN),
        'character': (LocalFields.SMALL_CHARACTER, LocalFields.CHARACTER),
        'tag': (LocalFields.SMALL_TAG, LocalFields.TAG),
        'producer': (LocalFields.SMALL_PRODUCER, LocalFields.PRODUCER),
        'staff': (LocalFields.SMALL_STAFF, LocalFields.STAFF),
        'trait': (LocalFields.SMALL_TRAIT, LocalFields.TRAIT),
        'release': (LocalFields.SMALL_RELEASE, LocalFields.RELEASE)
    }

    if search_type not in field_mapping:
        raise ValueError(f"Invalid search_type: {search_type}")

    return field_mapping[search_type][0] if response_size == 'small' else field_mapping[search_type][1]