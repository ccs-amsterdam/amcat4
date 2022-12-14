"""Helper methods for authentication."""

from fastapi import HTTPException
from fastapi.params import Depends
from fastapi.security import OAuth2PasswordBearer


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def check_role(u, role, ix: str = None):
    """Check if the given user have at least the given role (in the index, if given), raise Exception otherwise."""
    if not u:
        raise HTTPException(status_code=401, detail="No authenticated user")
    if ix:
        if not ix.has_role(u, role):
            raise HTTPException(status_code=401, detail=f"User {u.email} does not have role {role} on index {ix}")
    else:
        if not u.has_role(role):
            raise HTTPException(status_code=401, detail=f"User {u.email} does not have role {role}")


async def authenticated_user(token: str = Depends(oauth2_scheme)):
    """Dependency to verify and return a user based on a token."""
    user = auth.verify_token(token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid token")
    return user


async def authenticated_writer(user = Depends(authenticated_user)):
    """Dependency to verify and return a global writer user based on a token."""
    if not user.has_role(Role.WRITER):
        raise HTTPException(status_code=401, detail=f"User {user} does not have WRITER access")
    return user
