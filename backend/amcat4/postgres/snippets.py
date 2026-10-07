"""
Snippets for the postgres backend.

Snippets are a security boundary (metareaders may only see snippets of some fields), so we build them
ourselves from the stored text, and enforce the limits here. pg_search is only used to tell us *where*
the query matched (paradedb.snippet_positions), so matching is consistent with the search itself.
"""

from amcat4.models import SnippetParams


def make_snippet(
    text: str | None,
    positions: list[list[int]] | None,
    params: SnippetParams,
    pre_tag: str = "",
    post_tag: str = "",
) -> str:
    """
    Create a snippet from text, given the (start, end) character offsets of query matches.

    - If there are no matches (or max_matches is 0), return the first nomatch_chars characters.
    - Otherwise return at most max_matches fragments of about match_chars characters around the matches,
      joined by " ... ". Overlapping fragments are merged. Fragments are cut at word boundaries if possible.

    The returned text (excluding tags) is never longer than max(nomatch_chars, max_matches * match_chars) plus
    separators.
    """
    if not text:
        return ""
    if not positions or params.max_matches == 0:
        return _cut(text, 0, params.nomatch_chars)

    fragments: list[tuple[int, int, list[tuple[int, int]]]] = []
    for start, end in sorted((p[0], p[1]) for p in positions):
        if fragments and start < fragments[-1][1]:
            # match falls within the previous fragment
            fragments[-1][2].append((start, end))
            continue
        if len(fragments) >= params.max_matches:
            break
        match_len = end - start
        context = max(0, params.match_chars - match_len) // 2
        fstart = max(0, start - context)
        fend = min(len(text), fstart + max(params.match_chars, match_len))
        if match_len > params.match_chars:
            fend = start + params.match_chars
        fragments.append((fstart, fend, [(start, end)]))

    parts = []
    for fstart, fend, matches in fragments:
        fstart, fend = _word_boundaries(text, fstart, fend)
        part, cursor = [], fstart
        for mstart, mend in matches:
            mstart, mend = max(mstart, fstart), min(mend, fend)
            if mstart >= mend:
                continue
            part.append(text[cursor:mstart])
            part.append(pre_tag + text[mstart:mend] + post_tag)
            cursor = mend
        part.append(text[cursor:fend])
        parts.append("".join(part).strip())
    return " ... ".join(parts)


def _word_boundaries(text: str, start: int, end: int) -> tuple[int, int]:
    """Shrink a fragment so it does not start or end in the middle of a word (if that leaves something)"""
    if start > 0 and not text[start - 1].isspace():
        s = text.find(" ", start, end)
        if s != -1:
            start = s + 1
    if end < len(text) and not text[end].isspace():
        e = text.rfind(" ", start, end)
        if e > start:
            end = e
    return start, end


def _cut(text: str, start: int, n: int) -> str:
    if len(text) <= n:
        return text
    return text[start : start + n]


def highlight(
    text: str | None, positions: list[list[int]] | None, pre_tag: str = "<em>", post_tag: str = "</em>"
) -> str | None:
    """Return the full text with query matches wrapped in tags"""
    if not text or not positions:
        return text
    parts, cursor = [], 0
    for start, end in sorted((p[0], p[1]) for p in positions):
        if start < cursor:
            continue
        parts += [text[cursor:start], pre_tag, text[start:end], post_tag]
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)
