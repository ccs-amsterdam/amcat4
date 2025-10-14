from typing import Iterable, Literal

from fastapi import HTTPException
from amcat4.config import AuthOptions, get_settings
from amcat4.systemdata.versions.v2 import ROLES_INDEX, roles_index_id
from amcat4.elastic import es
from amcat4.models import IndexId, Context, UserRole, Role
from amcat4.systemdata.util import index_scan
from enum import IntEnum


# Special username constants
ADMIN_USER = "_admin"
GUEST_USER = "_guest"


class RoleHierarchy(IntEnum):
    NONE = 0
    LISTER = 5
    METAREADER = 10
    READER = 20
    WRITER = 30
    ADMIN = 40


def elastic_create_or_update_role(email: str, permission_context: Context, role: Role):
    user_role = UserRole(email=email, permission_context=permission_context, role=role)
    id = roles_index_id(user_role.email, user_role.permission_context)
    doc = {"email": user_role.email, "permission_context": user_role.permission_context, "role": user_role}
    es().update(index=ROLES_INDEX, id=id, doc=doc, doc_as_upsert=True, refresh=True)


def elastic_delete_role(email: str, permission_context: Context):
    id = roles_index_id(email, permission_context)
    es().delete(index=ROLES_INDEX, id=id, refresh=True)


def elastic_get_role(email: str, permission_context: Context) -> Role | None:
    id = roles_index_id(email, permission_context)

    try:
        doc = es().get(index=ROLES_INDEX, id=id, source=["role"])
        return doc["_source"]["role"]
    except Exception:
        return None


def elastic_list_roles(email: str, min_role: Role | None = None) -> Iterable[UserRole]
    query: dict = {"bool": { "must": [{"term": {"email": email}}], } }

    if min_role is not None:
        query["bool"]["filter"] = min_role_filter(min_role)

    for id, doc in index_scan(ROLES_INDEX, query=query):
        yield UserRole(email=doc["email"], permission_context=doc["permission_context"], role=doc["role"])


def min_role_filter(min_role: Role):
    min_role_hierarchy = RoleHierarchy[min_role]
    roles = [role.name for role in RoleHierarchy if role.value > min_role_hierarchy.value]
    return {"terms": {"role": roles}}


# TODO: add lru caching (and make sure it invalidates in create_or_update_role)
def has_role(email: str, permission_context: Context, required_role: Role) -> bool:
    """
    Check if the given user has at least the required role. Returns bool
    :param email: The email address of the authenticated user
    :param permission_context: The context (index id or _server) of the role
    :param required_role: The minimum global role of the user
    """
    # skip checks if auth disabled
    if get_settings().auth == AuthOptions.no_auth:
        return True

    role = elastic_get_role(email, permission_context)
    has_required_role = role_is_required_role(role, required_role)

    # server admin has admin role on all indices
    if not has_required_role and permission_context != "_server":
        # TODO: Convince wouter that admin should only:
            # - get READ access to all indices (because monitoring is part of their task)
            # - would need to explicitly assign themselves a WRITER/ADMIN role on the index
        if has_role(email, "_server", 'ADMIN'):
            return True

    return has_required_role


def role_is_required_role(role: str | None, required_role: Role | None) -> bool:
    return RoleHierarchy[role or "NONE"] >= RoleHierarchy[required_role or "NONE"]


def raise_if_not_has_role(email: str, permission_context: Context, required_role: Role):
    """
    Raise an HTTP Exception if has_role is false
    """
    if not has_role(email, permission_context, required_role):
        raise HTTPException(status_code=401, detail=f"User {email} does not have {required_role} role for {permission_context}")
