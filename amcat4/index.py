"""
Index and authorization management

Encapsulates elasticsearch indices  and provides authorisation through user roles

Authorisation rules:
- There are 5 increasing levels of authorisation: None, metareader, reader, writer, admin
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
"""
from typing import List, Sequence, Set

import elasticsearch.helpers
from elasticsearch import NotFoundError

from amcat4.config import get_settings
from amcat4.elastic import es, DEFAULT_MAPPING


def list_all_indices(exclude_system_index=True) -> List[str]:
    """
    List all indices on the connected elastic cluster.
    You should probably use the methods in amcat4.index rather than this.
    """
    result = es().indices.get(index="*")
    exclude = get_settings().system_index if exclude_system_index else None
    return [x for x in result.keys() if not (x == exclude)]


def create_index(name: str, guest_role=None) -> None:
    """
    Create a new index in elasticsearch and register it with this AmCAT instance
    """
    es().indices.create(index=name, mappings={'properties': DEFAULT_MAPPING})
    register_index(name, guest_role=guest_role)


def register_index(name: str, guest_role=None) -> None:
    """
    Register an existing elastic index with this AmCAT instance, i.e. create an entry in the system index
    """
    if not es().indices.exists(index=name):
        raise ValueError(f"Index {name} does not exist")
    system_index = get_settings().system_index
    if es().exists(index=system_index, id=name):
        raise ValueError(f"Index {name} is already registered")
    es().index(index=system_index, id=name, document={guest_role: guest_role})
    refresh(system_index)


def list_known_indices() -> Set[str]:
    """
    List all known indices, e.g. indices registered in this amcat4 instance
    """
    indices = list(elasticsearch.helpers.scan(es(), index=get_settings().system_index))
    print(indices)
    return {ix["_id"] for ix in indices}


def refresh(index: str):
    """
    Refresh the elasticsearch index
    """
    es().indices.refresh(index=index)


def index_exists(name: str) -> bool:
    """
    Check if an index with this name exists
    """
    return es().indices.exists(index=name)


def delete_index(name: str, ignore_missing=False) -> None:
    """
    Delete an index from AmCAT and deregister it from this instance
    :param name: The name of the index (without prefix)
    :param ignore_missing: If True, do not throw exception if index does not exist
    """
    deregister_index(name, ignore_missing=ignore_missing)
    es().indices.delete(index=name, ignore=([404] if ignore_missing else []))


def deregister_index(name: str, ignore_missing=False) -> None:
    """
    Deregister an existing elastic index from this AmCAT instance, i.e. remove the entry in the system index
    :param name: The name of the index (without prefix)
    :param ignore_missing: If True, do not throw exception if index does not exist
    """
    try:
        es().delete(index=get_settings().system_index, id=name)
    except NotFoundError:
        if not ignore_missing:
            raise
    else:
        refresh(get_settings().system_index)
