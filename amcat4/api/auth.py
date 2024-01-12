"""Helper methods for authentication."""
import functools
import logging
from datetime import datetime

import requests
from authlib.common.errors import AuthlibBaseError
from authlib.jose import jwt
from fastapi import HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from starlette.status import HTTP_401_UNAUTHORIZED

from amcat4.models import FieldSpec
from amcat4.config import get_settings, AuthOptions
from amcat4.index import Role, get_role, get_global_role, get_fields

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


class InvalidToken(ValueError):
    pass


@functools.lru_cache()
def get_middlecat_config(middlecat_url) -> dict:
    r = requests.get(f"{middlecat_url}/api/configuration")
    r.raise_for_status()
    return r.json()


def verify_token(token: str) -> dict:
    """
    Verifies the given token and returns the payload

    raises a InvalidToken exception if the token could not be validated
    """
    payload = decode_middlecat_token(token)
    if missing := {"email", "resource", "exp"} - set(payload.keys()):
        raise InvalidToken(f"Invalid token, missing keys {missing}")
    now = int(datetime.now().timestamp())
    if payload["exp"] < now:
        raise InvalidToken("Token expired")
    if payload["resource"] != get_settings().host:
        raise InvalidToken(f"Wrong host! {payload['resource']} != {get_settings().host}")
    return payload


def decode_middlecat_token(token: str) -> dict:
    """
    Verifies a midddlecat token
    """
    url = get_settings().middlecat_url
    if not url:
        raise InvalidToken("No middlecat defined, cannot decrypt middlecat token")
    public_key = get_middlecat_config(url)["public_key"]
    try:
        return jwt.decode(token, public_key)
    except AuthlibBaseError as e:
        raise InvalidToken(e)


def check_global_role(user: str, required_role: Role, raise_error=True):
    """
    Check if the given user has at least the required role
    :param user: The email address of the authenticated user
    :param required_role: The minimum global role of the user
    :param raise_error: If true, raise an error when not authorized, otherwise return False
                        (will always raise an error if user is not authenticated)
    """
    if not user:
        raise HTTPException(status_code=401, detail="No authenticated user")
    try:
        global_role = get_global_role(user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error on retrieving user {user}: {e}")
    if global_role and global_role >= required_role:
        return global_role
    if raise_error:
        raise HTTPException(
            status_code=401,
            detail=f"User {user} does not have global " f"{required_role.name.title()} permissions on this instance",
        )
    else:
        return False


def check_role(user: str, required_role: Role, index: str, required_global_role: Role = Role.ADMIN):
    """Check if the given user have at least the given role (in the index, if given), raise Exception otherwise.

    :param user: The email address of the authenticated user
    :param required_role: The minimum role of the user on the given index
    :param index: The index to check the role on
    :param required_global_role: If the user has this global role (default: admin), also allow them access
    :return: the actual role of the user on this index
    """
    # First, check global role (also checks that user exists and deals with 'admin' special user)
    if check_global_role(user, required_global_role, raise_error=False):
        return get_role(index, user)
    # Global role check was false, so now check local role
    actual_role = get_role(index, user)
    if get_settings().auth == AuthOptions.no_auth:
        return actual_role
    elif actual_role and actual_role >= required_role:
        return actual_role
    else:
        raise HTTPException(
            status_code=401,
            detail=f"User {user} does not have " f"{required_role.name.title()} permissions on index {index}",
        )


def check_fields_access(index: str, user: str, fields: list[FieldSpec]) -> None:
    """Check if the given user is allowed to query the given fields and snippets on the given index.

    :param index: The index to check the role on
    :param user: The email address of the authenticated user
    :param fields: The fields to check
    :param snippets: The snippets to check
    :return: Nothing. Throws HTTPException if the user is not allowed to query the given fields and snippets.
    """

    role = get_role(index, user)
    if role is None:
        raise HTTPException(
            status_code=401,
            detail=f"User {user} does not have a role on index {index}",
        )
    if role >= Role.READER:
        return None
    if fields is None:
        return None

    # after this, we know the user is a metareader, so we need to check metareader_access
    index_fields = get_fields(index)
    for field in fields:
        if field.name not in index_fields:
            # might be better to raise an error here, but since we want to support querying multiple
            # indices at once, this allows the user to query fields that do not exist on all indices
            continue
        metareader = index_fields[field.name].metareader

        if metareader.access == "read":
            continue
        elif metareader.access == "snippet" and metareader.max_snippet is not None:
            if metareader.max_snippet is None:
                max_params_msg = ""
            else:
                max_params_msg = "Can only read snippet with max parameters:"
                f"\n- nomatch_chars = {metareader.max_snippet.nomatch_chars}"
                f"\n- max_matches = {metareader.max_snippet.max_matches}"
                f"\n- match_chars = {metareader.max_snippet.match_chars}"

            if field.snippet is None:
                # if snippet is not specified, the whole field is requested
                raise HTTPException(
                    status_code=401, detail=f"METAREADER cannot read {field} on index {index}. {max_params_msg}"
                )

            valid_nomatch_chars = field.snippet.nomatch_chars <= metareader.max_snippet.nomatch_chars
            valid_max_matches = field.snippet.max_matches <= metareader.max_snippet.max_matches
            valid_match_chars = field.snippet.match_chars <= metareader.max_snippet.match_chars
            valid = valid_nomatch_chars and valid_max_matches and valid_match_chars
            if not valid:
                raise HTTPException(
                    status_code=401,
                    detail=f"The requested snippet of {field.name} on index {index} is too long. {max_params_msg}",
                )
        else:
            raise HTTPException(
                status_code=401,
                detail=f"METAREADER cannot read {field} on index {index}",
            )


async def authenticated_user(token: str = Depends(oauth2_scheme)) -> str:
    """Dependency to verify and return a user based on a token."""
    auth = get_settings().auth
    if token is None:
        if auth == AuthOptions.no_auth:
            return "admin"
        elif auth == AuthOptions.allow_guests:
            return "guest"
        else:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="This instance has no guest access, please provide a valid bearer token",
            )
    try:
        user = verify_token(token)["email"]
    except Exception:
        logging.exception("Login failed")
        raise HTTPException(status_code=401, detail="Invalid token")
    if auth == AuthOptions.authorized_users_only:
        if get_global_role(user) is None:
            raise HTTPException(
                status_code=401,
                detail=f"The user {user} is not authorized to access this AmCAT instance",
            )
    return user


async def authenticated_writer(user: str = Depends(authenticated_user)):
    """Dependency to verify and return a global writer user based on a token."""
    if get_settings().auth != AuthOptions.no_auth:
        check_global_role(user, Role.WRITER)
    return user


async def authenticated_admin(user: str = Depends(authenticated_user)):
    """Dependency to verify and return a global writer user based on a token."""
    if get_settings().auth != AuthOptions.no_auth:
        check_global_role(user, Role.ADMIN)
    return user
