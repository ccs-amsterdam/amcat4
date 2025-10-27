from functools import wraps
import hashlib
import json
import logging
from typing import Any, TypeVar, Callable
from fastapi import Request, Response

# Not implemented yet. Just thinking aloud here and learning about caching strategies.

F = TypeVar("F", bound=Callable)
ResponseBody = TypeVar("ResponseBody")


def static_browser_cache(func: Callable) -> Callable:
    """
    Decorator to set a highly aggressive, immutable Cache-Control header
    on the response for static or immutable content. This indicates to browsers
    and intermediate caches that the content can be cached for a long time (1 year)
    and will not change, allowing for optimal caching behavior.

    Main use case for AmCAT would be for static assets like project thumbnails.
    This should then be an endpoint where each static asset has a unique URL
    (so change the id when updating the asset).
    """
    max_age_seconds = 60 * 60 * 24 * 365
    cache_header = f"public, max-age={max_age_seconds}, immutable"

    @wraps(func)
    async def wrapper(*args, response: Response, **kwargs) -> Any:
        result = await func(*args, response=response, **kwargs)
        response.headers["Cache-Control"] = cache_header
        return result

    return wrapper


def hashed_browser_cache(func: Callable) -> Callable:
    """
    Decorator to add ETag-based caching to FastAPI endpoints.
    The ETag is based on a hash of the response content. If the client sends
    an If-None-Match header with a matching ETag, a 304 Not Modified response is returned.
    This is useful for endpoints that return large responses that change infrequently.
    """

    @wraps(func)
    async def wrapper(*args, request: Request, response: Response, **kwargs) -> Any:
        result = await func(*args, request=request, response=response, **kwargs)
        return response_with_etag(request, response, result)

    return wrapper


def response_with_etag(request: Request, response: Response, data: ResponseBody) -> ResponseBody | Response:
    try:
        content_str = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    except TypeError as e:
        # Handle cases where data isn't easily JSON serializable
        logging.warning(f"Warning: Data could not be serialized for ETag hashing: {e}")
        return data

    hash = hashlib.sha1(content_str).hexdigest()
    etag = f'"{hash}"'

    # Check if client has a (previous) matching ETag for this endpoint that matches the current content
    if_none_match = request.headers.get("if-none-match")
    if if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})

    response.headers["ETag"] = etag

    return data
