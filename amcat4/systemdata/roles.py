from cmath import e
from typing import Iterable, Literal
from typing_extensions import Required

from fastapi import HTTPException
from pydantic import EmailStr
from amcat4.systemdata.versions.v2 import ROLES_INDEX, roles_index_id
from amcat4.elastic import es
from amcat4.models import IndexId, RoleContext, RoleEmailPattern, RoleMatch, RoleRule, User, Role, UserRole
from amcat4.systemdata.util import index_scan
from enum import IntEnum


class RoleHierarchy(IntEnum):
    NONE = 0
    LISTER = 5
    METAREADER = 10
    READER = 20
    WRITER = 30
    ADMIN = 40


class EmailMatchHierarchy(IntEnum):
    ANY = 0
    DOMAIN = 10
    EXACT = 20


class InvalidRoleError(ValueError):
    pass


def elastic_create_or_update_role(email_pattern: RoleEmailPattern, role_context: RoleContext, role: Role):
    user_role = RoleRule(email_pattern=email_pattern, role_context=role_context, role=role, role_match=get_match_type(email_pattern))

    id = roles_index_id(user_role.email_pattern, user_role.role_context)
    doc = {"email": user_role.email_pattern, "role_context": user_role.role_context, "role": user_role}
    es().update(index=ROLES_INDEX, id=id, doc=doc, doc_as_upsert=True, refresh=True)


def elastic_delete_role(email_pattern: RoleEmailPattern, role_context: RoleContext):
    id = roles_index_id(email_pattern, role_context)
    es().delete(index=ROLES_INDEX, id=id, refresh=True)



def elastic_list_roles(email_patterns: list[RoleEmailPattern] | None = None,
                       role_contexts: list[RoleContext] | None = None,
                       min_role: Role | None = None,
                       min_match: RoleMatch | None = None) -> Iterable[RoleRule]:
    """
    List roles, optionally filtered by user, minimum role, role contexts, and minimum match quality.

    :param role_emails: List of email patterns to filter on (or None for all users)
    :param min_role: The minimum global role of the user (or None for all roles)
    :param role_contexts: List of role contexts to filter on (or None for all contexts)
    :param min_match: The minimum match quality (or None for all matches)
    :return: List of UserRole objects
    """
    query: dict = {"bool": {"must": []}}

    if email_patterns is not None:
        query["bool"]["must"].append({"terms": {"email": email_patterns}})

    if role_contexts is not None:
        query["bool"]["must"].append({"terms": {"role_context": role_contexts}})

    if min_role is not None:
        query["bool"]["must"].append(min_role_query(min_role))

    if min_match is not None:
        query["bool"]["must"].append(min_match_query(min_match))

    for id, user_role in index_scan(ROLES_INDEX, query=query):
        yield RoleRule.model_validate(user_role)


def list_user_roles(email: EmailStr | None,
                    role_contexts: list[RoleContext] | None = None,
                    required_role: Role | None = None,
                    required_match: RoleMatch | None = None) -> list[UserRole]:
    """
    For a given user, get the most exact matching role for each role context (index or _server)
    This does not account for global admin rights (see get_user_role for that).
    """
    strongest_matches: dict[RoleContext, UserRole] = {}

    all_matches = elastic_list_roles(
        email_patterns=email_to_role_emails(email),
        role_contexts=role_contexts,
        min_match=required_match,
        min_role=required_role
    )

    for match in all_matches:
        context = match.role_context
        user_role = UserRole(role_context=match.role_context, role=match.role, role_match=match.role_match)
        if context in strongest_matches:
            if EmailMatchHierarchy[match.role_match] > EmailMatchHierarchy[strongest_matches[context].role_match]:
                strongest_matches[context] = user_role
        else:
            strongest_matches[context] = user_role

    return list(strongest_matches.values())


def get_project_index_role(email: EmailStr | None,
                  project_index: IndexId,
                  global_admin: bool = True) -> UserRole | None:
    """
    Get the role for the given user and context, or None if no role exists.
    This gives the most exact matching role on the given context.
    If email is None, only the guest role (email="*") will be considered.

    By default, a server admin will get ADMIN role on all contexts.
    Set global_admin to False to disable this.
    """
    user_roles = list_user_roles(email, role_contexts=[project_index, "_server"])
    target_role = next((ur for ur in user_roles if ur.role_context == project_index), None)
    server_role = next((ur for ur in user_roles if ur.role_context == "_server"), None)

    if global_admin and server_role and server_role.role == "ADMIN":
        return UserRole(role_context=project_index, role="ADMIN", role_match="EXACT")
    return target_role


def get_server_role(email: EmailStr | None) -> UserRole | None:
    user_roles = list_user_roles(email, role_contexts=["_server"])
    return user_roles[0] if user_roles else None


def raise_if_not_project_index_role(user: User,
                          role_context: RoleContext,
                          required_role: Role,
                          global_admin: bool = True,
                          message: str | None = None
):
    """
    Raise an HTTP Exception if the user does not have the required role for the given context.
    """
    role = get_project_index_role(user.email, role_context, global_admin=global_admin)
    if not role_is_at_least(role, required_role):
        detail = message or f"User {user.email} does not have {required_role} role for {role_context}"
        raise HTTPException(status_code=401, detail=detail)


def raise_if_not_server_role(user: User,
                          required_role: Role,
                          message: str | None = None
):
    """
    Raise an HTTP Exception if the user does not have the required role for the given context.
    """
    role = get_server_role(user.email)
    if not role_is_at_least(role, required_role):
        detail = message or f"User {user.email} does not have the {required_role} server role"
        raise HTTPException(status_code=401, detail=detail)

def set_guest_role(index_id: IndexId, role: Role | Literal["NONE"]):
    if role == "NONE":
        elastic_delete_role(email_pattern="*", role_context=index_id)
    else:
        elastic_create_or_update_role(email_pattern="*", role_context=index_id, role=role)

def get_guest_role(index_id: IndexId) -> RoleRule | None:
    get_project_index_role(email=None, project_index=index_id)


def role_is_at_least(user_role: UserRole | None, required_role: Role) -> bool:
    if user_role is None:
        return False
    return RoleHierarchy[user_role.role] >= RoleHierarchy[required_role]

def match_is_at_least(user_role: UserRole | None, required_match: RoleMatch) -> bool:
    if user_role is None:
        return False
    return EmailMatchHierarchy[user_role.role_match] >= EmailMatchHierarchy[required_match]





def email_to_role_emails(email: EmailStr | None):
    """
    Given a user, return a list of email patterns that should be checked for roles.
    """
    if email is None:
        return ["*"]
    return [
        email,
        "*@" + email.split("@")[-1],
        "*"
    ]



def min_role_query(min_role: Role):
    min_role_hierarchy = RoleHierarchy[min_role]
    roles = [role.name for role in RoleHierarchy if role.value > min_role_hierarchy.value]
    return {"terms": {"role": roles}}


def min_match_query(min_match: RoleMatch):
    min_match_hierarchy = EmailMatchHierarchy[min_match]
    matches = [match.name for match in EmailMatchHierarchy if match.value >= min_match_hierarchy.value]
    return {"terms": {"role_match": matches}}


def get_match_type(email: EmailStr | Literal['*']) -> RoleMatch
    if email == "*":
        return "ANY"
    elif email.startswith("*@"):
        return "DOMAIN"
    else:
        return "EXACT"
