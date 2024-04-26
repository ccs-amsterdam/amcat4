import functools
from multiprocessing import Value
from re import I
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel
import jsonpath_ng

from amcat4.models import FieldType

"""
https://huggingface.co/docs/api-inference/detailed_parameters

"""


class PreprocessingRequest(BaseModel):
    body: Literal["json", "binary"]
    template: Optional[dict] = None


class PreprocessingSetting(BaseModel):
    name: str
    type: str = "string"
    path: Optional[str] = None

    @functools.cached_property
    def parsed(self) -> jsonpath_ng.JSONPath:
        return jsonpath_ng.parse(self.path)


class PreprocessingOutput(PreprocessingSetting):
    recommended_type: FieldType


class PreprocessingParameter(PreprocessingSetting):
    use_field: Literal["yes", "no"] = "no"
    default: Optional[bool | str | int | float] = None
    placeholder: Optional[str] = None
    header: Optional[bool] = None
    secret: Optional[bool] = False


class PreprocessingEndpoint(BaseModel):
    placeholder: str
    domain: List[str]


class PreprocessingTask(BaseModel):
    """Form for query metadata."""

    name: str
    endpoint: PreprocessingEndpoint
    parameters: List[PreprocessingParameter]
    outputs: List[PreprocessingOutput]
    request: PreprocessingRequest

    def get_parameter(self, name) -> PreprocessingParameter:
        # TODO should probably cache this
        for param in self.parameters:
            if param.name == name:
                return param
        raise ValueError(f"Parameter {name} not defined on task {self.name}")

    def get_output(self, name) -> PreprocessingOutput:
        # TODO should probably cache this
        for output in self.outputs:
            if output.name == name:
                return output
        raise ValueError(f"Parameter {name} not defined on task {self.name}")


TASKS: List[PreprocessingTask] = [
    PreprocessingTask(
        # https://huggingface.co/docs/api-inference/detailed_parameters#zero-shot-classification-task
        name="HuggingFace Zero-Shot",
        endpoint=PreprocessingEndpoint(
            placeholder="https://api-inference.huggingface.co/models/facebook/bart-large-mnli",
            domain=["huggingface.co", "huggingfacecloud.com"],
        ),
        parameters=[
            PreprocessingParameter(name="input", type="string", use_field="yes", path="$.inputs"),
            PreprocessingParameter(
                name="candidate_labels",
                type="string[]",
                use_field="no",
                placeholder="politics, sports",
                path="$.parameters.candidate_labels",
            ),
            PreprocessingParameter(
                name="Huggingface Token",
                type="string",
                use_field="no",
                header=True,
                path="Authorization:Bearer",
                secret=True,
            ),
        ],
        outputs=[PreprocessingOutput(name="label", recommended_type="keyword", path="$.labels[0]")],
        request=PreprocessingRequest(body="json", template={"inputs": "", "parameters": {"candidate_labels": ""}}),
    ),
    PreprocessingTask(
        # https://huggingface.co/docs/api-inference/detailed_parameters#zero-shot-classification-task
        name="HuggingFace Image Classification",
        endpoint=PreprocessingEndpoint(
            placeholder="https://api-inference.huggingface.co/models/google/vit-base-patch16-224",
            domain=["huggingface.co", "huggingfacecloud.com"],
        ),
        parameters=[
            PreprocessingParameter(name="input", type="image", use_field="yes"),
            PreprocessingParameter(
                name="Huggingface Token",
                type="string",
                use_field="no",
                header=True,
                path="Authorization:Bearer",
                secret=True,
            ),
        ],
        outputs=[PreprocessingOutput(name="label", recommended_type="keyword", path="$[0].label")],
        request=PreprocessingRequest(body="binary"),
    ),
]


@functools.cache
def get_task(name):
    for task in TASKS:
        if task.name == name:
            return task
    raise ValueError(f"Task {task} not defined")


def get_tasks():
    return TASKS
