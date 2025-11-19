import aioboto3
from botocore.client import Config

from amcat4.config import get_settings


class S3SessionHolder:
    active: aioboto3.Session | None = None


S3_SESSION = S3SessionHolder()


def get_s3_session() -> aioboto3.Session:
    if S3_SESSION.active is None:
        S3_SESSION.active = aioboto3.Session()
    return S3_SESSION.active


def get_s3_client():
    settings = get_settings()

    if settings.s3_host is None:
        raise ValueError("s3_host not specified")
    if settings.s3_access_key is None or settings.s3_secret_key is None:
        raise ValueError("s3_access_key or s3_secret_key not specified")

    session = get_s3_session()
    if session is None:
        raise ValueError("S3 client session not initialized")

    return session.client(
        "s3",
        endpoint_url=settings.s3_host,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
    )


async def close_s3_session():
    ## TODO: check if this needs to be closed.
    ## (supposedly it has its own connection pool)
    if S3_SESSION.active is not None:
        pass


def s3_enabled() -> bool:
    settings = get_settings()
    return all([settings.s3_host, settings.s3_access_key, settings.s3_secret_key])
