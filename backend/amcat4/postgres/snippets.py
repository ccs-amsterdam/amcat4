"""
Snippets and highlighting.

Snippets are a security boundary (metareaders may only see snippets of some fields), so we build them ourselves
from the stored text and enforce the limits here. Snippets are defined in words:

- If there are query matches (and max_matches > 0): at most max_matches fragments of words_per_match words around
  the matches, joined by " ... "
- Otherwise: the first nomatch_words words of the text
"""

import re

from amcat4.models import SnippetParams

_WORD = re.compile(r"\S+")


def make_snippet(
    text: str | None,
    positions: list[list[int]] | None,
    params: SnippetParams,
    pre_tag: str = "",
    post_tag: str = "",
) -> str:
    """
    Create a snippet from text, given the (start, end) character offsets of query matches.
    The snippet never contains more than max(nomatch_words, max_matches * words_per_match) words.
    """
    if not text:
        return ""
    words = [(m.start(), m.end()) for m in _WORD.finditer(text)]
    if not words:
        return ""
    if not positions or params.max_matches == 0:
        n = params.nomatch_words
        return text[words[0][0] : words[min(n, len(words)) - 1][1]] if n > 0 else ""

    # the word index of each match (a match can span multiple words)
    def word_index(offset: int) -> int:
        for i, (start, end) in enumerate(words):
            if offset < end:
                return i
        return len(words) - 1

    fragments: list[tuple[int, int]] = []  # word ranges [first, last]
    for start, end in sorted((p[0], p[1]) for p in positions):
        first, last = word_index(start), word_index(max(start, end - 1))
        if fragments and first <= fragments[-1][1]:
            continue  # match falls within the previous fragment
        if len(fragments) >= params.max_matches:
            break
        size = params.words_per_match
        match_words = last - first + 1
        if match_words >= size:
            fragments.append((first, first + size - 1))
            continue
        before = (size - match_words) // 2
        fstart = max(0, first - before)
        fend = min(len(words) - 1, fstart + size - 1)
        fstart = max(0, fend - size + 1)
        if fragments and fstart <= fragments[-1][1]:
            fstart = fragments[-1][1] + 1
        fragments.append((fstart, fend))

    parts = []
    for first, last in fragments:
        start, end = words[first][0], words[last][1]
        matches = [(max(s, start), min(e, end)) for s, e in sorted((p[0], p[1]) for p in positions) if s < end and e > start]
        parts.append(_tag(text, start, end, matches, pre_tag, post_tag))
    return " ... ".join(parts)


def _tag(text: str, start: int, end: int, matches: list[tuple[int, int]], pre_tag: str, post_tag: str) -> str:
    out, cursor = [], start
    for mstart, mend in matches:
        if mstart < cursor:
            continue
        out += [text[cursor:mstart], pre_tag, text[mstart:mend], post_tag]
        cursor = mend
    out.append(text[cursor:end])
    return "".join(out)


def highlight(
    text: str | None, positions: list[list[int]] | None, pre_tag: str = "<em>", post_tag: str = "</em>"
) -> str | None:
    """Return the full text with query matches wrapped in tags"""
    if not text or not positions:
        return text
    return _tag(text, 0, len(text), sorted((p[0], p[1]) for p in positions), pre_tag, post_tag)


def byte_to_char_positions(text: str | None, positions: list[list[int]] | None) -> list[list[int]] | None:
    """pg_search returns utf-8 byte offsets; convert them to character offsets"""
    if not text or not positions or text.isascii():
        return positions
    encoded = text.encode("utf-8")
    return [
        [len(encoded[:start].decode("utf-8", "ignore")), len(encoded[:end].decode("utf-8", "ignore"))]
        for start, end in positions
    ]
