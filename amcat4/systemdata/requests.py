from datetime import datetime
from typing import Iterable
import logging

from amcat4.elastic import es
from amcat4.models import IndexSettings, PermissionRequest, RoleRequest, CreateProjectRequest
from amcat4.projectdata import create_project_index
from amcat4.systemdata.roles import elastic_create_or_update_role, elastic_delete_role, elastic_list_roles
from amcat4.systemdata.util import index_scan
from amcat4.systemdata.versions.v2 import REQUESTS_INDEX, requests_index_id


def elastic_create_or_update_request(request: PermissionRequest):
    # TODO add timestamp=datetime.now().isoformat())
    # Index requests  by type+email+index
    id = requests_index_id(request.request_type, request.email, request.permission_context)

    if not request.timestamp:
        request.timestamp = datetime.now()

    es().update(
        index=REQUESTS_INDEX,
        id=id,
        doc=request.model_dump(),
        doc_as_upsert=True,
        refresh=True,
    )


def elastic_delete_request(request: PermissionRequest):
    id = requests_index_id(request.request_type, request.email, request.permission_context)
    es().delete(index=REQUESTS_INDEX, id=id, refresh=True)


def elastic_list_user_requests(email: str) -> Iterable[PermissionRequest]:
    """List all requests for this user"""
    docs = index_scan(REQUESTS_INDEX, query={"term": {"email": email}})
    for id, doc in docs:
        yield request_from_elastic(doc)


def elastic_list_admin_requests(email: str) -> Iterable[PermissionRequest]:
    """List all requests that this user can administrate"""
    admin_indices: list[str] = []
    for user_role in elastic_list_roles(email, "ADMIN"):
        admin_indices.append(user_role.permission_context)

    query = {"terms": {"permission_context": admin_indices}}

    for id, doc in index_scan(REQUESTS_INDEX, query=query):
        yield request_from_elastic(doc)


def request_from_elastic(d) -> PermissionRequest:
    match d["request_type"]:
        case "role":
            return RoleRequest(**d)
        case "create_project":
            return CreateProjectRequest(**d)
        case _:
            raise ValueError(f"Cannot parse request {d}")


def process_requests(requests: list[PermissionRequest]):
    for r in requests:
        try:
            if not r.status == "rejected":
                match r.request_type:
                    case "role":
                        assert isinstance(r, RoleRequest)
                        process_role_request(r)
                    case "create_project":
                        assert isinstance(r, CreateProjectRequest)
                        process_project_request(r)
                    case _:
                        raise ValueError(f"Cannot process {r}")
            elastic_create_or_update_request(r)
        except Exception as e:
            logging.error(f"Error processing request {r}: {e}")


def process_role_request(r: RoleRequest):
    if r.role == "NONE":
        elastic_delete_role(r.email, r.permission_context)
    else:
        elastic_create_or_update_role(r.email, r.permission_context, r.role)


def process_project_request(r: CreateProjectRequest):
    # the permission context for a create_project request is the new index name
    new_index = IndexSettings(
        id=r.permission_context,
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
    es().delete_by_query(index=REQUESTS_INDEX, query={"match_all": {}}, refresh=True)


def elastic_list_all_requests(statuses: list[str] | None = None) -> Iterable[PermissionRequest]:
    """
    TESTS ONLY
    """
    query = {"terms": {"status": statuses}} if statuses else {"match_all": {}}

    for id, doc in index_scan(REQUESTS_INDEX, query=query):
        yield request_from_elastic(doc)
