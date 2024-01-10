import re
from typing import Tuple


def parse_field(field: str) -> Tuple[str, int, int, int]:
    """
    Parse a field into a field and the snippet parameters.
    The format is fieldname[nomatch_chars;max_matches;match_chars].
    If no snippet parameters are given, the values are None
    """
    pattern = r"\[([0-9]+);([0-9]+);([0-9]+)]$"
    match = re.search(pattern, field)

    if match:
        fieldname = field[: match.start()]
        nomatch_chars = int(match.group(1))
        max_matches = int(match.group(2))
        match_chars = int(match.group(3))
    else:
        fieldname = field
        nomatch_chars = None
        max_matches = None
        match_chars = None

    return fieldname, nomatch_chars, max_matches, match_chars
