"""API Endpoints for MiddleCat Authentication."""
import requests, logging, os, json
from datetime import datetime
from urllib.parse import urlparse
from http import HTTPStatus
from typing import Literal, Optional, Mapping, List

from fastapi import APIRouter, Query, HTTPException, status, Response, Request
from fastapi.params import Body
from fastapi.responses import RedirectResponse

from dotenv import load_dotenv

import bcrypt
from authlib.jose import JsonWebToken, JsonWebSignature
from authlib.jose.errors import DecodeError

load_dotenv()
SECRET_KEY = os.getenv('SECRET_KEY')
MIDDLECAT_HOST = os.getenv('MIDDLECAT_HOST') 

app_middlecat = APIRouter(
    prefix="/middlecat",
    tags=["middlecat"])

# run for test:
# This should normally be called from the client, with the client parameter being the current client route.
# In the current form it redirects to this connect endpoint, which then shows if auth succeeded
# http://localhost:5000/middlecat/connect?client=http://localhost:5000/middlecat/connect

@app_middlecat.get('/connect', status_code=200)
def connect(req: Request, 
            client: str = Query(None, description="Client callback URL")):
    """
    If the user has a valid token, this endpoint returns the payload with user info.

    If not, it runs the following auth flow:
    - direct user to middlecat with the server and client urls
    - middlecat creates a JWT for giving the user accesss to this specific server
    - middlecat redirects user to this server at the /middlecat/token endpoint
    - the middlecat token is validated using the middlecat public key (that is available on the middlecat API)
    - if the user is authenticated, the server creates its own JWT. (The middlecat token should only be short term
      because it gets passed via a get request)
    - the server's own token gets set as a httponly cookie

    The key advantages of this approach are:
    - MiddleCat does not have to be on the same domain. So easy to create multiple instances.
    - The redirect flow is fast, and only needs to be performed once, or when the amcat token expires.
    - Not having to rely on cross-domain cookies should also make it much easier to use this for CLI (AmCAT, Python) auth 
    
    Currently this is not yet integrated in the rest of the API endpoints (these still use the bearer token that is send with each request).
    If we think this is a good appraoch, we can implement it as follows:
    - replace the authenticated_user and authenticated_writer functions with a single function for verifying the auth cookie 
    - Get rid of the auth.py code 
    - Setup authorization that only links email addresses to roles. If we can do this in elastic, we can drop Peewee
    """

    token = req.cookies.get('access-token')
    user = verify_token(token)
    if user is not None:
        # if there is a valid token, return the payload with user info
        return user
    else:
        # if not, run the following auth flow:
        # - direct user to middlecat with the server and client urls
        # - middlecat creates a JWT for giving the user accesss to this specific server
        # - middlecat redirects user to this server at the /middlecat/token endpoint
        # - the middlecat token is validated using the middlecat public key (that is available on the middlecat API)
        # - if the user is authenticated, the server creates its own JWT. (The middlecat token should only be short term
        #   because it gets passed via a get request)
        # - the server's own token gets set as a httponly cookie
        if client is None:
            raise HTTPException(status_code=400, detail='client url needs to be provided to login with MiddleCat')
        server = server_url(req)
        middlecat_url = f"{MIDDLECAT_HOST}/login?server={server}&client={client}"
        return RedirectResponse(middlecat_url, status_code=307)


@app_middlecat.get("/token", status_code=200)
def token(req: Request,
          token: str = Query(None, description='MiddleCat Token'),
          client: str = Query(None, description='Client callback url')):

    # dynamically fetch public_key (we can also include public key, but this way
    # amcat servers only need to specify middlecat urls, and middlecat can rotate keys)
    public_key = requests.get(f"{MIDDLECAT_HOST}/api/public_key").text
    public_key = public_key.replace('\\n','\n').strip().strip('"')
    
    try:
        jwt = JsonWebToken('RS256')
        claims = jwt.decode(token, public_key)
        ## !! still have to add claims in middlecat to make this a token that expires fast (like 1 minute))
        claims.validate()    
    except DecodeError:
        logging.exception("Token invalid: cannot validate JWT")
        return None
    
    # Also confirm that the token is for this server. The server to which the token is redirected 
    # is included in the JWT so that a server cannot abuse a key to make requests from other servers
    server = server_url(req)
    if server != claims['server']:
        raise HTTPException(status_code=404, detail="Token invalid: server does not match")

    amcat_token = create_token(claims, 7)
    

    response = RedirectResponse(client, status_code=303)
    response.set_cookie(key='access-token', value=amcat_token, httponly=True)
    return response


def server_url(req: Request):
    server = urlparse(str(req.url))
    server = f"{server.scheme}://{server.netloc}"
    return server

def create_token(claims, days_valid: int = 7) -> str:
    """
    Create a new token for this user
    :param days_valid: the number of days from now that the token should be valid
    """
    header: dict = {'alg': 'HS256'}
    if days_valid:
        exp = now() + days_valid * 24*60*60
        header.update({'crit': ['exp'], 'exp': exp})
    payload = {'email': claims['email'], 'name': claims['name'], 'image':claims['image']}
   
    s = JsonWebSignature().serialize_compact(header, json.dumps(payload).encode("utf-8"), SECRET_KEY)
    return s.decode('utf-8')

def verify_token(token: str):
    """
    Check the token and return the authenticated user email
    :param token: The token to verify
    :return: a User object if user could be authenticated, None otherwise
    """
    if token is None:
        logging.exception("User does not yet have a token")
        return None

    jws = JsonWebSignature()
    try:
        result = jws.deserialize_compact(token, SECRET_KEY)
    except:
        logging.exception("Token verification failed")
        #raise HTTPException(status_code=400, detail=token)
        return None
    if "exp" in result["header"]:
        if result["header"]["exp"] < now():
            logging.error("Token expired")
            return None
    payload = json.loads(result['payload'].decode("utf-8"))
    return payload


def now() -> int:
    """Current time in seconds since epoch"""
    return int(datetime.now().timestamp())

