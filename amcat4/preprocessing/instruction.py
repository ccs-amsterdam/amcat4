from amcat4.config import get_settings
from amcat4.elastic import es
from amcat4.fields import create_fields, get_fields
from amcat4.preprocessing.models import PreprocessingInstruction
from amcat4.preprocessing.processor import get_manager


def get_instructions(index: str):
    res = es().get(index=get_settings().system_index, id=index, source="preprocessing")
    return res["_source"].get("preprocessing", [])


def add_instruction(index: str, instruction: PreprocessingInstruction):
    if instruction.field in get_fields(index):
        raise ValueError("Field {instruction.field} already exists in index {index}")
    current = get_instructions(index)
    current.append(instruction.model_dump())
    create_fields(index, {instruction.field: "preprocess"})
    es().update(index=get_settings().system_index, id=index, doc=dict(preprocessing=current))
    get_manager().add_preprocessor(index, instruction)
