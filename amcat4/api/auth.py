"""Helper methods for authentication."""
import logging
from datetime import datetime
from typing import Optional

from authlib.jose import JsonWebSignature
from authlib.jose.errors import DecodeError
from fastapi import HTTPException
from fastapi.params import Depends
from fastapi.security import OAuth2PasswordBearer
import json

from amcat4.config import get_settings
from amcat4.index import Role, get_role

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def create_token(email: str, days_valid: int = 7) -> bytes:
    """
    Create a new token for this user
    :param email: the email or username to create a token for
    :param days_valid: the number of days from now that the token should be valid
    """
    header: dict = {'alg': 'HS256'}
    if days_valid:
        now = int(datetime.now().timestamp())
        exp = now + days_valid * 24 * 60 * 60
        header.update({'crit': ['exp'], 'exp': exp})
    payload = {'email': email}
    s = JsonWebSignature().serialize_compact(header, json.dumps(payload).encode("utf-8"), get_settings().salt)
    return s


def verify_admin(password: str) -> bool:
    """
    Check that this user exists and can be authenticated with the given password, returning a User object
    :param email: Email address identifying the user
    :param password: Password to check
    """
    admin_password = get_settings().admin_password
    if not admin_password:
        logging.info("Attempted admin login without AMCAT4_ADMIN_PASSWORD set")
        return False

    print(password, admin_password)
    if password == admin_password:
        logging.info("Successful admin login")
        return True
    else:
        logging.warning(f"Incorrect password for admin")
        return False


def verify_token(token: str) -> Optional[str]:
    """Verify the given token and return the email"""
    jws = JsonWebSignature()
    try:
        result = jws.deserialize_compact(token, get_settings().salt)
    except DecodeError:
        logging.exception("Token verification failed")
        return None
    if "exp" in result["header"]:
        now = int(datetime.now().timestamp())
        if result["header"]["exp"] < now:
            logging.error("Token expired")
            return None
    payload = json.loads(result['payload'].decode("utf-8"))
    return payload['email']


def check_role(user: str, required_role: Role, index: str = None):
    """Check if the given user have at least the given role (in the index, if given), raise Exception otherwise."""
    if not user:
        raise HTTPException(status_code=401, detail="No authenticated user")
    if user == "admin":
        return True
    actual_role = get_role(user, index) if index else get_role(user)
    if actual_role and actual_role >= required_role:
        return True
    else:
        error = f"User {user} does not have role {required_role}"
        if index:
            error += f" on index {index}"
        raise HTTPException(status_code=401, detail=error)


async def authenticated_user(token: str = Depends(oauth2_scheme)):
    """Dependency to verify and return a user based on a token."""
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid token")
    print(f"!! {user!r}")
    return user


async def authenticated_writer(user: str = Depends(authenticated_user)):
    """Dependency to verify and return a global writer user based on a token."""
    check_role(user, Role.WRITER)
    return user


async def authenticated_admin(user: str = Depends(authenticated_user)):
    """Dependency to verify and return a global writer user based on a token."""
    check_role(user, Role.ADMIN)
    return user
