"""
Query string parsing for the postgres backend.

Users write Lucene-like query strings. We parse these ourselves (instead of passing them to the pg_search
query parser) and compile them to pg_search's structured json query language, because:

- Field names are project-level labels that need to be translated to storage paths ("title" -> "text_data.f12")
- We need to control which fields can be queried (field-level access), including which fields are searched
  when no field is given (pg_search does not search 'all keys' of a json field)
- The pg_search query parser does not support all syntax on json fields (e.g. wildcards, phrase slop, dates),
  while the structured queries do.

Supported syntax:
    word                 match word in default fields
    field:word           match word in a specific field
    "a phrase"           phrase query,       "a phrase"~3 phrase with slop
    immigr*              prefix query (only trailing wildcards)
    word~1               fuzzy query (edit distance 1, max 2)
    word^2               boost
    a AND b, a OR b      boolean operators (must be uppercase). Juxtaposition uses the default operator (OR)
    NOT a, -a, +a        exclusion / requirement
    ( ... )              grouping, also field:(a OR b)
    field:[a TO b]       inclusive range ({a TO b} for exclusive, * for open ended)
    field:>a, field:>=a, field:<a, field:<=a
"""

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, Sequence

from amcat4.postgres.fields import FieldInfo, FieldSet, QueryError, normalize_value

Occur = Literal["must", "should", "must_not"]

__all__ = ["QueryError", "FieldSet", "parse_query", "compile_query", "query_string_to_json", "range_query"]


class FieldResolver(Protocol):
    def resolve(self, name: str) -> Sequence[FieldInfo]:
        """Return the field with this name. Raise QueryError if it does not exist or may not be queried"""
        ...

    def default_fields(self) -> Sequence[FieldInfo]:
        """Fields that are searched if a query does not specify a field"""
        ...


# ------------------------------------------------------------------ AST


@dataclass
class Term:
    field: str | None
    text: str
    fuzzy: int | None = None
    boost: float | None = None

    @property
    def prefix(self) -> bool:
        return self.text.endswith("*")


@dataclass
class Phrase:
    field: str | None
    text: str
    slop: int = 0
    boost: float | None = None


@dataclass
class Range:
    field: str
    lower: str | None
    upper: str | None
    include_lower: bool = True
    include_upper: bool = True


@dataclass
class Bool:
    clauses: list[tuple[Occur, "Node"]] = field(default_factory=list)


Node = Term | Phrase | Range | Bool


# ------------------------------------------------------------------ Lexer

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<lparen>\()
  | (?P<rparen>\))
  | (?P<range>[\[{]\s*(?P<lo>"[^"]*"|\S+)\s+TO\s+(?P<hi>"[^"]*"|[^\s\]}]+)\s*[\]}])
  | (?P<phrase>"(?:[^"\\]|\\.)*")(?:~(?P<slop>\d+))?(?:\^(?P<pboost>\d+(?:\.\d+)?))?
  | (?P<cmp>(?:>=|<=|>|<))
  | (?P<colon>:)
  | (?P<plus>\+)
  | (?P<minus>-)
  | (?P<word>(?:[^\s()":\[\]{}\\^~]|\\.)+)(?:~(?P<fuzzy>\d*))?(?:\^(?P<boost>\d+(?:\.\d+)?))?
    """,
    re.VERBOSE,
)


@dataclass
class Token:
    kind: str
    value: Any
    pos: int
    preceded_by_space: bool


def _unescape(s: str) -> str:
    return re.sub(r"\\(.)", r"\1", s)


def tokenize(q: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    space = True
    while pos < len(q):
        m = _TOKEN_RE.match(q, pos)
        if not m:
            raise QueryError(f"Cannot parse query at position {pos}: {q[pos : pos + 20]!r}")
        kind = ""
        if m.group("ws"):
            space = True
            pos = m.end()
            continue
        if m.group("range") is not None:
            kind = "range"
            value: Any = (
                m.group("range")[0] == "[",
                _strip_quotes(m.group("lo")),
                _strip_quotes(m.group("hi")),
                m.group("range")[-1] == "]",
            )
        elif m.group("phrase") is not None:
            kind = "phrase"
            value = (_unescape(m.group("phrase")[1:-1]), m.group("slop"), m.group("pboost"))
        elif m.group("word") is not None:
            kind = "word"
            value = (m.group("word"), m.group("fuzzy"), m.group("boost"))
            if value[0] in ("AND", "OR", "NOT", "&&", "||") and value[1] is None and value[2] is None:
                kind = {"&&": "AND", "||": "OR"}.get(value[0]) or str(value[0])
        else:
            value = m.group(0)
            kind = next(k for k in ("lparen", "rparen", "cmp", "colon", "plus", "minus") if m.group(k) is not None)
        tokens.append(Token(kind, value, pos, space))
        space = False
        pos = m.end()
    return tokens


def _strip_quotes(s: str) -> str:
    return s[1:-1] if len(s) >= 2 and s[0] == s[-1] == '"' else s


# ------------------------------------------------------------------ Parser


class _Parser:
    def __init__(self, q: str, default_operator: Literal["AND", "OR"] = "OR"):
        self.q = q
        self.tokens = tokenize(q)
        self.i = 0
        self.default_occur: Occur = "must" if default_operator == "AND" else "should"

    def peek(self, offset: int = 0) -> Token | None:
        j = self.i + offset
        return self.tokens[j] if j < len(self.tokens) else None

    def next(self) -> Token:
        t = self.peek()
        if t is None:
            raise QueryError("Unexpected end of query")
        self.i += 1
        return t

    def expect(self, kind: str) -> Token:
        t = self.next()
        if t.kind != kind:
            raise QueryError(f"Expected {kind} at position {t.pos}, got {t.value!r}")
        return t

    def parse(self) -> Node:
        node = self.parse_sequence(None)
        if self.peek() is not None:
            t = self.peek()
            raise QueryError(f"Unexpected {t.value!r} at position {t.pos}")  # type: ignore[union-attr]
        return node

    def parse_sequence(self, fieldname: str | None) -> Node:
        """A sequence of OR-expressions combined with the default operator"""
        clauses: list[tuple[Occur, Node]] = []
        while (t := self.peek()) is not None and t.kind != "rparen":
            clauses.append(self.parse_or(fieldname))
        if not clauses:
            raise QueryError("Empty query")
        return _simplify(Bool([(occur if occur != "should" else self.default_occur, n) for occur, n in clauses]))

    def parse_or(self, fieldname: str | None) -> tuple[Occur, Node]:
        first = self.parse_and(fieldname)
        items = [first]
        while (t := self.peek()) is not None and t.kind == "OR":
            self.next()
            items.append(self.parse_and(fieldname))
        if len(items) == 1:
            return first
        return "should", _simplify(Bool([(("should" if o == "must" else o), n) for o, n in items]))

    def parse_and(self, fieldname: str | None) -> tuple[Occur, Node]:
        first = self.parse_unary(fieldname)
        items = [first]
        while (t := self.peek()) is not None and t.kind == "AND":
            self.next()
            items.append(self.parse_unary(fieldname))
        if len(items) == 1:
            return first
        return "should", _simplify(Bool([(("must" if o == "should" else o), n) for o, n in items]))

    def parse_unary(self, fieldname: str | None) -> tuple[Occur, Node]:
        t = self.peek()
        if t is None:
            raise QueryError("Unexpected end of query")
        if t.kind in ("NOT", "minus"):
            self.next()
            _, node = self.parse_unary(fieldname)
            return "must_not", node
        if t.kind == "plus":
            self.next()
            _, node = self.parse_unary(fieldname)
            return "must", node
        return "should", self.parse_primary(fieldname)

    def parse_primary(self, fieldname: str | None) -> Node:
        t = self.next()
        if t.kind == "lparen":
            node = self.parse_sequence(fieldname)
            self.expect("rparen")
            return node
        if t.kind == "word" and (nxt := self.peek()) is not None and nxt.kind == "colon" and not nxt.preceded_by_space:
            if fieldname is not None:
                raise QueryError(f"Nested field specification at position {t.pos}")
            word, fuzzy, boost = t.value
            if fuzzy is not None or boost is not None:
                raise QueryError(f"Invalid field name at position {t.pos}")
            self.next()  # colon
            return self.parse_field_value(_unescape(word))
        return self.parse_value(t, fieldname)

    def parse_field_value(self, fieldname: str) -> Node:
        t = self.next()
        if t.kind == "lparen":
            node = self.parse_sequence(fieldname)
            self.expect("rparen")
            return node
        if t.kind == "range":
            incl_lo, lo, hi, incl_hi = t.value
            return Range(fieldname, None if lo == "*" else lo, None if hi == "*" else hi, incl_lo, incl_hi)
        if t.kind == "cmp":
            v = self.next()
            if v.kind == "word":
                value = _unescape(v.value[0])
            elif v.kind == "phrase":
                value = v.value[0]
            else:
                raise QueryError(f"Expected a value after {t.value} at position {v.pos}")
            op = t.value
            if op.startswith(">"):
                return Range(fieldname, value, None, include_lower=op == ">=")
            return Range(fieldname, None, value, include_upper=op == "<=")
        return self.parse_value(t, fieldname)

    def parse_value(self, t: Token, fieldname: str | None) -> Node:
        if t.kind == "word":
            word, fuzzy, boost = t.value
            return Term(
                fieldname,
                _unescape(word),
                fuzzy=None if fuzzy is None else int(fuzzy or 2),
                boost=float(boost) if boost else None,
            )
        if t.kind == "phrase":
            text, slop, boost = t.value
            return Phrase(fieldname, text, slop=int(slop or 0), boost=float(boost) if boost else None)
        raise QueryError(f"Unexpected {t.value!r} at position {t.pos}")


def _simplify(node: Bool) -> Node:
    """Remove unnecessary nesting: a bool with a single positive clause is just that clause"""
    if len(node.clauses) == 1 and node.clauses[0][0] != "must_not":
        return node.clauses[0][1]
    return node


def parse_query(q: str, default_operator: Literal["AND", "OR"] = "OR") -> Node:
    return _Parser(q, default_operator).parse()


# ------------------------------------------------------------------ Compiler

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def _boost(query: dict, boost: float | None) -> dict:
    if boost is None:
        return query
    return {"boost": {"query": query, "factor": boost}}


def _any_of(queries: list[dict]) -> dict:
    if len(queries) == 1:
        return queries[0]
    return {"boolean": {"should": queries}}


def compile_query(node: Node, resolver: FieldResolver) -> dict:
    """Compile a parsed query into a pg_search json query"""
    if isinstance(node, Term) and node.text == "*" and node.field is None:
        return {"all": None}
    if isinstance(node, Bool):
        out: dict[str, list] = {"must": [], "should": [], "must_not": []}
        for occur, child in node.clauses:
            out[occur].append(compile_query(child, resolver))
        if not out["must"] and not out["should"]:
            out["must"].append({"all": None})
        return {"boolean": {k: v for k, v in out.items() if v}}

    fieldname = node.field
    if fieldname is None:
        if isinstance(node, Range):
            raise QueryError("Range queries need a field")
        fields = resolver.default_fields()
        if not fields:
            raise QueryError("No default fields to search, please specify a field")
        return _any_of([_compile_leaf(node, f) for f in fields])
    return _any_of([_compile_leaf(node, f) for f in resolver.resolve(fieldname)])


def _compile_leaf(node: Term | Phrase | Range, f: FieldInfo) -> dict:
    if f.type == "text":
        return _compile_text(node, f)
    return _compile_exact(node, f)


def _compile_text(node: Term | Phrase | Range, f: FieldInfo) -> dict:
    path = f.path
    if isinstance(node, Range):
        raise QueryError(f"Range queries are not supported on text field {f.name}")
    if isinstance(node, Term):
        text = node.text
        if "?" in text or "*" in text.rstrip("*"):
            raise QueryError(f"Wildcards are only supported at the end of a word (e.g. econom*), not in {text!r}")
        if node.prefix:
            words = _words(text.rstrip("*"))
            if len(words) != 1:
                raise QueryError(f"Invalid prefix query: {text}")
            return _boost(_prefix_query(path, words[0]), node.boost)
        if node.fuzzy is not None:
            words = _words(text)
            if len(words) != 1:
                raise QueryError(f"Invalid fuzzy query: {text}")
            return _boost({"fuzzy_term": {"field": path, "value": words[0], "distance": min(node.fuzzy, 2)}}, node.boost)
        return _boost({"match": {"field": path, "value": text}}, node.boost)
    # phrase
    prefix = node.text.rstrip().endswith("*")
    if "?" in node.text or "*" in node.text.rstrip().rstrip("*"):
        raise QueryError(f'Wildcards are only supported at the end of a phrase (e.g. "house of repr*"), not in {node.text!r}')
    words = _words(node.text)
    if not words:
        raise QueryError(f"Empty phrase: {node.text!r}")
    if prefix and node.slop and len(words) > 1:
        # pg_search has no phrase_prefix with slop, and regex_phrase does not work on json fields
        raise QueryError(f"Wildcards cannot be combined with proximity (~) in phrase {node.text!r}")
    if prefix:
        return _boost({"phrase_prefix": {"field": path, "phrases": words}}, node.boost)
    if len(words) == 1:
        return _boost({"match": {"field": path, "value": words[0]}}, node.boost)
    return _boost({"phrase": {"field": path, "phrases": words, "slop": node.slop}}, node.boost)


def _prefix_query(path: str, prefix: str) -> dict:
    return {"phrase_prefix": {"field": path, "phrases": [prefix]}}


def _compile_exact(node: Term | Phrase | Range, f: FieldInfo) -> dict:
    path = f.path
    if isinstance(node, Range):
        return range_query(f, node.lower, node.upper, node.include_lower, node.include_upper)
    value = node.text
    if isinstance(node, Term) and node.prefix and f.type in ("keyword", "tag", "url"):
        stem = value.rstrip("*")
        return {"range": {"field": path, "lower_bound": {"included": stem}, "upper_bound": {"excluded": stem + "￿"}}}
    if f.type == "date":
        # A date without time matches the whole day
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return range_query(f, value, value + "T23:59:59.999999", True, True)
        return range_query(f, value, value, True, True)
    try:
        normalized = normalize_value(value, f.type)
    except ValueError as e:
        raise QueryError(f"Invalid value for field {f.name}: {value!r}") from e
    if isinstance(normalized, list):
        normalized = normalized[0]
    return {"term": {"field": path, "value": normalized}}


def range_query(f: FieldInfo, lower: Any, upper: Any, include_lower: bool = True, include_upper: bool = True) -> dict:
    if f.type not in ("number", "integer", "date", "keyword", "tag", "url"):
        raise QueryError(f"Range queries are not supported on {f.type} field {f.name}")

    def bound(value: Any, inclusive: bool) -> dict | None:
        if value is None:
            return None
        try:
            v = normalize_value(value, f.type)
        except ValueError as e:
            raise QueryError(f"Invalid value for field {f.name}: {value!r}") from e
        if isinstance(v, list):
            v = v[0]
        return {"included" if inclusive else "excluded": v}

    q: dict[str, Any] = {
        "field": f.path,
        "lower_bound": bound(lower, include_lower),
        "upper_bound": bound(upper, include_upper),
    }
    if f.type == "date":
        q["is_datetime"] = True
    return {"range": q}


def query_string_to_json(q: str, resolver: FieldResolver, default_operator: Literal["AND", "OR"] = "OR") -> dict:
    return compile_query(parse_query(q, default_operator), resolver)


# ------------------------------------------------------------------ Highlighting


@dataclass
class ProximityPattern:
    """
    Matches a phrase with slop ("a b"~n), following tantivy: each next word must be within slop positions of
    where it would be in the exact phrase, in either direction. Finds the positions of the matched words.
    """

    words: list[str]
    slop: int

    def spans(self, text: str) -> list[tuple[int, int]]:
        tokens = [(m.group().lower(), m.start(), m.end()) for m in _WORD_RE.finditer(text)]
        positions: dict[str, list[int]] = {}
        for i, (word, _, _) in enumerate(tokens):
            positions.setdefault(word, []).append(i)

        def extend(chain: list[int]) -> list[int] | None:
            if len(chain) == len(self.words):
                return chain
            expected = chain[-1] + 1
            candidates = [p for p in positions.get(self.words[len(chain)], []) if abs(p - expected) <= self.slop]
            for p in sorted(candidates, key=lambda p: abs(p - expected)):
                if p not in chain and (result := extend([*chain, p])):
                    return result
            return None

        spans = []
        for start in positions.get(self.words[0], []):
            if chain := extend([start]):
                spans.extend((tokens[i][1], tokens[i][2]) for i in chain)
        return sorted(set(spans))


HighlightPattern = re.Pattern | ProximityPattern


def highlight_patterns(node: Node, field: str, default_field: bool) -> list[HighlightPattern]:
    """
    Patterns that match the (positive) terms of the query in the given field. Used to find match
    positions for highlighting and snippets. default_field: whether the field is searched for terms without field.
    """
    patterns: list[HighlightPattern] = []

    def visit(n: Node, negated: bool):
        if isinstance(n, Bool):
            for occur, child in n.clauses:
                visit(child, negated or occur == "must_not")
            return
        if negated or isinstance(n, Range):
            return
        if not (n.field == field or (n.field is None and default_field)):
            return
        prefix = n.text.rstrip().endswith("*")
        words = _words(n.text.rstrip("*"))
        if not words or (isinstance(n, Term) and n.fuzzy is not None):
            return
        if isinstance(n, Phrase) and n.slop and len(words) > 1:
            patterns.append(ProximityPattern(words, n.slop))
            return
        body = r"\W+".join(re.escape(w) for w in words)
        suffix = r"\w*" if prefix else ""
        patterns.append(re.compile(rf"(?<!\w){body}{suffix}(?!\w)", re.IGNORECASE))

    visit(node, False)
    return patterns


def match_positions(text: str, patterns: list[HighlightPattern]) -> list[list[int]]:
    positions = []
    for pattern in patterns:
        if isinstance(pattern, ProximityPattern):
            positions.extend([start, end] for start, end in pattern.spans(text))
        else:
            positions.extend([m.start(), m.end()] for m in pattern.finditer(text))
    return positions
