"""
Index and authorization management

Encapsulates elasticsearch indices and provides authorisation through user roles

Authorisation rules:
- There are 5 increasing levels of authorisation: None, metareader, reader, writer, admin
- The 'admin' user automatically has admin rights everywhere (or globally?)
- Users can have a global role and a role on any index. Every index can also have a guest role
- Global roles:
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
- This system index contains authorization records: {index, email, role} with id f"{index}|{email}"
- Index _global defines the global roles of a user
- Email _guest defubes the guest roles of an index
- (elasticsearch index names cannot start with _ or contain |)
- Every index should have a guest role defined (possibly None), i.e. the list of guest roles is the list of indices
"""
from enum import IntEnum
from typing import List, Set, Optional, Iterable, Tuple

import elasticsearch.helpers
from elasticsearch import NotFoundError

from amcat4.config import get_settings
from amcat4.elastic import es, DEFAULT_MAPPING


class Role(IntEnum):
    NONE = 0
    METAREADER = 10
    READER = 20
    WRITER = 30
    ADMIN = 40


GUEST_USER = "_guest"
GLOBAL_ROLES = "_global"


def list_all_indices(exclude_system_index=True) -> List[str]:
    """
    List all indices on the connected elastic cluster.
    You should probably use the methods in amcat4.index rather than this.
    """
    result = es().indices.get(index="*")
    exclude = get_settings().system_index if exclude_system_index else None
    return [x for x in result.keys() if not (x == exclude)]


def list_known_indices(email: str = None) -> Set[str]:
    """
    List all known indices, e.g. indices registered in this amcat4 instance
    :param email: if given, only list indices visible to this user
    """
    if email is None or get_global_role(email) == Role.ADMIN:
        query = {"query": {"term": {"email": GUEST_USER}}}
    else:
        # Either user has a role in the index, or index has a non-empty guest role
        query = {"query": {"bool": {"should": [
            {"term": {"email": email}},
            {"bool": {
                "must": [{"term": {"email": GUEST_USER}}],
                "must_not": [{"term": {"role": Role.NONE.name}}]}}
        ]}}}
    indices = list(elasticsearch.helpers.scan(
        es(), index=get_settings().system_index, fields=["index"], _source=False, query=query))
    return {ix['fields']["index"][0] for ix in indices} - {GLOBAL_ROLES}


def create_index(index: str, guest_role: Role = Role.NONE) -> None:
    """
    Create a new index in elasticsearch and register it with this AmCAT instance
    """
    es().indices.create(index=index, mappings={'properties': DEFAULT_MAPPING})
    register_index(index, guest_role=guest_role)


def register_index(index: str, guest_role: Role = Role.NONE) -> None:
    """
    Register an existing elastic index with this AmCAT instance, i.e. create an entry in the system index
    """
    if not es().indices.exists(index=index):
        raise ValueError(f"Index {index} does not exist")
    system_index = get_settings().system_index
    if es().exists(index=system_index, id="{name}|_guest"):
        raise ValueError(f"Index {index} is already registered")
    _set_auth_entry(index, GUEST_USER, guest_role)


def refresh(index: str):
    """
    Refresh the elasticsearch index
    """
    es().indices.refresh(index=index)


def delete_index(index: str, ignore_missing=False) -> None:
    """
    Delete an index from AmCAT and deregister it from this instance
    :param index: The name of the index
    :param ignore_missing: If True, do not throw exception if index does not exist
    """
    deregister_index(index, ignore_missing=ignore_missing)
    es().indices.delete(index=index, ignore=([404] if ignore_missing else []))


def deregister_index(index: str, ignore_missing=False) -> None:
    """
    Deregister an existing elastic index from this AmCAT instance, i.e. remove all authorization entries
    :param index: The name of the index
    :param ignore_missing: If True, do not throw exception if index does not exist
    """
    try:
        es().delete_by_query(index=get_settings().system_index, body={"query": {"term": {"index": index}}})
    except NotFoundError:
        if not ignore_missing:
            raise
    else:
        refresh(get_settings().system_index)


def set_role(index: str, email: str, role: Role):
    """
    Set the role for this user on the given index)
    """
    _set_auth_entry(index=index, email=email, role=role)


def set_global_role(email: str, role: Role):
    """
    Set the global role for this user
    """
    set_role(index=GLOBAL_ROLES, email=email, role=role)


def set_guest_role(index: str, role: Role):
    """
    Set the guest role for this index
    """
    set_role(index=index, email=GUEST_USER, role=role)


def remove_role(index: str, email: str):
    """
    Remove the role of this user on the given index
    """
    if index is None:
        index = GLOBAL_ROLES
    system_index = get_settings().system_index
    es().delete(index=system_index, id=f"{index}|{email}", ignore=True)
    es().indices.refresh(index=system_index)


def remove_global_role(email: str):
    """
    Remove the global role of this user
    """
    remove_role(index=GLOBAL_ROLES, email=email)


def _get_role(index: str, email: str) -> Optional[Role]:
    """
    Retrieve the role of this user on this index (or None if no role exists)
    """
    try:
        doc = es().get(index=get_settings().system_index, id=f"{index}|{email}")
    except NotFoundError:
        return None
    role = doc["_source"]["role"]
    return Role[role.upper()]


def get_role(index: str, email: str) -> Optional[Role]:
    """
    Retrieve the role of this user on this index, or the guest role if user has no role
    Raises a ValueError if the index does not exist
    :returns: a Role object, or Role.NONE if the user has no role and no guest role exists
    """
    role = _get_role(index, email)
    if role is None:
        if index == GLOBAL_ROLES:
            return None
        return get_guest_role(index)
    return role


def get_guest_role(index: str) -> Optional[Role]:
    """
    Return the guest role for this index, raising a ValueError if the index does not exist
    :returns: a Role object, or None if global role was NONE
    """
    role = _get_role(index=index, email=GUEST_USER)
    if role is None:
        raise ValueError(f"Index {index} does not exist")
    return None if role == Role.NONE else role


def get_global_role(email: str) -> Optional[Role]:
    """
    Retrieve the global role of this user

    :returns: a Role object, or None if the user has no role
    """
    return get_role(index=GLOBAL_ROLES, email=email)


def list_users(index: str) -> Iterable[Tuple[str, Role]]:
    """"
    List all users and their roles on the given index
    :param index: The index to list roles for. If None, list global roles
    :returns: an iterable of (user, Role) pairs
    """
    r = es().search(index=get_settings().system_index, query={"term": {"index": index}})
    for doc in r['hits']['hits']:
        email = doc['_source']['email']
        if email != GUEST_USER:
            yield email, Role[doc['_source']['role'].upper()]


def list_global_users() -> Iterable[Tuple[str, Role]]:
    """"
    List all global users and their roles
    :returns: an iterable of (user, Role) pairs
    """
    return list_users(index=GLOBAL_ROLES)


def _set_auth_entry(index: str, email: str, role: Role):
    system_index = get_settings().system_index
    es().index(index=system_index, id=f"{index}|{email}",
               document=dict(index=index, email=email, role=role.name))
    refresh(system_index)


def delete_user(email: str) -> None:
    """Delete this user from all indices"""
    system_index = get_settings().system_index
    es().delete_by_query(index=system_index, body={"query": {"term": {"email": email}}})
    refresh(system_index)
