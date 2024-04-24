import asyncio
import logging
from typing import Annotated, Literal
from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

from amcat4 import index
from amcat4.api.auth import authenticated_user, check_role
from amcat4.preprocessing.models import PreprocessingInstruction
from amcat4.index import (
    get_instruction,
    get_instructions,
    add_instruction,
    reassign_preprocessing_errors,
    start_preprocessor,
    stop_preprocessor,
)
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


@app_preprocessing.get("/index/{ix}/preprocessing/{field}/status")
async def get_status(ix: str, field: str, user: str = Depends(authenticated_user)):
    return dict(status=get_manager().get_status(ix, field))


@app_preprocessing.post(
    "/index/{ix}/preprocessing/{field}/status", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def set_status(
    ix: str,
    field: str,
    user: str = Depends(authenticated_user),
    action: Literal["Start", "Stop", "Reassign"] = Body(description="Status to set for this preprocessing task", embed=True),
):
    check_role(user, index.Role.WRITER, ix)
    current_status = get_manager().get_status(ix, field)
    if action == "Start" and current_status in {"Unknown", "Error", "Stopped", "Done"}:
        start_preprocessor(ix, field)
    elif action == "Stop" and current_status in {"Active"}:
        stop_preprocessor(ix, field)
    elif action == "Reassign":
        reassign_preprocessing_errors(ix, field)
    else:
        raise HTTPException(422, f"Cannot {action}, (status: {current_status}; field {ix}.{field})")
