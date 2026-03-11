"""API Endpoints for Elasticsearch snapshot management (disaster recovery backups)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from amcat4.api.auth_helpers import authenticated_user
from amcat4.connections import es
from amcat4.models import Roles, User
from amcat4.systemdata.roles import HTTPException_if_not_server_role

app_snapshots = APIRouter(tags=["snapshots"])


class SnapshotRepository(BaseModel):
    name: str
    type: str
    settings: dict


class CreateRepositoryBody(BaseModel):
    name: str
    type: str
    settings: dict


class SnapshotInfo(BaseModel):
    snapshot: str
    repository: str
    uuid: str
    state: str
    indices: list[str]
    start_time: str
    end_time: str | None
    size_in_bytes: int | None = None


class CreateSnapshotBody(BaseModel):
    repository: str
    snapshot: str


@app_snapshots.get("/snapshots/path-repo")
async def get_path_repo(user: User = Depends(authenticated_user)) -> list[str]:
    """Get the path.repo values configured across all Elasticsearch nodes. Requires ADMIN server role."""
    await HTTPException_if_not_server_role(user, Roles.ADMIN)
    result = await es().nodes.info(metric=["settings"])
    paths: set[str] = set()
    for node in result.get("nodes", {}).values():
        repo = node.get("settings", {}).get("path", {}).get("repo")
        if repo is None:
            continue
        if isinstance(repo, str):
            paths.add(repo)
        elif isinstance(repo, list):
            paths.update(repo)
    return sorted(paths)


@app_snapshots.get("/snapshots/repositories")
async def list_repositories(user: User = Depends(authenticated_user)) -> list[SnapshotRepository]:
    """List all configured Elasticsearch snapshot repositories. Requires ADMIN server role."""
    await HTTPException_if_not_server_role(user, Roles.ADMIN)
    result = await es().snapshot.get_repository(name="*")
    return [SnapshotRepository(name=name, **repo) for name, repo in result.items()]


@app_snapshots.post("/snapshots/repositories", status_code=status.HTTP_201_CREATED)
async def register_repository(body: CreateRepositoryBody, user: User = Depends(authenticated_user)) -> SnapshotRepository:
    """Register a new Elasticsearch snapshot repository. Requires ADMIN server role."""
    await HTTPException_if_not_server_role(user, Roles.ADMIN)
    existing = await es().snapshot.get_repository(name="*")
    if body.type == "fs":
        new_loc = body.settings.get("location", "")
        for name, repo in existing.items():
            if repo.get("type") == "fs" and repo.get("settings", {}).get("location") == new_loc:
                raise HTTPException(status_code=409, detail=f"Location '{new_loc}' is already used by repository '{name}'")
    elif body.type == "s3":
        new_bucket = body.settings.get("bucket", "")
        new_path = body.settings.get("base_path", "")
        for name, repo in existing.items():
            s = repo.get("settings", {})
            if repo.get("type") == "s3" and s.get("bucket") == new_bucket and s.get("base_path", "") == new_path:
                raise HTTPException(
                    status_code=409,
                    detail=f"S3 bucket/path '{new_bucket}/{new_path}' is already used by repository '{name}'",
                )
    await es().snapshot.create_repository(
        name=body.name,
        repository={"type": body.type, "settings": body.settings},
    )
    return SnapshotRepository(name=body.name, type=body.type, settings=body.settings)


@app_snapshots.delete("/snapshots/repositories/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(name: str, user: User = Depends(authenticated_user)) -> None:
    """Unregister an Elasticsearch snapshot repository. Requires ADMIN server role."""
    await HTTPException_if_not_server_role(user, Roles.ADMIN)
    try:
        await es().snapshot.delete_repository(name=name)
    except Exception as e:
        if "repository_missing_exception" in str(e) or "404" in str(e):
            raise HTTPException(status_code=404, detail=f"Repository '{name}' not found")
        raise


@app_snapshots.get("/snapshots")
async def list_snapshots(repository: str | None = None, user: User = Depends(authenticated_user)) -> list[SnapshotInfo]:
    """List snapshots. Optionally filter by repository. Requires ADMIN server role."""
    await HTTPException_if_not_server_role(user, Roles.ADMIN)
    repo = repository or "_all"
    try:
        result = await es().snapshot.get(repository=repo, snapshot="_all", index_details=True)
    except Exception as e:
        if "repository_missing_exception" in str(e) or "404" in str(e):
            return []
        raise
    return [
        SnapshotInfo(
            snapshot=s["snapshot"],
            repository=s.get("repository", repo if repo != "_all" else ""),
            uuid=s["uuid"],
            state=s["state"],
            indices=s.get("indices", []),
            start_time=s.get("start_time", ""),
            end_time=s.get("end_time"),
            size_in_bytes=sum(idx.get("size_in_bytes", 0) for idx in s.get("index_details", {}).values()) or None,
        )
        for s in result.get("snapshots", [])
    ]


@app_snapshots.post("/snapshots", status_code=status.HTTP_202_ACCEPTED)
async def create_snapshot(body: CreateSnapshotBody, user: User = Depends(authenticated_user)) -> SnapshotInfo:
    """Trigger a new snapshot of all indices. Returns immediately; poll GET /snapshots for status.
    Requires ADMIN server role."""
    await HTTPException_if_not_server_role(user, Roles.ADMIN)
    result = await es().snapshot.create(
        repository=body.repository,
        snapshot=body.snapshot,
        wait_for_completion=False,
    )
    snap = result.get("snapshot", {})
    return SnapshotInfo(
        snapshot=snap.get("snapshot", body.snapshot),
        repository=body.repository,
        uuid=snap.get("uuid", ""),
        state=snap.get("state", "IN_PROGRESS"),
        indices=snap.get("indices", []),
        start_time=snap.get("start_time", ""),
        end_time=snap.get("end_time"),
    )
