"""
Field definitions for the postgres backend.

Each field has a stable storage key ("f<pk>") that is used as the json key in the documents table. The field
name is only a project-level label. This module maps AmCAT field types to storage columns, normalizes values
for storage, and manages the `fields` table.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable, Literal, Mapping

from psycopg import AsyncConnection

from amcat4.models import FieldType

StorageColumn = Literal["text_data", "meta_data", "extra_data"]

# Which jsonb column a field type is stored in. text_data is tokenized, meta_data is exact/columnar,
# extra_data is stored but not indexed.
_STORAGE: dict[str, StorageColumn] = {
    "text": "text_data",
    "keyword": "meta_data",
    "tag": "meta_data",
    "url": "meta_data",
    "image": "meta_data",
    "video": "meta_data",
    "audio": "meta_data",
    "boolean": "meta_data",
    "number": "meta_data",
    "integer": "meta_data",
    "date": "meta_data",
    "object": "extra_data",
    "vector": "extra_data",
    "geo_point": "extra_data",
}


def storage_column(field_type: str) -> StorageColumn:
    try:
        return _STORAGE[field_type]
    except KeyError:
        raise ValueError(f"Unknown field type: {field_type}")


@dataclass(frozen=True)
class FieldInfo:
    pk: int
    name: str
    type: str
    unique_field: bool = False
    primary_date: bool = False

    @property
    def key(self) -> str:
        """The json key under which values are stored"""
        return f"f{self.pk}"

    @property
    def column(self) -> StorageColumn:
        return storage_column(self.type)

    @property
    def path(self) -> str:
        """The field path in the BM25 index, e.g. text_data.f12"""
        return f"{self.column}.{self.key}"

    @property
    def indexed(self) -> bool:
        return self.column != "extra_data"

    def derived_key(self, part: str) -> str:
        """json key of a derived value (e.g. the month of a date field)"""
        return f"{self.key}_{part}"

    def derived_path(self, part: str) -> str:
        return f"{self.column}.{self.derived_key(part)}"


# Derived values that are stored for every date field (as extra keys in meta_data), so that grouping by
# date intervals and filtering on date parts can be done inside the BM25 index (columnar), instead of
# computing them in SQL for every document. pg_search cannot push down expressions like date_trunc.
def _daypart(dt: datetime) -> str:
    return "Night" if dt.hour < 6 else "Morning" if dt.hour < 12 else "Afternoon" if dt.hour < 18 else "Evening"


DATE_DERIVED: dict[str, Callable[[datetime], str | int]] = {
    "year": lambda dt: dt.strftime("%Y"),
    "month": lambda dt: dt.strftime("%Y-%m"),
    "week": lambda dt: (dt.date() - timedelta(days=dt.weekday())).isoformat(),
    "day": lambda dt: dt.strftime("%Y-%m-%d"),
    "yearnr": lambda dt: dt.year,
    "monthnr": lambda dt: dt.month,
    "weeknr": lambda dt: dt.isocalendar().week,
    "dayofmonth": lambda dt: dt.day,
    "dayofweek": lambda dt: dt.strftime("%A"),
    "daypart": _daypart,
    "decade": lambda dt: dt.year // 10 * 10,
}


def parse_date(normalized: str) -> datetime:
    return datetime.fromisoformat(normalized.replace("Z", "+00:00"))


def derived_date_values(f: FieldInfo, normalized: str) -> dict[str, str | int]:
    dt = parse_date(normalized)
    return {f.derived_key(part): fn(dt) for part, fn in DATE_DERIVED.items()}


def normalize_date(value: Any) -> str:
    """
    Normalize a date(time) to a fixed-width UTC RFC3339 string. Tantivy recognizes these as dates in json
    fields (so range queries work), and the fixed width means they also sort correctly as strings.
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError(f"Cannot convert {value!r} to a date")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def normalize_value(value: Any, field_type: str) -> Any:
    """Normalize a value for storage in the documents table"""
    if value is None:
        return None
    match field_type:
        case "text" | "keyword" | "url" | "image" | "video" | "audio":
            return str(value)
        case "tag":
            values = value if isinstance(value, list) else [value]
            return [str(v) for v in values]
        case "number":
            return float(value)
        case "integer":
            return int(value)
        case "boolean":
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return bool(value)
        case "date":
            return normalize_date(value)
        case _:
            return value


async def list_fields(conn: AsyncConnection, project_pk: int) -> dict[str, FieldInfo]:
    cur = await conn.execute(
        "SELECT pk, name, type, unique_field, primary_date FROM fields WHERE project_pk = %s ORDER BY pk", [project_pk]
    )
    rows = await cur.fetchall()
    return {r["name"]: FieldInfo(**r) for r in rows}  # type: ignore[index, call-overload, arg-type]


async def create_fields(
    conn: AsyncConnection, project_pk: int, fields: Mapping[str, FieldType], unique_fields: list[str] | None = None
) -> dict[str, FieldInfo]:
    """
    Create fields that do not exist yet. Existing fields must have the same type.
    (Unlike in elastic, changing a type would only require rewriting the values of this field)

    The first date field of a project becomes its *primary date*: its value is also stored in the
    documents.sort_date column, which (unlike json keys) pg_search can use for fast sorting.
    """
    current = await list_fields(conn, project_pk)
    has_primary_date = any(f.primary_date for f in current.values())
    unique_fields = unique_fields or []
    for name, field_type in fields.items():
        storage_column(field_type)  # validates the type
        if name in current:
            if current[name].type != field_type:
                raise ValueError(f"Field {name!r} already exists with type {current[name].type!r}")
            continue
        primary_date = field_type == "date" and not has_primary_date
        has_primary_date = has_primary_date or primary_date
        await conn.execute(
            "INSERT INTO fields (project_pk, name, type, unique_field, primary_date) VALUES (%s, %s, %s, %s, %s)",
            [project_pk, name, field_type, name in unique_fields, primary_date],
        )
    return await list_fields(conn, project_pk)


async def rename_field(conn: AsyncConnection, project_pk: int, old: str, new: str) -> None:
    """Renaming is a metadata-only operation, because values are stored by field key"""
    await conn.execute("UPDATE fields SET name = %s WHERE project_pk = %s AND name = %s", [new, project_pk, old])


class QueryError(ValueError):
    pass


class FieldSet:
    """
    The fields of one or more projects, as seen by a specific user.

    Field names are resolved per project: the same name can have a different storage key in different projects,
    so resolving a name gives a list of FieldInfo (one per project that has the field). The types must match.

    queryable: names of fields that the user may search/filter on (None = all fields). This is where field-level
    access control plugs in. (Later we may distinguish visible, queryable-but-invisible, and invisible fields.)
    """

    def __init__(self, project_fields: dict[int, dict[str, FieldInfo]], queryable: set[str] | None = None):
        self.project_fields = project_fields
        self.queryable = queryable
        self.by_name: dict[str, list[FieldInfo]] = {}
        for fields in project_fields.values():
            for name, f in fields.items():
                existing = self.by_name.setdefault(name, [])
                if existing and existing[0].type != f.type:
                    raise QueryError(f"Field {name} has different types in different projects")
                existing.append(f)

    @property
    def project_pks(self) -> list[int]:
        return list(self.project_fields.keys())

    def type(self, name: str) -> str:
        return self.by_name[name][0].type

    def resolve(self, name: str) -> list[FieldInfo]:
        fs = self.by_name.get(name)
        if not fs or (self.queryable is not None and name not in self.queryable):
            raise QueryError(f"Unknown field: {name}")
        if not fs[0].indexed:
            raise QueryError(f"Field {name} is not searchable")
        return fs

    def default_fields(self) -> list[FieldInfo]:
        return [
            f
            for name, fs in self.by_name.items()
            if fs[0].type == "text" and (self.queryable is None or name in self.queryable)
            for f in fs
        ]
