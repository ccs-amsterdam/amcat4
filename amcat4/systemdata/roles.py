from typing import Iterable, Literal

from elasticsearch.exceptions import ConflictError
from fastapi import HTTPException
from pydantic import EmailStr
from amcat4.systemdata.versions.v2 import ROLES_INDEX, roles_index_id
from amcat4.elastic import es
from amcat4.models import (
    IndexId,
    RoleContext,
    RoleEmailPattern,
    RoleRule,
    User,
    Role,
)
from amcat4.elastic.util import index_scan


class InvalidRoleError(ValueError):
    pass


def create_role(email_pattern: RoleEmailPattern, role_context: RoleContext, role: Role):
    """
    Creates a role for a given email pattern and role context.
    Raises an error if a role for this email_pattern in this context already exists.
    """
    if role == Role.NONE:
        raise InvalidRoleError("Cannot create a role with Role.NONE. Use update_role to delete roles.")

    id = roles_index_id(email_pattern, role_context)
    user_role = RoleRule(email_pattern=email_pattern, role_context=role_context, role=role)
    doc = {"email": user_role.email_pattern, "role_context": user_role.role_context, "role": user_role.role.name}
    es().create(index=ROLES_INDEX, id=id, document=doc, refresh=True)


def update_role(email_pattern: RoleEmailPattern, role_context: RoleContext, role: Role):
    """
    Updates (or creates) a role for a given email pattern and role context.
    """
    id = roles_index_id(email_pattern, role_context)
    if role == Role.NONE:
        es().delete(index=ROLES_INDEX, id=id, refresh=True)
        return

    user_role = RoleRule(email_pattern=email_pattern, role_context=role_context, role=role)
    doc = {"email": user_role.email_pattern, "role_context": user_role.role_context, "role": user_role.role.name}
    es().update(index=ROLES_INDEX, id=id, doc_as_upsert=True, doc=doc, refresh=True)


def list_roles(
    email_patterns: list[RoleEmailPattern] | None = None,
    role_contexts: list[RoleContext] | None = None,
    min_role: Role | None = None,
) -> Iterable[RoleRule]:
    """
    List roles, optionally filtered by user, minimum role, role contexts, and minimum match quality.

    :param role_emails: List of email patterns to filter on (or None for all users)
    :param min_role: The minimum global role of the user (or None for all roles)
    :param role_contexts: List of role contexts to filter on (or None for all contexts)
    :param min_match: The minimum match quality (or None for all matches)
    """
    query: dict = {"bool": {"must": []}}

    if email_patterns is not None:
        query["bool"]["must"].append({"terms": {"email": email_patterns}})

    if role_contexts is not None:
        query["bool"]["must"].append({"terms": {"role_context": role_contexts}})

    if min_role is not None:
        query["bool"]["must"].append(min_role_query(min_role))

    for id, user_role in index_scan(ROLES_INDEX, query=query):
        yield RoleRule.model_validate(user_role)


def list_user_roles(
    user: User,
    role_contexts: list[RoleContext] | None = None,
    required_role: Role | None = None,
) -> list[RoleRule]:
    """
    For a given user, get the most exact matching role for each role context (index or _server)
    This does not account for global admin rights (see get_user_role for that).

    if email is None, only the guest role (email="*") will be considered.
    """

    all_matches = list_roles(email_patterns=user_to_role_emails(user), role_contexts=role_contexts, min_role=required_role)

    return get_strongest_matches(all_matches)


def get_user_project_role(user: User, project_index: IndexId, global_admin: bool = True) -> RoleRule:
    """
    Get the role for the given user and context.
    This gives the most exact matching role on the given context.
    If email is None, only the guest role (email="*") will be considered.

    By default, a server admin will get ADMIN role on all contexts.
    Set global_admin to False to disable this.

    returns a RoleRule with Role.NONE if no role exists.
    """
    # If we just need the project role, its a simple lookup
    if not global_admin:
        project_role = list_user_roles(user, role_contexts=[project_index])
        project_role = project_role[0] if project_role else None

    # If we need to consider global admin, we fetch both roles in one go
    # and overwrite the project role if the server role is ADMIN
    else:
        user_roles = list_user_roles(user, role_contexts=[project_index, "_server"])
        project_role = next((ur for ur in user_roles if ur.role_context == project_index), None)
        server_role = next((ur for ur in user_roles if ur.role_context == "_server"), None)

        if server_role and server_role.role == Role.ADMIN:
            project_role = server_role
            project_role.role_context = project_index

    if project_role:
        return project_role
    else:
        return RoleRule(email_pattern="*", role_context=project_index, role=Role.NONE)


def get_user_server_role(user: User) -> RoleRule:
    """
    Get the most exact server role match for the given user.
    returns a RoleRule with Role.NONE if no role exists.
    """
    user_roles = list_user_roles(user, role_contexts=["_server"])
    if user_roles:
        return user_roles[0]
    else:
        return RoleRule(email_pattern="*", role_context="_server", role=Role.NONE)


def raise_if_not_project_index_role(
    user: User, role_context: RoleContext, required_role: Role, global_admin: bool = True, message: str | None = None
):
    """
    Raise an HTTP Exception if the user does not have the required role for the given context.
    """
    role = get_user_project_role(user, role_context, global_admin=global_admin)
    if not role_is_at_least(role, required_role):
        detail = message or f"User {user.email} does not have {required_role} role for {role_context}"
        raise HTTPException(status_code=401, detail=detail)


def raise_if_not_server_role(user: User, required_role: Role, message: str | None = None):
    """
    Raise an HTTP Exception if the user does not have the required role for the given context.
    """
    role = get_user_server_role(user)
    if not role_is_at_least(role, required_role):
        detail = message or f"User {user.email} does not have the {required_role} server role"
        raise HTTPException(status_code=401, detail=detail)


def set_guest_role(index_id: IndexId, role: Role):
    """
    Helper to set the guest role for an index.
    """
    if role == Role.ADMIN:
        raise InvalidRoleError("Cannot set guest role to ADMIN. Guests can at most be WRITER.")
    update_role(email_pattern="*", role_context=index_id, role=role)


def get_guest_role(index_id: IndexId) -> Role:
    """Get the guest role for an index. Note that this returns the Role not RoleRule!"""
    return get_user_project_role(user=User(email=None), project_index=index_id).role


def role_is_at_least(user_role: RoleRule | None, required_role: Role) -> bool:
    if user_role is None:
        if required_role == Role.NONE:
            return True
        return False
    return user_role.role >= required_role


def user_to_role_emails(user: User):
    """
    Given a user, return a list of email patterns that should be checked for roles.
    """
    # If no email is given, only the guest role (*) applies
    if user.email is None:
        return ["*"]
    # Otherwise, check exact email, domain wildcard, and guest role
    return [user.email, "*@" + user.email.split("@")[-1], "*"]


def min_role_query(min_role: Role):
    roles = [role.name for role in Role if role > min_role]
    return {"terms": {"role": roles}}


def match_strength(email_pattern: RoleEmailPattern) -> int:
    if email_pattern == "*":
        return 1
    elif email_pattern.startswith("*@"):
        return 2
    else:
        return 3


def get_strongest_matches(role_matches: Iterable[RoleRule]) -> list[RoleRule]:
    """
    From a list of roles, return the strongest match for each role context.
    """
    # use tuples of (strength, RoleRule) for each role context to sort out the strongest matches
    strongest_matches: dict[RoleContext, tuple[int, RoleRule]] = {}

    for match in role_matches:
        context = match.role_context
        strength = match_strength(match.email_pattern)

        if context in strongest_matches:
            current_strength = strongest_matches[context][0]
            if strength > current_strength:
                strongest_matches[context] = (strength, match)
        else:
            strongest_matches[context] = (strength, match)

    return [match for strength, match in strongest_matches.values()]
