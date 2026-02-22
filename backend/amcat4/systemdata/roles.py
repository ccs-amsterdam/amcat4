from typing import AsyncIterable

from fastapi import HTTPException

from amcat4.connections import es
from amcat4.elastic.util import index_scan
from amcat4.models import (
    GuestRole,
    IndexId,
    RoleContext,
    RoleEmailPattern,
    RoleRule,
    Roles,
    User,
)
from amcat4.systemdata.versions import roles_index_id, roles_index_name


def role_is_at_least(user: User, user_role: RoleRule | None, required_role: Roles, ignore_restrictions: bool = False) -> bool:
    """
    !!!
    This function should be used for any permission checks, because it correctly handles user.role_restrictions.
    So even if you just want to check if a user has exactly ADMIN role, you should use this function.

    In most cases you can also use the higher-level HTTPException_if_not... functions.
    """
    if user_role is None:
        if required_role == Roles.NONE:
            return True
        return False

    restricted_role = restrict_role(user, user_role) if not ignore_restrictions else user_role
    return Roles[restricted_role.role] >= required_role


async def create_project_role(email: RoleEmailPattern, project_id: IndexId, role: Roles):
    await _create_role(email=email, role_context=project_id, role=role)


async def create_server_role(email: RoleEmailPattern, role: Roles):
    await _create_role(email=email, role_context="_server", role=role)


async def update_project_role(email: RoleEmailPattern, project_id: IndexId, role: Roles, ignore_missing: bool = False):
    await _update_role(email=email, role_context=project_id, role=role, ignore_missing=ignore_missing)


async def update_server_role(email: RoleEmailPattern, role: Roles, ignore_missing: bool = False):
    await _update_role(email=email, role_context="_server", role=role, ignore_missing=ignore_missing)


async def delete_project_role(email: RoleEmailPattern, project_id: IndexId, ignore_missing: bool = False):
    await _delete_role(email=email, role_context=project_id, ignore_missing=ignore_missing)


async def delete_server_role(email: RoleEmailPattern, ignore_missing: bool = False):
    await _delete_role(email=email, role_context="_server", ignore_missing=ignore_missing)


def list_project_roles(
    emails: list[RoleEmailPattern] | None = None,
    project_ids: list[IndexId] | None = None,
    min_role: Roles | None = None,
) -> AsyncIterable[RoleRule]:
    return _list_roles(emails=emails, role_contexts=project_ids, min_role=min_role, only_projects=True)


def list_server_roles(
    emails: list[RoleEmailPattern] | None = None,
    min_role: Roles | None = None,
) -> AsyncIterable[RoleRule]:
    return _list_roles(emails=emails, role_contexts=["_server"], min_role=min_role)


async def list_user_roles(
    user: User,
    role_contexts: list[RoleContext] | None = None,
    required_role: Roles | None = None,
) -> list[RoleRule]:
    all_matches = _list_roles(emails=_user_to_role_emails(user), role_contexts=role_contexts, min_role=required_role)
    return await _get_user_matches(user, all_matches)


async def list_user_project_roles(
    user: User,
    project_ids: list[IndexId] | None = None,
    required_role: Roles | None = None,
) -> list[RoleRule]:
    """
    List all project roles for a given user.
    This gives the most exact matching role for each project (guest, domain or full email).
    This does not (!!) take server role into account (see get_user_project_role)
    """
    all_matches = list_project_roles(emails=_user_to_role_emails(user), project_ids=project_ids, min_role=required_role)
    return await _get_user_matches(user, all_matches)


async def get_user_project_role(user: User, project_index: IndexId, global_admin: bool = True) -> RoleRule:
    """
    Get the role for the given user and context.
    This gives the most exact matching role on the given context.
    If email is None, only the guest role (email="*") will be considered.

    By default, a server admin will get ADMIN role on all contexts.
    Set global_admin to False to disable this.

    returns a RoleRule with Role.NONE if no role exists.
    """
    # If auth disabled always return the admin role, even if global_admin is False.
    if user.auth_disabled:
        return RoleRule(email=user.email or "*", role_context=project_index, role=Roles.ADMIN.name)

    # If the user is a superadmin, we can directly return ADMIN
    if global_admin and user.superadmin:
        return RoleRule(email=user.email or "*", role_context=project_index, role=Roles.ADMIN.name)

    # If we just need the project role, its a simple lookup
    if not global_admin:
        project_role = await list_user_roles(user, role_contexts=[project_index])
        project_role = project_role[0] if project_role else None

    # If we need to consider global admin, we fetch both roles in one go
    # and overwrite the project role if the server role is ADMIN
    else:
        user_roles = await list_user_roles(user, role_contexts=[project_index, "_server"])
        project_role = next((ur for ur in user_roles if ur.role_context == project_index), None)
        server_role = next((ur for ur in user_roles if ur.role_context == "_server"), None)

        if server_role and server_role.role == Roles.ADMIN.name:
            project_role = server_role
            project_role.role_context = project_index

    if project_role:
        return project_role
    else:
        return RoleRule(email="*", role_context=project_index, role="NONE")


async def get_user_server_role(user: User) -> RoleRule:
    """
    Get the most exact server role match for the given user.
    returns a RoleRule with Role.NONE if no role exists.
    """
    if user.superadmin or user.auth_disabled:
        return RoleRule(email=user.email or "*", role_context="_server", role=Roles.ADMIN.name)

    user_roles = await list_user_roles(user, role_contexts=["_server"])
    if user_roles:
        return user_roles[0]
    else:
        return RoleRule(email="*", role_context="_server", role="NONE")


async def HTTPException_if_not_project_index_role(
    user: User, role_context: RoleContext, required_role: Roles, global_admin: bool = True, message: str | None = None
):
    """
    Raise an HTTP Exception if the user does not have the required role for the given context.
    """
    role = await get_user_project_role(user, role_context, global_admin=global_admin)

    if message:
        detail = f"does not have persmission. {message}"
    else:
        detail = f"does not have {required_role.name} permissions on project {role_context}"

    if not role_is_at_least(user, role, required_role, ignore_restrictions=True):
        raise HTTPException(403, f"{user.email or 'GUEST'} {detail}")
    if not role_is_at_least(user, role, required_role, ignore_restrictions=False):
        raise HTTPException(403, f"API key '{user.api_key_name}' {detail}")


async def HTTPException_if_not_server_role(user: User, required_role: Roles, message: str | None = None):
    """
    Raise an HTTP Exception if the user does not have the required role for the given context.
    """
    role = await get_user_server_role(user)

    if message:
        detail = f"does not have persmission. {message}"
    else:
        detail = f"does not have {required_role.name} permissions on the server"

    if not role_is_at_least(user, role, required_role, ignore_restrictions=True):
        raise HTTPException(403, f"{user.email or 'GUEST'} {detail}")
    if not role_is_at_least(user, role, required_role, ignore_restrictions=False):
        detail = message or f"{user.email or 'GUEST'} does not have {required_role.name} permissions on the server"
        raise HTTPException(403, f"API key '{user.api_key_name}' {detail}")


async def set_project_guest_role(index_id: IndexId, role: Roles):
    """
    Helper to set the guest role for an index.
    """
    await _update_role(email="*", role_context=index_id, role=role, ignore_missing=True)


async def get_project_guest_role(index_id: IndexId) -> GuestRole:
    """Get the guest role for an index. Note that this returns the Role not RoleRule!"""
    role = (await get_user_project_role(user=User(email=None), project_index=index_id)).role
    if role == Roles.ADMIN.name:
        return Roles.WRITER.name  # guests cannot be ADMIN.
    return role


async def _create_role(email: RoleEmailPattern, role_context: RoleContext, role: Roles):
    """
    Creates a role for a given email pattern and role context.
    Raises an error if a role for this email in this context already exists.
    """
    id = roles_index_id(email, role_context)
    if role == Roles.NONE:
        raise HTTPException(422, "Cannot create a role with Role.NONE.")

    user_role = RoleRule(email=email, role_context=role_context, role=role.name)
    await es().create(index=roles_index_name(), id=id, document=user_role.model_dump(), refresh=True)


async def _update_role(email: RoleEmailPattern, role_context: RoleContext, role: Roles, ignore_missing: bool = False):
    """
    Updates (or creates) a role for a given email pattern and role context.
    """
    id = roles_index_id(email, role_context)
    if role == Roles.NONE:
        await _delete_role(email, role_context, ignore_missing=ignore_missing)

    user_role = RoleRule(email=email, role_context=role_context, role=role.name)
    await es().update(index=roles_index_name(), id=id, doc=user_role.model_dump(), doc_as_upsert=ignore_missing, refresh=True)


async def _delete_role(email: RoleEmailPattern, role_context: RoleContext, ignore_missing: bool = False):
    elastic = es().options(ignore_status=404) if ignore_missing else es()
    await elastic.delete(index=roles_index_name(), id=roles_index_id(email, role_context), refresh=True)


async def _list_roles(
    emails: list[RoleEmailPattern] | None = None,
    role_contexts: list[RoleContext] | None = None,
    min_role: Roles | None = None,
    only_projects: bool = False,
) -> AsyncIterable[RoleRule]:
    """
    List roles, optionally filtered by user, minimum role, role contexts, and minimum match quality.

    :param role_emails: List of email patterns to filter on (or None for all users)
    :param min_role: The minimum global role of the user (or None for all roles)
    :param role_contexts: List of role contexts to filter on (or None for all contexts)
    :param min_match: The minimum match quality (or None for all matches)
    """
    query: dict = {"bool": {"must": []}}

    if emails is not None:
        query["bool"]["must"].append({"terms": {"email": emails}})

    if role_contexts is not None:
        query["bool"]["must"].append({"terms": {"role_context": role_contexts}})

    if min_role is not None:
        query["bool"]["must"].append(_min_role_query(min_role))

    if only_projects:
        query["bool"]["must"].append({"bool": {"must_not": {"term": {"role_context": "_server"}}}})

    async for id, user_role in index_scan(roles_index_name(), query=query):
        yield RoleRule.model_validate(user_role)


def _user_to_role_emails(user: User):
    """
    Given a user, return a list of email patterns that should be checked for roles.
    """
    # If no email is given, only the guest role (*) applies
    if user.email is None:
        return ["*"]
    # Otherwise, check exact email, domain wildcard, and guest role
    return [user.email, "*@" + user.email.split("@")[-1], "*"]


def _min_role_query(min_role: Roles):
    roles = [role.name for role in Roles if role >= min_role]
    return {"terms": {"role": roles}}


def _match_strength(email: RoleEmailPattern) -> int:
    """Could also just use len(email), but this is more explicit"""
    if email == "*":
        return 1
    elif email.startswith("*@"):
        return 2
    else:
        return 3


async def _get_user_matches(user: User, role_matches: AsyncIterable[RoleRule]) -> list[RoleRule]:
    """
    From a list of role matches for an email address, return the correct role for the user.
    - If there are multiple matches, use the strongest match (exact > domain > guest)
    - If the user has role restrictions, do not return roles stronger than the maximum allowed role for that context.
    """
    # use tuples of (strength, RoleRule) for each role context to sort out the strongest matches
    strongest_matches: dict[RoleContext, tuple[int, RoleRule]] = {}

    async for match in role_matches:
        context = match.role_context
        strength = _match_strength(match.email)

        if context in strongest_matches:
            current_strength = strongest_matches[context][0]
            if strength > current_strength:
                strongest_matches[context] = (strength, match)
        else:
            strongest_matches[context] = (strength, match)

    return [match for strength, match in strongest_matches.values()]


def restrict_role(user: User, role_rule: RoleRule) -> RoleRule:
    """
    Apply API key role restrictions
    """
    if role_rule.role == Roles.NONE or user.api_key_restrictions is None:
        return role_rule

    if role_rule.role_context == "_server":
        server_role = user.api_key_restrictions.server_role or None
        if server_role and Roles[role_rule.role] > Roles[server_role]:
            role_rule.role = server_role
        return role_rule

    default_project_role = user.api_key_restrictions.default_project_role or None
    project_roles = user.api_key_restrictions.project_roles or None
    project_role = project_roles.get(role_rule.role_context, None) if project_roles else None

    if project_role:
        if Roles[role_rule.role] > Roles[project_role]:
            role_rule.role = project_role
    elif default_project_role:
        if Roles[role_rule.role] > Roles[default_project_role]:
            role_rule.role = default_project_role

    return role_rule
