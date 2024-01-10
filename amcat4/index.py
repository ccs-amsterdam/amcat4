"""
Index and authorization management

Encapsulates elasticsearch indices and provides authorisation through user roles

Authorisation rules:
- There are 5 increasing levels of authorisation: None, metareader, reader, writer, admin
- The 'admin' user automatically has admin rights everywhere (or globally?)
- Users can have a global role and a role on any index. Every index can also have a guest role
- Global roles:
  - Readers can see which indices exist, but cannot access them
  - Writers can create new projects and users (with at most their own global role)
  - Admins can delete projects and assign themselves a role on any index role
- Index roles:
  - None means an index cannot be viewed or accessed in any way (the index is invisible to the user)
  - Metareader means the user can read all properties, do queries, etc., but cannot read the 'text' attribute
    (this is mostly intended to provide access to metadata fields of copyrighted material)
  - Reader can read all properties, do queries, etc., but cannot make changes
  - Writers can add/delete documents, add/delete users (up to their own level), and make other changes (but not delete)
  - Admins can do whatever they want, including deleting the index
- If a user does not have an explicit role on an index, the guest role (if any) is used
- An unauthorized user can still get guest roles, so it can see any indices with a guest role

Note that these rules are not enforced in this module, they should be enforced by the API!

Elasticsearch implementation
- There is a system index (configurable name, default: amcat4_system)
- This system index contains a 'document' for each index:
    {name: "...", description:"...", guest_role: "...", roles: [{email, role}...]}
- A special _global document defines the global properties for this instance (name, roles)
"""
import collections
from enum import IntEnum
from typing import Dict, Iterable, List, Optional

import elasticsearch.helpers
from elasticsearch import NotFoundError

from amcat4.config import get_settings
from amcat4.elastic import DEFAULT_MAPPING, es, get_fields
from amcat4.models import FieldSettings, updateFieldSettings


class Role(IntEnum):
    METAREADER = 10
    READER = 20
    WRITER = 30
    ADMIN = 40


GUEST_USER = "_guest"
GLOBAL_ROLES = "_global"

Index = collections.namedtuple(
    "Index",
    ["id", "name", "description", "guest_role", "roles", "summary_field"],
)


class IndexDoesNotExist(ValueError):
    pass


def refresh_index(index: str):
    """
    Refresh the elasticsearch index
    """
    es().indices.refresh(index=index)


def refresh_system_index():
    """
    Refresh the elasticsearch index
    """
    es().indices.refresh(index=get_settings().system_index)


def list_known_indices(email: str = None) -> Iterable[Index]:
    """
    List all known indices, e.g. indices registered in this amcat4 instance
    :param email: if given, only list indices visible to this user
    """
    # TODO: Maybe this can be done with a smart query, rather than getting all indices and filtering in python?
    # I tried the following but had no luck
    # q_guest = {"bool" : {"filter": {"exists": {"field": "guest_role"}},
    #                      "must_not": {"term": {"guest_role": {"value": "none", "case_insensitive": True}}}}}
    # q_role = {"nested": {"path": "roles", "query": {"term": {"roles.email": email}}}}
    # query = {"bool": {"should": [q_guest, q_role]}}
    check_role = not (email is None or get_global_role(email) == Role.ADMIN or get_settings().auth == "no_auth")
    for index in elasticsearch.helpers.scan(es(), index=get_settings().system_index, fields=[], _source=True):
        ix = _index_from_elastic(index)
        if ix.name == GLOBAL_ROLES:
            continue
        if (not check_role) or (ix.guest_role) or (email in ix.roles):
            yield ix


def _index_from_elastic(index):
    src = index["_source"]
    guest_role = src.get("guest_role")
    return Index(
        id=index["_id"],
        name=src.get("name", index["_id"]),
        description=src.get("description"),
        guest_role=guest_role and guest_role != "NONE" and Role[guest_role.upper()],
        roles=_roles_from_elastic(src.get("roles", [])),
        summary_field=src.get("summary_field"),
    )


def get_index(index: str) -> Index:
    try:
        index = es().get(index=get_settings().system_index, id=index)
    except NotFoundError:
        raise IndexDoesNotExist(index)
    return _index_from_elastic(index)


def create_index(
    index: str,
    guest_role: Optional[Role] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    admin: Optional[str] = None,
) -> None:
    """
    Create a new index in elasticsearch and register it with this AmCAT instance
    """
    es().indices.create(index=index, mappings={"properties": DEFAULT_MAPPING})
    register_index(
        index,
        guest_role=guest_role,
        name=name,
        description=description,
        admin=admin,
    )


def register_index(
    index: str,
    guest_role: Optional[Role] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    admin: Optional[str] = None,
) -> None:
    """
    Register an existing elastic index with this AmCAT instance, i.e. create an entry in the system index
    """
    if not es().indices.exists(index=index):
        raise ValueError(f"Index {index} does not exist")
    system_index = get_settings().system_index
    if es().exists(index=system_index, id=index):
        raise ValueError(f"Index {index} is already registered")
    roles = [dict(email=admin, role="ADMIN")] if admin else []
    es().index(
        index=system_index,
        id=index,
        document=dict(
            name=(name or index),
            roles=roles,
            description=description,
            guest_role=guest_role and guest_role.name,
        ),
    )
    refresh_index(system_index)


def delete_index(index: str, ignore_missing=False) -> None:
    """
    Delete an index from AmCAT and deregister it from this instance
    :param index: The name of the index
    :param ignore_missing: If True, do not throw exception if index does not exist
    """
    deregister_index(index, ignore_missing=ignore_missing)
    _es = es().options(ignore_status=404) if ignore_missing else es()
    _es.indices.delete(index=index)


def deregister_index(index: str, ignore_missing=False) -> None:
    """
    Deregister an existing elastic index from this AmCAT instance, i.e. remove all authorization entries
    :param index: The name of the index
    :param ignore_missing: If True, do not throw exception if index does not exist
    """
    system_index = get_settings().system_index
    try:
        es().delete(index=system_index, id=index)
    except NotFoundError:
        if not ignore_missing:
            raise
    else:
        refresh_index(system_index)


def _roles_from_elastic(roles: List[Dict]) -> Dict[str, Role]:
    return {role["email"]: Role[role["role"].upper()] for role in roles}


def _roles_to_elastic(roles: dict) -> List[Dict]:
    return [{"email": email, "role": role.name} for (email, role) in roles.items()]


def set_role(index: str, email: str, role: Optional[Role]):
    """
    Set the role for this user on the given index)
    If role is None, remove the role
    """
    # TODO: It would probably be better to do this with a query script on elastic
    system_index = get_settings().system_index
    try:
        d = es().get(index=system_index, id=index, source_includes="roles")
    except NotFoundError:
        raise ValueError(f"Index {index} is not registered")
    roles_dict = _roles_from_elastic(d["_source"].get("roles", []))
    if role:
        roles_dict[email] = role
    else:
        if email not in roles_dict:
            return  # Nothing to change
        del roles_dict[email]
    es().update(
        index=system_index,
        id=index,
        doc=dict(roles=_roles_to_elastic(roles_dict)),
    )


def set_global_role(email: str, role: Role):
    """
    Set the global role for this user
    """
    set_role(index=GLOBAL_ROLES, email=email, role=role)


def set_guest_role(index: str, guest_role: Optional[Role]):
    """
    Set the guest role for this index. Set to None to disallow guest access
    """
    modify_index(index, guest_role=guest_role, remove_guest_role=(guest_role is None))


def _fields_settings_to_elastic(fields_settings: Dict[str, FieldSettings]) -> List[Dict]:
    return [{"field": field, "settings": settings} for field, settings in fields_settings.items()]


def _fields_settings_from_elastic(
    fields_settings: List[Dict],
) -> Dict[str, FieldSettings]:
    return {fs["field"]: fs["settings"] for fs in fields_settings}


def set_fields_settings(index: str, new_fields_settings: Dict[str, FieldSettings]):
    """
    Set the fields settings for this index
    """
    system_index = get_settings().system_index
    try:
        d = es().get(index=system_index, id=index, source_includes="fields_settings")
    except NotFoundError:
        raise ValueError(f"Index {index} is not registered")
    fields_settings = _fields_settings_from_elastic(d["_source"].get("fields_settings", {}))

    for field, new_settings in new_fields_settings.items():
        current: FieldSettings = fields_settings.get(field, FieldSettings())
        fields_settings[field] = updateFieldSettings(current, new_settings)

    es().update(
        index=system_index,
        id=index,
        doc=dict(roles=_fields_settings_to_elastic(fields_settings)),
    )


def modify_index(
    index: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    guest_role: Optional[Role] = None,
    remove_guest_role=False,
    summary_field=None,
):
    doc = dict(
        name=name,
        description=description,
        guest_role=guest_role and guest_role.name,
        summary_field=summary_field,
    )
    if summary_field is not None:
        f = get_fields(index)
        if summary_field not in f:
            raise ValueError(f"Summary field {summary_field} does not exist!")
        if f[summary_field]["type"] not in ["date", "keyword", "tag"]:
            raise ValueError(f"Summary field {summary_field} should be date, keyword or tag, not {f[summary_field]['type']}!")
    doc = {x: v for (x, v) in doc.items() if v}
    if remove_guest_role:
        doc["guest_role"] = None
    if doc:
        es().update(index=get_settings().system_index, id=index, doc=doc)


def remove_role(index: str, email: str):
    """
    Remove the role of this user on the given index
    """
    set_role(index, email, role=None)


def remove_global_role(email: str):
    """
    Remove the global role of this user
    """
    remove_role(index=GLOBAL_ROLES, email=email)


def get_role(index: str, email: str) -> Optional[Role]:
    """
    Retrieve the role of this user on this index, or the guest role if user has no role
    Raises a ValueError if the index does not exist
    :returns: a Role object, or Role.NONE if the user has no role and no guest role exists
    """
    try:
        doc = es().get(
            index=get_settings().system_index,
            id=index,
            source_includes=["roles", "guest_role"],
        )
    except NotFoundError:
        raise IndexDoesNotExist(f"Index {index} does not exist or is not registered")
    roles_dict = _roles_from_elastic(doc["_source"].get("roles", []))
    if role := roles_dict.get(email):
        return role
    if index == GLOBAL_ROLES:
        return None
    role = doc["_source"].get("guest_role", None)
    if role and role.lower() != "none":
        return Role[role]
    return None


def get_guest_role(index: str) -> Optional[Role]:
    """
    Return the guest role for this index, raising a IndexDoesNotExist if the index does not exist
    :returns: a Role object, or None if global role was NONE
    """
    try:
        d = es().get(
            index=get_settings().system_index,
            id=index,
            source_includes="guest_role",
        )
    except NotFoundError:
        raise IndexDoesNotExist(index)
    role = d["_source"].get("guest_role")
    if role and role.lower() != "none":
        return Role[role]
    return None


def get_global_role(email: str, only_es: bool = False) -> Optional[Role]:
    """
    Retrieve the global role of this user

    :returns: a Role object, or None if the user has no role
    """
    # The 'admin' user is given to everyone in the no_auth scenario
    if only_es is False:
        if email == get_settings().admin_email or email == "admin":
            return Role.ADMIN
    return get_role(index=GLOBAL_ROLES, email=email)


def get_fields_settings(index: str) -> Dict[str, FieldSettings]:
    """
    Retrieve the fields settings for this index
    """
    try:
        d = es().get(
            index=get_settings().system_index,
            id=index,
            source_includes="fields_settings",
        )
    except NotFoundError:
        raise IndexDoesNotExist(index)
    return _fields_settings_from_elastic(d["_source"].get("fields_settings", {}))


def list_users(index: str) -> Dict[str, Role]:
    """ "
    List all users and their roles on the given index
    :param index: The index to list roles for.
    :returns: an iterable of (user, Role) pairs
    """
    r = es().get(index=get_settings().system_index, id=index, source_includes="roles")
    return _roles_from_elastic(r["_source"].get("roles", []))


def list_global_users() -> Dict[str, Role]:
    """ "
    List all global users and their roles
    :returns: an iterable of (user, Role) pairs
    """
    return list_users(index=GLOBAL_ROLES)


def delete_user(email: str) -> None:
    """Delete this user from all indices"""
    set_global_role(email, None)
    for ix in list_known_indices(email):
        set_role(ix.id, email, None)
