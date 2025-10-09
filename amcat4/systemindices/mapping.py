from typing import Literal, TypedDict, Mapping, Union, Dict


class SI_Field(TypedDict):
    """
    An Elasticsearch field mapping for the system index. Deliberately limits the types.
    """

    type: Literal["text", "keyword", "float", "integer", "boolean", "date", "flattened"]


class SI_NestedField(TypedDict):
    """
    Use 'object' and 'nested' for nested structures (or "flattened" for untyped object)
        - object: If the field is a dictionary (not an array of dictionaries)
        - nested: If the field is an array of dictionaries
    """

    type: Literal["object", "nested"]
    dynamic: Literal["strict"]
    properties: Dict[str, Union["SI_Field", "SI_NestedField"]]


SI_ElasticMapping = Dict[str, SI_Field | SI_NestedField]
