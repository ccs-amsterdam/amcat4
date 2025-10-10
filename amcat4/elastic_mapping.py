from typing import Literal, TypedDict, Union, Dict

ElasticType = Literal[
    "text",
    "annotated_text",
    "binary",
    "match_only_text",
    "date",
    "boolean",
    "keyword",
    "constant_keyword",
    "wildcard",
    "integer",
    "byte",
    "short",
    "long",
    "unsigned_long",
    "float",
    "half_float",
    "double",
    "scaled_float",
    "object",
    "flattened",
    "nested",
    "dense_vector",
    "geo_point",
]


class ElasticField(TypedDict):
    type: ElasticType


class ElasticNestedField(TypedDict):
    """
    Use 'object' and 'nested' for nested structures (or "flattened" for untyped object)
        - object: If the field is a dictionary (not an array of dictionaries)
        - nested: If the field is an array of dictionaries
    """

    type: Literal["object", "nested"]
    dynamic: Literal["strict"]
    properties: Dict[str, Union["ElasticField", "ElasticNestedField"]]


ElasticMappingProperties = Dict[str, ElasticField | ElasticNestedField]

# Helper functions to create object and nested fields without too much boilerplate


def object_field(**properties: Union[ElasticField, ElasticNestedField]) -> ElasticNestedField:
    return {"type": "object", "dynamic": "strict", "properties": properties}


def nested_field(**properties: Union[ElasticField, ElasticNestedField]) -> ElasticNestedField:
    return {"type": "nested", "dynamic": "strict", "properties": properties}
