from amcat4.systemdata.versions.v2 import ROLES_INDEX, roles_index_id
from amcat4.elastic import es
from amcat4.models import RoleType
from enum import IntEnum


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


def elastic_set_role(email: str, index: str | None, role: RoleType | None) -> list[dict]:
    id = roles_index_id(email, index)
    doc = {"index": index, "email": email, "role": role}

    if role is None:
        es().delete(index=ROLES_INDEX, id=id, refresh=True)
    else:
        es().update(index=ROLES_INDEX, id=id, doc=doc, doc_as_upsert=True, refresh=True)


def elastic_get_role(email, index: str | None = None) -> Role:
    id = roles_index_id(email, index)
    try:
        role = es().get(index=ROLES_INDEX, id=id, source=["role"])["_source"]
        return Role(role)
    except Exception:
        return Role.NONE
