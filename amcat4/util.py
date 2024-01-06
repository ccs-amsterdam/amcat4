import re
from typing import Tuple


def parse_snippet(snippet: str) -> Tuple[str, int, int, int]:
    """
    Parse a snippet string into a field and the snippet parameters.
    The format is fieldname[nomatch_chars;max_matches;match_chars].
    If the snippet does not contain parameters (or the specification is wrong),
    we assume the snippet is just the field name and use default values.
    """
    pattern = r"\[([0-9]+);([0-9]+);([0-9]+)]$"
    match = re.search(pattern, snippet)

    if match:
        field = snippet[: match.start()]
        nomatch_chars = int(match.group(1))
        max_matches = int(match.group(2))
        match_chars = int(match.group(3))
    else:
        field = snippet
        nomatch_chars = 200
        max_matches = 3
        match_chars = 50

    return field, nomatch_chars, max_matches, match_chars
