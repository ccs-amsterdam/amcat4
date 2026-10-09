"""
Field definitions for the postgres backend.

Each field has a stable storage key ("f<pk>") that is used as the json key in the documents table. The field
name is only a project-level label. This module maps AmCAT field types to storage columns, normalizes values
for storage, and has low-level functions for the `fields` table (see amcat4.systemdata.fields for the API layer).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable, Literal

from psycopg import AsyncConnection

StorageColumn = Literal["text_fields", "exact_fields", "stored_fields", "vector"]
SortSlot = Literal["date", "source"]

# Which jsonb column a field type is stored in. text_fields is tokenized, exact_fields is exact/columnar,
# stored_fields is stored but not indexed. Vectors are stored in the document_vectors table.
_STORAGE: dict[str, StorageColumn] = {
    "text": "text_fields",
    "keyword": "exact_fields",
    "tag": "exact_fields",
    "url": "exact_fields",
    "image": "exact_fields",
    "video": "exact_fields",
    "audio": "exact_fields",
    "boolean": "exact_fields",
    "number": "exact_fields",
    "integer": "exact_fields",
    "date": "exact_fields",
    "geo_point": "exact_fields",
    "object": "stored_fields",
    "vector": "vector",
}

# Which sort slot (standard metadata column, which makes sorting fast) a field type can use
_SORT_SLOTS: dict[str, SortSlot] = {
    "date": "date",
    "keyword": "source",
}


def sort_slot_for_type(field_type: str) -> SortSlot | None:
    return _SORT_SLOTS.get(field_type)


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
    unique: bool = False
    sort_slot: str | None = None
    subkey: str | None = None  # for sub-fields, e.g. the lat/lon of a geo_point

    @property
    def key(self) -> str:
        """The json key under which values are stored"""
        return f"f{self.pk}.{self.subkey}" if self.subkey else f"f{self.pk}"

    @property
    def column(self) -> StorageColumn:
        return storage_column(self.type)

    @property
    def path(self) -> str:
        """The field path in the BM25 index, e.g. text_fields.f12"""
        return f"{self.column}.{self.key}"

    @property
    def indexed(self) -> bool:
        return self.column in ("text_fields", "exact_fields")

    @property
    def sort_column(self) -> str | None:
        """The standard metadata column in the documents table this field is copied to, for fast sorting (if any)"""
        return self.sort_slot

    def derived_key(self, part: str) -> str:
        """json key of a derived value (e.g. the month of a date field)"""
        return f"{self.key}_{part}"

    def derived_path(self, part: str) -> str:
        return f"{self.column}.{self.derived_key(part)}"


# Derived values that are stored for every date field (as extra keys in exact_fields), so that grouping by
# date intervals and filtering on date parts can be done inside the BM25 index (columnar), instead of
# computing them in SQL for every document. pg_search cannot push down expressions like date_trunc.
def _daypart(dt: datetime) -> str:
    return "Night" if dt.hour < 6 else "Morning" if dt.hour < 12 else "Afternoon" if dt.hour < 18 else "Evening"


DATE_DERIVED: dict[str, Callable[[datetime], str | int]] = {
    "year": lambda dt: f"{dt.year:04d}",
    "month": lambda dt: f"{dt.year:04d}-{dt.month:02d}",
    "week": lambda dt: (dt.date() - timedelta(days=dt.weekday())).isoformat(),
    "day": lambda dt: dt.date().isoformat(),
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
    dt = dt.astimezone(UTC)
    # (not strftime, because that does not zero-pad years < 1000 on all platforms)
    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}T{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}.{dt.microsecond:06d}Z"


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
        case "geo_point":
            return normalize_geo(value)
        case "vector":
            if not isinstance(value, list) or not all(isinstance(v, (int, float)) for v in value):
                raise ValueError(f"A vector should be a list of numbers, got {value!r}")
            return [float(v) for v in value]
        case _:
            return value


def normalize_geo(value: Any) -> dict[str, float]:
    """
    Normalize a geo point to {"lat": .., "lon": ..}. Accepts a dict with lat/lon, a "lat,lon" string,
    or a [lon, lat] list (GeoJSON order, as in elasticsearch). Stored as two numbers, so bounding box
    filters can use range queries on <field>.lat and <field>.lon
    """
    if isinstance(value, dict) and "lat" in value and "lon" in value:
        lat, lon = value["lat"], value["lon"]
    elif isinstance(value, str) and "," in value:
        lat, lon = value.split(",", 1)
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        lon, lat = value
    else:
        raise ValueError(f"Cannot interpret {value!r} as a geo point")
    lat, lon = float(lat), float(lon)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"Invalid geo point: lat={lat}, lon={lon}")
    return {"lat": lat, "lon": lon}


FIELD_COLUMNS = "pk, name, type, unique_field, sort_slot"


def field_info_from_row(row: dict) -> FieldInfo:
    return FieldInfo(pk=row["pk"], name=row["name"], type=row["type"], unique=row["unique_field"], sort_slot=row["sort_slot"])


async def list_field_infos(conn: AsyncConnection, project_pk: int) -> dict[str, FieldInfo]:
    cur = await conn.execute(f"SELECT {FIELD_COLUMNS} FROM fields WHERE project_pk = %s ORDER BY pk", [project_pk])  # type: ignore[arg-type]
    return {r["name"]: field_info_from_row(r) for r in await cur.fetchall()}  # type: ignore[index, call-overload, arg-type]


class QueryError(ValueError):
    pass


class FieldSet:
    """
    The fields of one or more projects, as seen by a specific user.

    Field names are resolved per project: the same name can have a different storage key in different projects,
    so resolving a name gives a list of FieldInfo (one per project that has the field). The types must match.

    queryable: names of fields that the user may search/filter on (None = all fields). This is where field-level
    access control plugs in. (Later we may distinguish visible, queryable-but-invisible, and invisible fields.)
    partitions: the documents partition of each project (needed for searching, see amcat4.postgres.layout)
    """

    def __init__(
        self,
        project_fields: dict[int, dict[str, FieldInfo]],
        queryable: set[str] | None = None,
        partitions: dict[int, int] | None = None,
    ):
        self.project_fields = project_fields
        self.queryable = queryable
        self.partitions = partitions or {}
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

    def partition(self, project_pk: int) -> int:
        if project_pk not in self.partitions:
            raise ValueError(f"Partition of project {project_pk} is unknown")
        return self.partitions[project_pk]

    def type(self, name: str) -> str:
        return self.by_name[name][0].type

    def resolve(self, name: str) -> list[FieldInfo]:
        if name not in self.by_name and "." in name:
            return self._resolve_subfield(name)
        fs = self.by_name.get(name)
        if not fs or (self.queryable is not None and name not in self.queryable):
            raise QueryError(f"Unknown field: {name} (field does not exist, or you cannot search it)")
        if not fs[0].indexed:
            raise QueryError(f"Field {name} is not searchable")
        return fs

    def _resolve_subfield(self, name: str) -> list[FieldInfo]:
        """Sub-fields: the latitude and longitude of a geo_point (e.g. location.lat), which can be filtered as numbers"""
        base, sub = name.rsplit(".", 1)
        fs = self.resolve(base)
        if fs[0].type != "geo_point" or sub not in ("lat", "lon"):
            raise QueryError(f"Unknown field: {name} (field does not exist, or you cannot search it)")
        return [FieldInfo(pk=f.pk, name=name, type="number", subkey=sub) for f in fs]

    def default_fields(self) -> list[FieldInfo]:
        return [
            f
            for name, fs in self.by_name.items()
            if fs[0].type == "text" and (self.queryable is None or name in self.queryable)
            for f in fs
        ]
