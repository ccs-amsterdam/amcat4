# given an elastic field type, Check if it is supported by AmCAT.
# this is not just the inverse of TYPEMAP_AMCAT_TO_ES because some AmCAT types map to multiple elastic
# types (e.g., tag and keyword, image_url and wildcard)
# (this is relevant if we are importing an index)
from typing import Any

from amcat4.models import ElasticType, FieldType, MultimediaElasticMapping

# This needs to be a one on one mapping. It should be
# possible to uniquely determine the AmCAT type from the elastic type.
_TYPEMAP_ES_TO_AMCAT: dict[ElasticType, FieldType] = {
    # TEXT fields
    "text": "text",
    "annotated_text": "text",
    "binary": "text",
    "match_only_text": "text",
    # DATE fields
    "date": "date",
    # BOOLEAN fields
    "boolean": "boolean",
    # KEYWORD fields
    "keyword": "keyword",
    "constant_keyword": "keyword",
    "wildcard": "keyword",
    # INTEGER fields
    "integer": "number",
    "byte": "number",
    "short": "number",
    "long": "number",
    "unsigned_long": "number",
    # NUMBER fields
    "float": "number",
    "half_float": "number",
    "double": "number",
    "scaled_float": "number",
    # OBJECT fields
    "object": "object",
    "flattened": "object",
    "nested": "object",
    # VECTOR fields (exclude sparse vectors?)
    "dense_vector": "vector",
    # GEO fields
    "geo_point": "geo_point",
}

# maps amcat field types to elastic field types.
# The first elastic type in the array is the default.
_TYPEMAP_AMCAT_TO_ES: dict[FieldType, list[ElasticType]] = {
    "text": ["text", "annotated_text", "binary", "match_only_text"],
    "date": ["date"],
    "boolean": ["boolean"],
    "keyword": ["keyword", "constant_keyword", "wildcard"],
    "number": ["double", "float", "half_float", "scaled_float"],
    "integer": ["long", "integer", "byte", "short", "unsigned_long"],
    # "object": ["flattened", "object", "nested"],
    "object": ["flattened"],
    "vector": ["dense_vector"],
    "geo_point": ["geo_point"],
    "tag": ["keyword", "wildcard"],
    "url": ["wildcard", "keyword", "constant_keyword", "text"],
    # MULTIMEDIA OBJECTS
    "image": ["object"],
    "video": ["object"],
    "audio": ["object"],
}


def list_allowed_elastic_types(field_type: FieldType) -> list[ElasticType]:
    return _TYPEMAP_AMCAT_TO_ES.get(field_type, [])


def infer_field_type(elastic_type: ElasticType, properties: dict[str, Any] | None) -> FieldType:
    """
    Infer the amcat field type from the elastic type and (if applicable) properties (e.g.
    if elastic type is object)
    """

    type = _TYPEMAP_ES_TO_AMCAT.get(elastic_type)
    if type is None:
        raise ValueError(f"Cannot infer amcat field type from elastic type {elastic_type}")
    return type
