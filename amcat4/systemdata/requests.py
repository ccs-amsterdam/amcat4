from datetime import datetime
from typing import Iterable
import logging

from elasticsearch import ConflictError
from fastapi import HTTPException


from amcat4.elastic import es
from amcat4.models import ProjectSettings, PermissionRequest, Roles, RoleRequest, CreateProjectRequest, User
from amcat4.projects.index import create_project_index
from amcat4.systemdata.roles import (
    update_project_role,
    list_user_roles,
    update_server_role,
)
from amcat4.elastic.util import index_scan
from amcat4.systemdata.versions.v2 import requests_index, requests_index_id


def update_request(request: PermissionRequest):
    # TODO add timestamp=datetime.now().isoformat())
    # Index requests  by type+email+index
    id = requests_index_id(request.request_type, request.email, request.role_context)

    if not request.timestamp:
        request.timestamp = datetime.now()

    es().update(
        index=requests_index(),
        id=id,
        doc=request.model_dump(exclude_none=True),
        doc_as_upsert=True,
        refresh=True,
    )


def delete_request(request: PermissionRequest):
    id = requests_index_id(request.request_type, request.email, request.role_context)
    try:
        es().delete(index=requests_index(), id=id, refresh=True)
    except ConflictError:
        raise HTTPException(404, "The request you tried to delete does not exist")


def list_user_requests(user: User) -> Iterable[PermissionRequest]:
    """List all requests for this user"""
    if user.email is None:
        return []

    docs = index_scan(requests_index(), query={"term": {"email": user.email}})
    for id, doc in docs:
        yield _request_from_elastic(doc)


def list_admin_requests(user: User) -> Iterable[PermissionRequest]:
    """List all requests that this user can administrate (i.e. is admin on role_context)"""
    if user.email is None:
        return []

    role_contexts: list[str] = []

    for role in list_user_roles(user, required_role=Roles.ADMIN):
        role_contexts.append(role.role_context)

    query = {"terms": {"role_context": role_contexts}}

    for id, doc in index_scan(requests_index(), query=query):
        yield _request_from_elastic(doc)


def process_request(request: PermissionRequest):
    # TODO: we could do this in bulk, but then we should make sure that
    # we only update the request if the processing was successful
    try:
        if not request.status == "rejected":
            match request.request_type:
                case "role":
                    assert isinstance(request, RoleRequest)
                    _process_role_request(request)
                case "create_project":
                    assert isinstance(request, CreateProjectRequest)
                    _process_project_request(request)
                case _:
                    raise ValueError(f"Cannot process {request}")
        update_request(request)
    except Exception as e:
        logging.error(f"Error processing request {request}: {e}")


def _request_from_elastic(d) -> PermissionRequest:
    match d["request_type"]:
        case "role":
            return RoleRequest(**d)
        case "create_project":
            return CreateProjectRequest(**d)
        case _:
            raise ValueError(f"Cannot parse request {d}")


def _process_role_request(r: RoleRequest):
    if r.role_context == "_server":
        update_server_role(r.email, Roles[r.role])
    else:
        update_project_role(r.role_context, r.email, Roles[r.role])


def _process_project_request(r: CreateProjectRequest):
    # the permission context for a create_project request is the new index name
    new_index = ProjectSettings(
        id=r.role_context,
        name=r.name,
        description=r.description,
        folder=r.folder,
    )
    create_project_index(new_index, admin_email=r.email)


# ================================ USED IN TESTS ONLY =========================================


def clear_requests():
    """
    TEST ONLY!!
    """
    es().delete_by_query(index=requests_index(), query={"match_all": {}}, refresh=True)


def list_all_requests(statuses: list[str] | None = None) -> Iterable[PermissionRequest]:
    """
    TESTS ONLY
    """
    query = {"terms": {"status": statuses}} if statuses else {"match_all": {}}

    for id, doc in index_scan(requests_index(), query=query):
        yield _request_from_elastic(doc)
