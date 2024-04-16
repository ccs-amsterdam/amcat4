import copy
from typing import Any, Iterable, List, Optional, Tuple

import httpx
from pydantic import BaseModel

from amcat4.preprocessing.task import get_task


class PreprocessingArgument(BaseModel):
    name: str
    field: Optional[str] = None
    value: Optional[str | int | bool | float | List[str] | List[int] | List[float]] = None


class PreprocessingOutput(BaseModel):
    name: str
    field: str


class PreprocessingInstruction(BaseModel):
    field: str
    task: str
    endpoint: str
    arguments: List[PreprocessingArgument]
    outputs: List[PreprocessingOutput]

    def build_request(self, doc) -> httpx.Request:
        # TODO: validate that instruction is valid for task!
        task = get_task(self.task)
        if task.request.body != "json":
            raise NotImplementedError()
        if not task.request.template:
            raise ValueError(f"Task {task.name} has json body but not template")
        body = copy.deepcopy(task.request.template)
        for argument in self.arguments:
            param = task.get_parameter(argument.name)
            if param.use_field == "yes":
                value = doc.get(argument.field)
            else:
                value = argument.value
            param.parsed.update(body, value)

        return httpx.Request("POST", self.endpoint, json=body)

    def parse_output(self, output) -> Iterable[Tuple[str, Any]]:
        task = get_task(self.task)
        for arg in self.outputs:
            o = task.get_output(arg.name)
            yield arg.field, o.parsed.find(output)[0].value
