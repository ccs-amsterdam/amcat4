import logging
from fastapi import APIRouter, Depends, HTTPException, Response, status

from amcat4 import index
from amcat4.api.auth import authenticated_user, check_role
from amcat4.preprocessing.instruction import PreprocessingInstruction, get_instruction, get_instructions, add_instruction
from amcat4.preprocessing.processor import get_counts, get_manager
from amcat4.preprocessing.task import get_tasks

logger = logging.getLogger("amcat4.preprocessing")

app_preprocessing = APIRouter(tags=["preprocessing"])


@app_preprocessing.get("/preprocessing_tasks")
def list_tasks():
    return [t.model_dump() for t in get_tasks()]


@app_preprocessing.get("/index/{ix}/preprocessing")
def list_instructions(ix: str, user: str = Depends(authenticated_user)):
    check_role(user, index.Role.READER, ix)
    return get_instructions(ix)


@app_preprocessing.post("/index/{ix}/preprocessing", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def post_instruction(ix: str, instruction: PreprocessingInstruction, user: str = Depends(authenticated_user)):
    check_role(user, index.Role.WRITER, ix)
    add_instruction(ix, instruction)


@app_preprocessing.get("/index/{ix}/preprocessing/{field}")
async def get_instruction_details(ix: str, field: str, user: str = Depends(authenticated_user)):
    check_role(user, index.Role.WRITER, ix)
    i = get_instruction(ix, field)
    if i is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preprocessing instruction for field {field} on index {ix} not found",
        )
    state = get_manager().get_status(ix, field)
    counts = get_counts(ix, field)
    return dict(instruction=i, status=state, counts=counts)
