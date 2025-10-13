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

import hashlib
import json
import logging
from enum import IntEnum
from typing import Any, Iterable, Literal, Mapping, NamedTuple, Optional

import elasticsearch.helpers
from elasticsearch import NotFoundError

# from amcat4.api.common import py2dict
from amcat4.config import get_settings
from amcat4.elastic import es
from amcat4.systemdata.fields import (
    coerce_type,
    create_fields,
    create_or_verify_tag_field,
    get_fields,
)
from amcat4.models import ContactInfo, CreateField, FieldType


class Role(IntEnum):
    NONE = 0
    METAREADER = 10
    READER = 20
    WRITER = 30
    ADMIN = 40


class GuestRole(IntEnum):
    NONE = 0
    METAREADER = 10
    READER = 20
    WRITER = 30


ADMIN_USER = "_admin"
GUEST_USER = "_guest"
GLOBAL_ROLES = "_global"


class Index(NamedTuple):
    id: str
    name: str
    description: Optional[str]
    guest_role: GuestRole
    archived: Optional[str]
    roles: dict[str, Role]
    folder: Optional[str]
    image_url: Optional[str]
    contact: Optional[list[ContactInfo]]


class IndexDoesNotExist(ValueError):
    pass


def refresh_index(index: str):
    """
    Refresh the elasticsearch index
    """
    es().indices.refresh(index=index)


def list_all_indices() -> Iterable[Index]:
    """
    List all known indices, e.g. indices registered in this amcat4 instance
    """
    for index in elasticsearch.helpers.scan(es(), index=get_settings().system_index, fields=[], _source=True):
        ix = _index_from_elastic(index)
        if ix.id != GLOBAL_ROLES:
            yield ix


def list_user_indices(email: str) -> Iterable[tuple[Index, Role]]:
    """
    List all indices this user has access to, and add the user roles to the index
    """

    check_role = get_global_role(email) != Role.ADMIN and get_settings().auth != "no_auth"

    # TODO: replace list_all_indices with a more efficient ES query

    for index in list_all_indices():
        user_role = get_index_user_role(index.guest_role, index.roles, email)

        if check_role and user_role == Role.NONE and index.guest_role == GuestRole.NONE:
            continue

        yield index, user_role


def _index_from_elastic(index):
    src = index["_source"]

    guest_role = src.get("guest_role", "NONE")
    guest_role = GuestRole[guest_role] if guest_role in GuestRole.__members__ else GuestRole.NONE

    return Index(
        id=index["_id"],
        name=src.get("name", index["_id"]),
        description=src.get("description"),
        guest_role=guest_role,
        roles=_roles_from_elastic(src.get("roles", [])),
        archived=src.get("archived"),
        folder=src.get("folder"),
        image_url=src.get("image_url"),
        contact=src.get("contact"),
    )


def get_index_user_role(guest_role: GuestRole, role_dict: dict[str, Role], email: str):
    """
    Returns the role of this user on this index.
    """
    user_role = guest_role.name

    # Now match any roles based on email
    for email_matcher, role in role_dict.items():
        if email_matcher.startswith("*@"):
            # domain match
            domain = email_matcher[2:]
            if email.endswith(f"@{domain}"):
                user_role = role.name
                continue
        elif email == email_matcher:
            # exact match
            user_role = role.name
            break

    return Role[user_role]


def get_index(index: str) -> Index:
    try:
        index_resp = es().get(index=get_settings().system_index, id=index)
    except NotFoundError:
        raise IndexDoesNotExist(index)
    return _index_from_elastic(index_resp)


def create_index(
    index: str,
    guest_role: Optional[GuestRole] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    admin: Optional[str] = None,
    folder: Optional[str] = None,
    image_url: Optional[str] = None,
    contact: Optional[list[ContactInfo]] = None,
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
        guest_role=guest_role or GuestRole.NONE,
        name=name or index,
        description=description or "",
        admin=admin,
        folder=folder,
        image_url=image_url,
        contact=contact,
    )


def register_index(
    index: str,
    guest_role: Optional[GuestRole] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    admin: Optional[str] = None,
    folder: Optional[str] = None,
    image_url: Optional[str] = None,
    contact: Optional[list[ContactInfo]] = None,
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
            guest_role=guest_role.name if guest_role is not None else "NONE",
            folder=folder,
            image_url=image_url,
            contact=[m.model_dump() for m in contact] if contact else None,
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
        refresh=True,
    )


def set_global_role(email: str, role: Role | None):
    """
    Set the global role for this user
    """
    set_role(index=GLOBAL_ROLES, email=email, role=role)


def set_guest_role(index: str, guest_role: Optional[GuestRole]):
    """
    Set the guest role for this index. Set to None to disallow guest access
    """
    modify_index(index, guest_role=GuestRole.NONE if guest_role is None else guest_role)


def modify_index(
    index: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    guest_role: Optional[GuestRole] = None,
    archived: Optional[str] = None,
    folder: Optional[str] = None,
    image_url: Optional[str] = None,
    contact: Optional[list[ContactInfo]] = None,
):
    doc = dict(
        name=name,
        description=description,
        guest_role=guest_role.name if guest_role is not None else None,
        archived=archived,
        folder=folder,
        image_url=image_url,
        contact=[m.model_dump() for m in contact] if contact else None,
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
    Retrieve the role of this user on this index, or the guest role if user has no role.
    Index can also be the GLOBAL_ROLES pseudo-index to get the global role of this user.
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

    guest_role = doc["_source"].get("guest_role", "NONE")
    guest_role = GuestRole[guest_role] if guest_role in Role.__members__ else GuestRole.NONE
    roles = _roles_from_elastic(doc["_source"].get("roles", []))

    user_role = get_index_user_role(guest_role, roles, email)
    return user_role


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
    if role and role in Role.__members__:
        return Role[role]
    return Role.NONE


def get_global_role(email: str, only_es: bool = False) -> Role:
    """
    Retrieve the global role of this user

    :returns: a Role object, or None if the user has no role
    """
    # The 'admin' user is given to everyone in the no_auth scenario
    if only_es is False:
        if email == get_settings().admin_email or email == ADMIN_USER:
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
    for ix, role in list_user_indices(email):
        set_role(ix.id, email, None)


def create_id(document: dict, identifiers: list[str]) -> str:
    """
    Create the _id for a document.
    """

    if len(identifiers) == 0:
        raise ValueError("Can only create id if identifiers are specified")

    id_keys = sorted(set(identifiers) & set(document.keys()))
    id_fields = {k: document[k] for k in id_keys}
    hash_str = json.dumps(id_fields, sort_keys=True, ensure_ascii=True, default=str).encode("ascii")
    m = hashlib.sha224()
    m.update(hash_str)
    return m.hexdigest()


def upload_documents(
    index: str,
    documents: list[dict[str, Any]],
    fields: Mapping[str, FieldType | CreateField] | None = None,
    op_type: Literal["index", "create", "update"] = "index",
    raise_on_error=False,
):
    """
    Upload documents to this index

    :param index: The name of the index (without prefix)
    :param documents: A sequence of article dictionaries
    :param fields: A mapping of fieldname:UpdateField for field types
    :param op_type: Whether to 'index' new documents (create or overwrite), 'create' (only create) or 'update' existing documents
    """
    if fields:
        create_fields(index, fields)

    actions = list(upload_document_es_actions(index, documents, op_type))
    try:
        successes, failures = elasticsearch.helpers.bulk(
            es(),
            actions,
            stats_only=False,
            raise_on_error=raise_on_error,
        )
    except elasticsearch.helpers.BulkIndexError as e:
        logging.error("Error on indexing: " + json.dumps(e.errors, indent=2, default=str))
        if e.errors:
            _, error = list(e.errors[0].items())[0]
            reason = error.get("error", {}).get("reason", error)
            e.args = e.args + (f"First error: {reason}",)
        raise

    return dict(successes=successes, failures=failures)


def upload_document_es_actions(index, documents, op_type):
    field_settings = get_fields(index)
    identifiers = [k for k, v in field_settings.items() if v.identifier is True]
    for document in documents:
        doc = dict()
        action = {"_op_type": op_type, "_index": index}

        for key in document.keys():
            if key in field_settings:
                doc[key] = coerce_type(document[key], field_settings[key].type)
            elif key == "_id":
                if len(identifiers) > 0:
                    raise ValueError(f"This index uses identifiers ({identifiers}), so you cannot set the _id directly.")
                action["_id"] = document[key]
            else:
                raise ValueError(f"Field '{key}' is not yet specified")

        if len(identifiers) > 0:
            action["_id"] = create_id(document, identifiers)
            # if no _id is given and no identifiers are used, elasticsearch creates a cool unique one

        # https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html
        if op_type == "update":
            if "_id" not in action:
                raise ValueError("Update requires _id")
            action["doc"] = doc
            action["doc_as_upsert"] = True
        else:
            action = {**doc, **action}

        yield action


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

    :param index: The Pname of the index
    :param doc_id: The document id (hash)
    """
    es().delete(index=index, id=doc_id)


UPDATE_SCRIPTS = dict(
    add="""
    if (ctx._source[params.field] == null) {
      ctx._source[params.field] = [params.tag]
    } else {
      if (ctx._source[params.field].contains(params.tag)) {
        ctx.op = 'noop';
      } else {
        ctx._source[params.field].add(params.tag)
      }
    }
    """,
    remove="""
    if (ctx._source[params.field] != null && ctx._source[params.field].contains(params.tag)) {
      ctx._source[params.field].removeAll([params.tag]);
      if (ctx._source[params.field].size() == 0) {
        ctx._source.remove(params.field);
      }
    } else {
      ctx.op = 'noop';
    }
    """,
)


def update_tag_by_query(
    index: str | list[str],
    action: Literal["add", "remove"],
    query: dict,
    field: str,
    tag: str,
):
    create_or_verify_tag_field(index, field)
    script = dict(
        source=UPDATE_SCRIPTS[action],
        lang="painless",
        params=dict(field=field, tag=tag),
    )
    result = es().update_by_query(index=index, script=script, **query, refresh=True)
    return dict(updated=result["updated"], total=result["total"])


def update_documents_by_query(index: str | list[str], query: dict, field: str, value: Any):
    if value is None:
        script = dict(
            source="ctx._source.remove(params.field)",
            lang="painless",
            params=dict(field=field),
        )
    else:
        script = dict(
            source="ctx._source[params.field] = params.value",
            lang="painless",
            params=dict(field=field, value=value),
        )
    return es().update_by_query(index=index, query=query, script=script, refresh=True)


def delete_documents_by_query(index: str | list[str], query: dict):
    return es().delete_by_query(index=index, query=query)
