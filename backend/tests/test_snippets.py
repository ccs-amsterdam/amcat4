from amcat4.models import SnippetParams
from amcat4.postgres.snippets import byte_to_char_positions, highlight, make_snippet

TEXT = "The quick brown fox jumps over the lazy dog. Later that day, the fox went home to sleep."


def test_nomatch():
    # without matches (or with max_matches=0), the snippet is the first nomatch_words words
    assert make_snippet(TEXT, None, SnippetParams(nomatch_words=2, max_matches=3, words_per_match=5)) == "The quick"
    assert make_snippet(TEXT, [[16, 19]], SnippetParams(nomatch_words=2, max_matches=0)) == "The quick"
    assert make_snippet(TEXT, None, SnippetParams(nomatch_words=0)) == ""


def test_matches_are_limited():
    positions = [[16, 19], [65, 68]]
    s = make_snippet(TEXT, positions, SnippetParams(max_matches=1, words_per_match=3))
    assert s == "brown fox jumps"
    s = make_snippet(TEXT, positions, SnippetParams(max_matches=2, words_per_match=3), "<em>", "</em>")
    assert s == "brown <em>fox</em> jumps ... the <em>fox</em> went"
    # overlapping fragments are merged
    s = make_snippet(TEXT, [[16, 19], [20, 25]], SnippetParams(max_matches=2, words_per_match=3), "<em>", "</em>")
    assert s == "brown <em>fox</em> <em>jumps</em>"


def test_highlight():
    assert highlight("a fox b", [[2, 5]]) == "a <em>fox</em> b"


def test_byte_to_char_positions():
    assert byte_to_char_positions("Café über fox", [[12, 15]]) == [[10, 13]]
    assert byte_to_char_positions("plain fox", [[6, 9]]) == [[6, 9]]
