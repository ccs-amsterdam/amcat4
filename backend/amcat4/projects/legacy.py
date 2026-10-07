"""
Conversion of project exports made by older (elasticsearch based) AmCAT servers.

The export format itself (ndjson with settings, field, user_role and document records) did not change, but field
definitions did:
- elastic_type no longer exists
- identifier fields are now unique fields (the document ids in the export are kept as is)
- snippet parameters are in words instead of characters
"""

from typing import Any

CHARS_PER_WORD = 6


def _chars_to_words(chars: Any, default: int) -> int:
    if not isinstance(chars, int):
        return default
    return max(1, round(chars / CHARS_PER_WORD))


def convert_field_definition(field: dict[str, Any]) -> dict[str, Any]:
    """Convert a field definition from an old export to the current format (new definitions are left unchanged)"""
    field = dict(field)
    field.pop("elastic_type", None)
    if "identifier" in field:
        field["unique"] = bool(field.pop("identifier"))
    metareader = field.get("metareader")
    if isinstance(metareader, dict) and isinstance(snippet := metareader.get("max_snippet"), dict):
        if "nomatch_chars" in snippet or "match_chars" in snippet:
            metareader = dict(metareader)
            metareader["max_snippet"] = {
                "nomatch_words": _chars_to_words(snippet.get("nomatch_chars"), 20),
                "max_matches": snippet.get("max_matches", 0),
                "words_per_match": _chars_to_words(snippet.get("match_chars"), 10),
            }
            field["metareader"] = metareader
    return field
