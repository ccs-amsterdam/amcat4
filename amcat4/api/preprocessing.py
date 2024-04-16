from fastapi import APIRouter, Depends, Response, status

from amcat4 import index
from amcat4.api.auth import authenticated_user, check_role
from amcat4.preprocessing.instruction import PreprocessingInstruction, get_instructions, add_instruction
from amcat4.preprocessing.task import get_tasks


app_preprocessing = APIRouter(tags=["preprocessing"])


@app_preprocessing.get("/preprocessing_tasks")
def list_tasks():
    print(get_tasks())
    print([t.model_dump() for t in get_tasks()])
    return [t.model_dump() for t in get_tasks()]


@app_preprocessing.get("/index/{ix}/preprocessing")
def list_instructions(ix: str, user: str = Depends(authenticated_user)):
    check_role(user, index.Role.READER, ix)
    return get_instructions(ix)


@app_preprocessing.post("/index/{ix}/preprocessing", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def post_instruction(ix: str, instruction: PreprocessingInstruction, user: str = Depends(authenticated_user)):
    check_role(user, index.Role.WRITER, ix)
    add_instruction(ix, instruction)
