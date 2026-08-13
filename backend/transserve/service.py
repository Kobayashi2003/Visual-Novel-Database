"""Translation service.

Every route goes through this service; it binds the language pair once and
delegates to `operations`. Three capabilities live behind it:

  1. Term base — short entries: VNDB tag and trait names. Two thirds are
     phrases rather than single words, hence "term".

  2. Passage memory — long-form description text.

  3. Text translation (`translate_text`) — reserved and not implemented. The
     signature and route exist so callers can be wired up now; calling it
     raises `TranslationNotImplemented`.

Term and passage are peers: every operation exists for both, named
`<verb>_term` / `<verb>_passage`. They differ only in how one row is addressed
— a term is its own key, while a passage is too long for that and uses an
opaque `source_hash` instead. `lookup_passage` still takes the text.
"""

from typing import Iterable
from flask import current_app

from . import operations


class TranslationNotImplemented(NotImplementedError):
    """Raised by the reserved text-translation interface until it is built."""


class TranslationService:
    def __init__(self, source_lang: str | None = None, target_lang: str | None = None):
        self.source_lang = source_lang or current_app.config.get('SOURCE_LANG', 'en')
        self.target_lang = target_lang or current_app.config.get('TARGET_LANG', 'ja')

    # ------------------------------------------------------------------
    # Term base
    # ------------------------------------------------------------------

    def lookup_term(self, term: str) -> str | None:
        return operations.lookup_term(term, self.source_lang, self.target_lang)

    def lookup_term_batch(self, terms: Iterable[str]) -> dict[str, str | None]:
        """Keyed by the input terms; an unknown term maps to None."""
        return operations.lookup_term_batch(terms, self.source_lang, self.target_lang)

    def get_term(self, term: str):
        """The whole row, where `lookup_term` yields only the translation."""
        return operations.get_term(term, self.source_lang, self.target_lang)

    def list_term(self, category: str | None = None, search: str | None = None,
                  page: int = 1, limit: int = 50) -> dict:
        return operations.list_term(
            self.source_lang, self.target_lang, category, search, page, limit)

    def init_term(self, entries: Iterable[dict], default_category: str | None = None,
                  replace: bool = False) -> int:
        """`replace=True` clears this language pair first. Returns rows written."""
        return operations.init_term(
            entries, default_category, self.source_lang, self.target_lang, replace)

    def append_term(self, entries: Iterable[dict], default_category: str | None = None) -> int:
        """Upsert by source text. Returns rows written."""
        return operations.append_term(
            entries, default_category, self.source_lang, self.target_lang)

    def delete_term(self, term: str) -> bool:
        """False when there was nothing to delete."""
        return operations.delete_term(term, self.source_lang, self.target_lang)

    def count_term(self) -> int:
        return operations.count_term(self.source_lang, self.target_lang)

    # ------------------------------------------------------------------
    # Passage memory
    # ------------------------------------------------------------------

    def lookup_passage(self, text: str) -> str | None:
        return operations.lookup_passage(text, self.source_lang, self.target_lang)

    def lookup_passage_batch(self, texts: Iterable[str]) -> dict[str, str | None]:
        """Keyed by the input texts; an unknown passage maps to None."""
        return operations.lookup_passage_batch(texts, self.source_lang, self.target_lang)

    def get_passage(self, source_hash: str):
        """The whole row, where `lookup_passage` yields only the translation."""
        return operations.get_passage(source_hash, self.source_lang, self.target_lang)

    def list_passage(self, entity_type: str | None = None, search: str | None = None,
                     page: int = 1, limit: int = 50) -> dict:
        return operations.list_passage(
            self.source_lang, self.target_lang, entity_type, search, page, limit)

    def init_passage(self, entries: Iterable[dict], default_entity: str | None = None,
                     default_category: str | None = None, replace: bool = False) -> int:
        """`replace=True` clears this language pair first. Markup preservation is
        validated on every entry. Returns rows written."""
        return operations.init_passage(
            entries, default_entity, default_category,
            self.source_lang, self.target_lang, replace)

    def append_passage(self, entries: Iterable[dict], default_entity: str | None = None,
                       default_category: str | None = None) -> int:
        """Upsert by source hash. Returns rows written."""
        return operations.append_passage(
            entries, default_entity, default_category, self.source_lang, self.target_lang)

    def delete_passage(self, source_hash: str) -> bool:
        """False when there was nothing to delete."""
        return operations.delete_passage(
            source_hash, self.source_lang, self.target_lang)

    def count_passage(self) -> int:
        return operations.count_passage(self.source_lang, self.target_lang)

    # ------------------------------------------------------------------
    # Text translation (reserved)
    # ------------------------------------------------------------------

    def translate_text(self, text: str) -> str:
        raise TranslationNotImplemented(
            "Text translation is not implemented yet; only term and passage lookup are available."
        )
