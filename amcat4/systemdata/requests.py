from datetime import datetime
from email import message
from typing import Iterable
import logging

from elasticsearch import ConflictError
from fastapi import HTTPException
from pydantic import EmailStr


from amcat4.elastic import es
from amcat4.models import (
    AdminPermissionRequest,
    ProjectRoleRequest,
    ProjectSettings,
    Roles,
    CreateProjectRequest,
    ServerRoleRequest,
    User,
)
from amcat4.projects.index import create_project_index
from amcat4.systemdata.roles import (
    get_user_server_role,
    role_is_at_least,
    update_project_role,
    list_user_roles,
    update_server_role,
)
from amcat4.elastic.util import index_scan
from amcat4.systemdata.versions import requests_index, requests_index_id


def update_request(request: AdminPermissionRequest):
    # TODO add timestamp=datetime.now().isoformat())
    # Index requests  by type+email+index
    doc = _request_to_elastic(request)
    id = requests_index_id(doc["type"], doc["email"], doc["project_id"])

    es().update(
        index=requests_index(),
        id=id,
        doc=doc,
        doc_as_upsert=True,
        refresh=True,
    )


def delete_request(request: AdminPermissionRequest):
    doc = _request_to_elastic(request)
    id = requests_index_id(doc["type"], doc["email"], doc["project_id"])
    try:
        es().delete(index=requests_index(), id=id, refresh=True)
    except ConflictError:
        raise HTTPException(404, "The request you tried to delete does not exist")


def list_user_requests(user: User) -> Iterable[AdminPermissionRequest]:
    """List all requests for this user"""
    if user.email is None:
        return []

    docs = index_scan(requests_index(), query={"term": {"email": user.email}})
    for id, doc in docs:
        yield _request_from_elastic(doc)


def list_admin_requests(user: User) -> Iterable[AdminPermissionRequest]:
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
                {"terms": {"project_id": role_contexts}},
                {"terms": {"type": ["server_role", "project_role"]}},
                {"term": {"status": "pending"}},
            ]
        }
    }

    for id, doc in index_scan(requests_index(), query=query):
        yield _request_from_elastic(doc)

    # then if user is server writer, return all create_project requests
    server_role = get_user_server_role(user)
    if role_is_at_least(server_role, Roles.WRITER):
        query = {"bool": {"must": [{"term": {"type": "create_project"}}, {"term": {"status": "pending"}}]}}
        for id, doc in index_scan(requests_index(), query=query):
            yield _request_from_elastic(doc)


def process_request(request: AdminPermissionRequest):
    try:
        if request.status == "pending":
            raise ValueError("Cannot process pending requests")
        elif request.status == "approved":
            match request.request.type:
                case "server_role":
                    _process_server_role_request(request.email, request.request)
                case "project_role":
                    _process_project_role_request(request.email, request.request)
                case "create_project":
                    _process_create_project_request(request.email, request.request)
                case _:
                    raise ValueError(f"Cannot process {request}")
        elif request.status == "rejected":
            pass
        else:
            raise ValueError(f"Unknown request status {request.status}")

        update_request(request)
    except Exception as e:
        HTTPException(400, f"Error processing request {request}: {e}")
        # logging.error(f"Error processing request {request}: {e}")


def _process_project_role_request(email: EmailStr, request: ProjectRoleRequest):
    update_project_role(email, request.project_id, Roles[request.role], ignore_missing=True)


def _process_server_role_request(email: EmailStr, request: ServerRoleRequest):
    update_server_role(request.email, Roles[request.role], ignore_missing=True)


def _process_create_project_request(email: EmailStr, request: CreateProjectRequest):
    # the permission context for a create_project request is the new index name
    new_index = ProjectSettings(
        id=request.project_id,
        name=request.name,
        description=request.description,
        folder=request.folder,
    )
    create_project_index(new_index, admin_email=email)


def _request_to_elastic(request: AdminPermissionRequest) -> dict:
    data = request.model_dump()

    doc = dict(
        type=data["request"].get("type"),
        email=data["email"],
        project_id=data["request"].get("project_id", None),
        status=data["status"],
        timestamp=data["timestamp"],
        message=data["message"],
        role=data["request"].get("role", None),
        name=data["request"].get("name", None),
        description=data["request"].get("description", None),
        folder=data["request"].get("folder", None),
    )

    doc = {k: v for k, v in doc.items() if v is not None}
    return doc


def _request_from_elastic(d: dict) -> AdminPermissionRequest:
    # type = d.get("type")

    # required

    # if type == "server_role":
    #     request = ServerRoleRequest.model_validate(d)
    # elif type == "project_role":
    #     request = ProjectRoleRequest.model_validate(d)
    # elif type == "create_project":
    #     request = CreateProjectRequest.model_validate(d)
    # else:
    #     raise ValueError(f"Unknown request type: {type}")

    return AdminPermissionRequest.model_validate(
        dict(
            email=d.get("email"),
            message=d.get("message"),
            timestamp=d.get("timestamp"),
            status=d.get("status"),
            request=d,
        )
    )


# ================================ USED IN TESTS ONLY =========================================


def clear_requests():
    """
    TEST ONLY!!
    """
    es().delete_by_query(index=requests_index(), query={"match_all": {}}, refresh=True)


def list_all_requests(statuses: list[str] | None = None) -> Iterable[AdminPermissionRequest]:
    """
    TESTS ONLY
    """
    query = {"terms": {"status": statuses}} if statuses else {"match_all": {}}

    for id, doc in index_scan(requests_index(), query=query):
        yield _request_from_elastic(doc)
