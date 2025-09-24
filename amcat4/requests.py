from datetime import datetime
from typing import Annotated, Literal, Optional, Union

import elasticsearch
import elasticsearch.helpers
from pydantic import BaseModel, Field

from amcat4.api.index import RoleType
from amcat4.config import get_settings
from amcat4.elastic import es
from amcat4.index import GLOBAL_ROLES, GuestRole, Role, _roles_from_elastic, get_index_user_role


class RoleRequest(BaseModel):
    request_type: Literal["role"]
    index: str | None
    email: str
    role: RoleType | Literal["NONE"]


class CreateProjectRequest(BaseModel):
    request_type: Literal["create_project"]
    index: str
    email: str


Request = Annotated[Union[RoleRequest, CreateProjectRequest], Field(discriminator="request_type")]


def get_role_requests(user: str | None = None):
    """
    List all role requests, optionally filtered by index and user
    :param user: If a user is given, only return requests that this
                 user has authority over (i.e. if the user is admin
                 or has admin role on the index)
    """
    system_index = get_settings().system_index

    query_filter = create_index_filter_query(
        exists=["role_requests"]
        # Don't use role filter until we fixed the system index on amcat4.labs.vu.nl
        # user=user if user else None,
        # min_role=Role.ADMIN if user else None
    )

    query = {"_source": {"includes": ["role_requests", "roles", "guest_role"]}, "query": query_filter}

    requests = []
    for ix in elasticsearch.helpers.scan(es(), query=query, index=system_index):
        if user:
            roles = _roles_from_elastic(ix["_source"].get("roles", []))
            guest_role = GuestRole[ix["_source"].get("guest_role", "NONE")]
            user_role = get_index_user_role(guest_role, roles, user)
            if user_role != Role.ADMIN and get_settings().auth != "no_auth":
                continue

        for request in ix["_source"].get("role_requests", []):
            request["index"] = ix["_id"]
            requests.append(request)
            if len(requests) > 2000:
                break

    # I don't think it's possible to sort role_requests across documents, so we do it in python.
    # If requests ever gets too large (now 2000) this only affects the order.
    requests.sort(key=lambda x: datetime.fromisoformat(x.get("timestamp")))

    return requests


def create_index_filter_query(
    ids: Optional[list[str]] = None,
    user: Optional[str] = None,
    min_role: Optional[Role] = None,
    exists: Optional[list[str]] = None,
):
    """
    Create an elasticsearch query filter for the given includes and excludes
    :param ids: A list of index names to include, or None for all indices
    :param includes: A list of index names to include, or None for all indices
    :param user: If given, only include indices where this user has at least min_role
    :param min_role: The minimum role the user should have on the index, if user
    :return: An elasticsearch query dict
    """
    filters = []
    if ids:
        filters.append({"ids": {"values": ids}})
    if exists:
        for f in exists:
            filters.append({"exists": {"field": f}})

    if min_role and get_settings().auth != "no_auth":
        valid_roles = []
        for role in ["ADMIN", "WRITER", "READER", "METAREADER"]:
            valid_roles.append(role)
            if min_role.name == role:
                break

        # make filter for guest role
        role_filter = {
            "nested": {"path": "roles", "query": {"bool": {"should": [{"terms": {"guest_role.keyword": valid_roles}}]}}}
        }

        # if user is given, add user role to filter
        if user is not None:
            # include domain wildcard
            wildcard_user = f"*@{user.split('@')[-1]}"
            email_matches = [user, wildcard_user]

            role_filter["nested"]["query"]["bool"]["should"].append(
                {
                    "bool": {
                        "must": [
                            {"terms": {"roles.email.keyword": email_matches}},
                            {"terms": {"roles.role.keyword": valid_roles}},
                        ]
                    }
                }
            )

        filters.append(role_filter)

    if filters:
        return {"bool": {"filter": filters}}
    else:
        return {"match_all": {}}


def set_role_request(index: str | None, email: str, role: Optional[Role]):
    """
    Create or update a role request for this user on the given index)
    If role is None, remove the role request
    """
    # TODO: It would probably be better to do this with a query script on elastic
    system_index = get_settings().system_index
    if not index:
        index = GLOBAL_ROLES
    try:
        d = es().get(index=system_index, id=index, source_includes="role_requests")
    except elasticsearch.NotFoundError:
        raise ValueError(f"Index {index} is not registered")

    requests = {request["email"]: request for request in d["_source"].get("role_requests", [])}

    if role:
        requests[email] = dict(email=email, role=role.name, timestamp=datetime.now().isoformat())
    else:
        requests.pop(email, None)

    es().update(
        index=system_index,
        id=index,
        doc=dict(role_requests=list(requests.values())),
    )
