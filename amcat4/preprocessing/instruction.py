from typing import Iterable, Optional
from amcat4.config import get_settings
from amcat4.elastic import es
from amcat4.fields import create_fields, get_fields
from amcat4.preprocessing.models import PreprocessingInstruction
from amcat4.preprocessing.processor import get_manager


def get_instructions(index: str) -> Iterable[PreprocessingInstruction]:
    res = es().get(index=get_settings().system_index, id=index, source="preprocessing")
    for i in res["_source"].get("preprocessing", []):
        for a in i.get("arguments", []):
            if a.get("secret"):
                a["value"] = "********"
        yield PreprocessingInstruction.model_validate(i)


def get_instruction(index: str, field: str) -> Optional[PreprocessingInstruction]:
    for i in get_instructions(index):
        if i.field == field:
            return i


def add_instruction(index: str, instruction: PreprocessingInstruction):
    print(instruction)
    if instruction.field in get_fields(index):
        raise ValueError(f"Field {instruction.field} already exists in index {index}")
    instructions = list(get_instructions(index))
    instructions.append(instruction)
    create_fields(index, {instruction.field: "preprocess"})
    body = [i.model_dump() for i in instructions]
    es().update(index=get_settings().system_index, id=index, doc=dict(preprocessing=body))
    get_manager().add_preprocessor(index, instruction)
