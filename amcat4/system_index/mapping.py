from typing import Mapping, Optional, Type, Literal, TypedDict, Union, List
from pydantic import BaseModel, create_model
from datetime import datetime


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
    properties: Mapping[str, Union['SI_Field', 'SI_NestedField']]


SI_ElasticMapping = Mapping[str, SI_Field | SI_NestedField]

SI_TypeMapping: Mapping[str, Type] = {
    "text": str,
    "keyword": str,
    "float": float,
    "integer": int,
    "boolean": bool,
    "date": datetime,
    "flattened": dict
}


def create_pydantic_model_from_mapping(
    model_name: str, mapping: SI_ElasticMapping
) -> Type[BaseModel]:
    """
    Dynamically creates a Pydantic BaseModel from an Elasticsearch mapping.
    This is used for typesafety in defining the migrations
    """
    pydantic_fields = {}
    for field_name, field_info in mapping.items():
        es_type = field_info["type"]
        python_type: Type

        if es_type in ("object", "nested"):
            nested_properties = field_info.get("properties")
            if not nested_properties:
                raise ValueError(f"Field '{field_name}' of type '{es_type}' must have 'properties' defined.")
            nested_model_name = f"{model_name}_{field_name}"
            nested_model = create_pydantic_model_from_mapping(
                nested_model_name, nested_properties
            )
            python_type = List[nested_model] if es_type == "nested" else nested_model

        else:
            if es_type not in SI_TypeMapping:
                raise ValueError(f"Unsupported Elasticsearch type: {es_type}")
            python_type = SI_TypeMapping[es_type]

        # all fields are optional. we just check the type if they are present
        pydantic_fields[field_name] = (Optional[python_type], None)

    return create_model(model_name, **pydantic_fields)
