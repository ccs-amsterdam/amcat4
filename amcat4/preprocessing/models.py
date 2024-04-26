import copy
from multiprocessing import Value
from typing import Any, Iterable, List, Optional, Tuple

import httpx
from pydantic import BaseModel

from amcat4 import multimedia
from amcat4.fields import get_fields
from amcat4.preprocessing.task import get_task


class PreprocessingArgument(BaseModel):
    name: str
    field: Optional[str] = None
    value: Optional[str | int | bool | float | List[str] | List[int] | List[float]] = None
    secret: Optional[bool] = False


class PreprocessingOutput(BaseModel):
    name: str
    field: str


class PreprocessingInstruction(BaseModel):
    field: str
    task: str
    endpoint: str
    arguments: List[PreprocessingArgument]
    outputs: List[PreprocessingOutput]

    def build_request(self, index, doc) -> httpx.Request:
        # TODO: validate that instruction is valid for task!
        fields = get_fields(index)
        task = get_task(self.task)
        if task.request.body == "json":
            if not task.request.template:
                raise ValueError(f"Task {task.name} has json body but not template")
            body = copy.deepcopy(task.request.template)
        elif task.request.body == "binary":
            body = None
        else:
            raise NotImplementedError()
        headers = {}
        for argument in self.arguments:
            param = task.get_parameter(argument.name)
            if param.use_field == "yes":
                if not argument.field:
                    raise ValueError("Field not given for field param")
                value = doc.get(argument.field)
                if task.request.body == "binary" and fields[argument.field].type in ["image"]:
                    value = multimedia.get_multimedia_object(index, value)
            else:
                value = argument.value
            if param.header:
                if not param.path:
                    raise ValueError("Path required for header params")
                if ":" in param.path:
                    path, prefix = param.path.split(":", 1)
                    prefix = f"{prefix} "
                else:
                    path, prefix = param.path, ""
                headers[path] = f"{prefix}{value}"
            else:
                if task.request.body == "json":
                    if not param.path:
                        raise ValueError("Path required for json body params")
                    param.parsed.update(body, value)
                elif task.request.body == "binary":
                    if param.path:
                        raise ValueError("Path not allowed for binary body")
                    if body:
                        raise ValueError("Multiple values for body")
                    if type(value) != bytes:
                        raise ValueError("Binary request requires multimedia object")
                    body = value
        if task.request.body == "json":
            return httpx.Request("POST", self.endpoint, json=body, headers=headers)
        else:
            return httpx.Request("POST", self.endpoint, content=body, headers=headers)

    def parse_output(self, output) -> Iterable[Tuple[str, Any]]:
        task = get_task(self.task)
        for arg in self.outputs:
            o = task.get_output(arg.name)
            yield arg.field, o.parsed.find(output)[0].value
