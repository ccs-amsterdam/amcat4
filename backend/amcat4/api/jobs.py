"""API endpoints for background jobs (such as copying documents between projects)."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from amcat4.api.auth_helpers import authenticated_user
from amcat4.models import Roles, User
from amcat4.projects.jobs import cancel_job, get_job, list_jobs
from amcat4.systemdata.roles import (
    HTTPException_if_not_project_index_role,
    get_user_project_role,
    get_user_server_role,
    role_is_at_least,
)

app_jobs = APIRouter(prefix="/jobs", tags=["jobs"])


async def _can_view(user: User, job: dict) -> bool:
    """Jobs can be viewed by their creator, by server admins, and by project writers"""
    if user.email is not None and job["created_by"] == user.email:
        return True
    if role_is_at_least(user, await get_user_server_role(user), Roles.ADMIN):
        return True
    if job["project"]:
        return role_is_at_least(user, await get_user_project_role(user, job["project"]), Roles.WRITER)
    return False


async def _get_job_or_403(user: User, job_id: str) -> dict:
    job = await get_job(job_id)
    if not await _can_view(user, job):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this job")
    return job


@app_jobs.get("")
async def get_jobs(
    project: str | None = Query(None, description="List the jobs of this project (requires WRITER role)"),
    user: User = Depends(authenticated_user),
) -> list[dict]:
    """List recent jobs: the jobs of a project, or else the jobs created by the current user."""
    if project:
        await HTTPException_if_not_project_index_role(user, project, Roles.WRITER)
        return await list_jobs(project=project)
    if user.email is None:
        return []
    return await list_jobs(created_by=user.email)


@app_jobs.get("/{job_id}")
async def get_job_status(job_id: str, user: User = Depends(authenticated_user)) -> dict:
    """Get the status, progress and result of a job."""
    return await _get_job_or_403(user, job_id)


@app_jobs.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str, user: User = Depends(authenticated_user)):
    """Cancel a pending or running job (work that was already done is not undone)."""
    await _get_job_or_403(user, job_id)
    await cancel_job(job_id)
