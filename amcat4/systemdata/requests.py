from datetime import datetime
from typing import Iterable
import logging

from elasticsearch import ConflictError
from fastapi import HTTPException


from amcat4.elastic import es
from amcat4.models import ProjectSettings, PermissionRequest, Roles, RoleRequest, CreateProjectRequest, User
from amcat4.projects.index import create_project_index
from amcat4.systemdata.roles import (
    get_user_server_role,
    role_is_at_least,
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
    """
    List all requests that this user can administrate.
    - For role requests, this means having ADMIN role on the relevant context.
    - For create_project requests, this means having WRITER role on the _server context.
    - only returns pending requests
    """
    if user.email is None:
        return []

    # First return all role request, based on contexts where the user is admin
    role_contexts = [r.role_context for r in list_user_roles(user, required_role=Roles.ADMIN)]
    query = {
        "bool": {
            "must": [
                {"terms": {"role_context": role_contexts}},
                {"term": {"request_type": "role"}},
                {"term": {"status": "pending"}},
            ]
        }
    }

    for id, doc in index_scan(requests_index(), query=query):
        yield _request_from_elastic(doc)

    # then if user is server writer, return all create_project requests
    server_role = get_user_server_role(user)
    if role_is_at_least(server_role, Roles.WRITER):
        query = {"bool": {"must": [{"term": {"request_type": "create_project"}}, {"term": {"status": "pending"}}]}}
        for id, doc in index_scan(requests_index(), query=query):
            yield _request_from_elastic(doc)


def process_request(request: PermissionRequest):
    # TODO: we could do this in bulk, but then we should make sure that
    # we only update the request if the processing was successful
    try:
        if request.status == "pending":
            raise ValueError("Cannot process pending requests")
        elif request.status == "approved":
            match request.request_type:
                case "role":
                    assert isinstance(request, RoleRequest)
                    _process_role_request(request)
                case "create_project":
                    assert isinstance(request, CreateProjectRequest)
                    _process_project_request(request)
                case _:
                    raise ValueError(f"Cannot process {request}")
        else:  ## request.status == "rejected":
            pass
        update_request(request)
    except Exception as e:
        HTTPException(400, f"Error processing request {request}: {e}")
        # logging.error(f"Error processing request {request}: {e}")


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
        update_server_role(r.email, Roles[r.role], ignore_missing=True)
    else:
        update_project_role(r.email, r.role_context, Roles[r.role], ignore_missing=True)


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
