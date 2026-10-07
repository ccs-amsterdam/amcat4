from amcat4.models import SnippetParams
from amcat4.postgres.snippets import highlight, make_snippet

TEXT = "The quick brown fox jumps over the lazy dog. Later that day, the fox went home to sleep."


def test_nomatch():
    assert make_snippet(TEXT, None, SnippetParams(nomatch_chars=9, max_matches=3, match_chars=20)) == "The quick"
    assert make_snippet(TEXT, [[16, 19]], SnippetParams(nomatch_chars=9, max_matches=0, match_chars=20)) == "The quick"


def test_matches_are_limited():
    positions = [[16, 19], [65, 68]]
    s = make_snippet(TEXT, positions, SnippetParams(nomatch_chars=10, max_matches=1, match_chars=20))
    assert "fox" in s and "..." not in s and len(s) <= 20
    s = make_snippet(TEXT, positions, SnippetParams(nomatch_chars=10, max_matches=2, match_chars=20), "<em>", "</em>")
    assert s.count("<em>fox</em>") == 2 and " ... " in s
    assert len(s.replace("<em>", "").replace("</em>", "")) <= 2 * 20 + len(" ... ")


def test_highlight():
    assert highlight("a fox b", [[2, 5]]) == "a <em>fox</em> b"
