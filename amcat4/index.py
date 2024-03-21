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
- We define the mappings (field types) based on existing elasticsearch mappings,
    but use field metadata to define specific fields.
"""

import collections
from datetime import datetime
from enum import IntEnum
from typing import Any, Iterable, Optional, Literal

import hashlib
import json

import elasticsearch.helpers
from elasticsearch import NotFoundError

# from amcat4.api.common import py2dict
from amcat4.config import get_settings
from amcat4.elastic import es
from amcat4.fields import (
    coerce_type,
    create_fields,
    get_fields,
)
from amcat4.models import CreateField, ElasticType, Field


class Role(IntEnum):
    NONE = 0
    METAREADER = 10
    READER = 20
    WRITER = 30
    ADMIN = 40


GUEST_USER = "_guest"
GLOBAL_ROLES = "_global"

Index = collections.namedtuple(
    "Index",
    ["id", "name", "description", "guest_role", "archived", "roles", "summary_field"],
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


def list_known_indices(email: str | None = None) -> Iterable[Index]:
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
        guest_role=guest_role,
        archived=src.get("archived"),
        roles=_roles_from_elastic(src.get("roles", [])),
        summary_field=src.get("summary_field"),
    )


def get_index(index: str) -> Index:
    try:
        index_resp = es().get(index=get_settings().system_index, id=index)
    except NotFoundError:
        raise IndexDoesNotExist(index)
    return _index_from_elastic(index_resp)


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
    try:
        get_index(index)
        raise ValueError(f'Index "{index}" already exists')
    except IndexDoesNotExist:
        pass

    es().indices.create(index=index, mappings={"properties": {}})

    register_index(
        index,
        guest_role=guest_role or Role.NONE,
        name=name or index,
        description=description or "",
        admin=admin,
    )

    # update_fields(index, DEFAULT_FIELDS)


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

    if guest_role is not None:
        guest_role_int = guest_role.value
    else:
        guest_role_int = Role.NONE.value

    es().index(
        index=system_index,
        id=index,
        document=dict(
            name=(name or index),
            roles=roles,
            description=description,
            guest_role=guest_role_int,
        ),
    )
    refresh_index(system_index)


def delete_index(index: str, ignore_missing=False) -> None:
    """
    Delete an index from AmCAT and deregister it from this instance
    :param index: The name of the index
    :param ignore_missing: If True, do not throw exception if index does not exist
    """
    _es = es().options(ignore_status=404) if ignore_missing else es()
    _es.indices.delete(index=index)
    deregister_index(index, ignore_missing=ignore_missing)


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


def _roles_from_elastic(roles: list[dict]) -> dict[str, Role]:
    return {role["email"]: Role[role["role"].upper()] for role in roles}


def _roles_to_elastic(roles: dict) -> list[dict]:
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


def set_global_role(email: str, role: Role | None):
    """
    Set the global role for this user
    """
    set_role(index=GLOBAL_ROLES, email=email, role=role)


def set_guest_role(index: str, guest_role: Optional[Role]):
    """
    Set the guest role for this index. Set to None to disallow guest access
    """
    modify_index(index, guest_role=Role.NONE if guest_role is None else guest_role)


def modify_index(
    index: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    guest_role: Optional[Role] = None,
    archived: Optional[str] = None,
    summary_field=None,
):
    doc = dict(
        name=name,
        description=description,
        guest_role=guest_role and guest_role.value,
        summary_field=summary_field,
        archived=archived,
    )

    doc = {x: v for (x, v) in doc.items() if v is not None}
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


def user_exists(email: str, index: str = GLOBAL_ROLES) -> bool:
    """
    Check if a user exists on server (GLOBAL_ROLES) or in a specific index
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
    return email in roles_dict


def get_role(index: str, email: str) -> Role:
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
        return Role.NONE

    return get_guest_role(index)


def get_guest_role(index: str) -> Role:
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
    return Role.NONE


def get_global_role(email: str, only_es: bool = False) -> Role:
    """
    Retrieve the global role of this user

    :returns: a Role object, or None if the user has no role
    """
    # The 'admin' user is given to everyone in the no_auth scenario
    if only_es is False:
        if email == get_settings().admin_email or email == "admin":
            return Role.ADMIN
    return get_role(index=GLOBAL_ROLES, email=email)


def list_users(index: str) -> dict[str, Role]:
    """ "
    List all users and their roles on the given index
    :param index: The index to list roles for.
    :returns: an iterable of (user, Role) pairs
    """
    r = es().get(index=get_settings().system_index, id=index, source_includes="roles")
    return _roles_from_elastic(r["_source"].get("roles", []))


def list_global_users() -> dict[str, Role]:
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


def _get_hash(document: dict, field_settings: dict[str, Field]) -> str:
    """
    Get the hash for a document
    """

    identifiers = [k for k, v in field_settings.items() if v.identifier]
    if len(identifiers) == 0:
        # if no identifiers specified, id is hash of entire document
        hash_values = document
    else:
        # if identifiers specified, id is hash of those fields
        hash_values = {k: document.get(k) for k in identifiers if k in document}

    hash_str = json.dumps(hash_values, sort_keys=True, ensure_ascii=True, default=str).encode("ascii")
    m = hashlib.sha224()
    m.update(hash_str)
    return m.hexdigest()


def upload_documents(
    index: str, documents: list[dict[str, Any]], fields: dict[str, CreateField] | None = None, op_type="index"
):
    """
    Upload documents to this index

    :param index: The name of the index (without prefix)
    :param documents: A sequence of article dictionaries
    :param fields: A mapping of fieldname:UpdateField for field types
    """

    if fields:
        create_fields(index, fields)

    def es_actions(index, documents, op_type):
        field_settings = get_fields(index)
        for document in documents:

            for key in document.keys():
                if key == "_id":
                    continue
                if key not in field_settings:
                    raise ValueError(f"The type for field {key} is not yet specified")
                document[key] = coerce_type(document[key], field_settings[key].elastic_type)
            if "_id" not in document:
                document["_id"] = _get_hash(document, field_settings)
            yield {"_op_type": op_type, "_index": index, **document}

    actions = list(es_actions(index, documents, op_type))
    successes, failures = elasticsearch.helpers.bulk(es(), actions, stats_only=True, raise_on_error=False)
    print(successes, failures)
    return dict(successes=successes, failures=failures)


def get_document(index: str, doc_id: str, **kargs) -> dict:
    """
    Get a single document from this index.

    :param index: The name of the index
    :param doc_id: The document id (hash)
    :return: the source dict of the document
    """
    return es().get(index=index, id=doc_id, **kargs)["_source"]


def update_document(index: str, doc_id: str, fields: dict):
    """
    Update a single document.

    :param index: The name of the index
    :param doc_id: The document id (hash)
    :param fields: a {field: value} mapping of fields to update
    """
    # Mypy doesn't understand that body= has been deprecated already...
    es().update(index=index, id=doc_id, doc=fields)  # type: ignore


def delete_document(index: str, doc_id: str):
    """
    Delete a single document

    :param index: The name of the index
    :param doc_id: The document id (hash)
    """
    es().delete(index=index, id=doc_id)


def update_by_query(index: str | list[str], script: str, query: dict, params: dict | None = None):
    script_dict = dict(source=script, lang="painless", params=params or {})
    es().update_by_query(index=index, script=script_dict, **query)


TAG_SCRIPTS = dict(
    add="""
    if (ctx._source[params.field] == null) {
      ctx._source[params.field] = [params.tag]
    } else if (!ctx._source[params.field].contains(params.tag)) {
      ctx._source[params.field].add(params.tag)
    }
    """,
    remove="""
    if (ctx._source[params.field] != null && ctx._source[params.field].contains(params.tag)) {
      ctx._source[params.field].removeAll([params.tag]);
      if (ctx._source[params.field].size() == 0) {
        ctx._source.remove(params.field);
      }
    }""",
)


def update_tag_by_query(index: str | list[str], action: Literal["add", "remove"], query: dict, field: str, tag: str):
    script = TAG_SCRIPTS[action]
    params = dict(field=field, tag=tag)
    update_by_query(index, script, query, params)
