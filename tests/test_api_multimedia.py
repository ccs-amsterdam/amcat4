import httpx
import pytest
from httpx import AsyncClient

from amcat4.models import Roles
from amcat4.objectstorage.s3client import s3_enabled
from amcat4.projects.documents import create_or_update_documents
from amcat4.systemdata.roles import create_project_role
from tests.conftest import not_localhost
from tests.tools import build_headers, check

if not s3_enabled():
    pytest.skip("S3 not configured, skipping multimedia tests", allow_module_level=True)


async def _get_names(client: AsyncClient, index, user, **kargs):
    res = await client.get(f"index/{index}/multimedia", params=kargs, headers=build_headers(user))
    res.raise_for_status()
    data = res.json()
    return {f"{obj['field']}/{obj['filepath']}" for obj in data["objects"]}


@pytest.mark.anyio
async def test_authorisation(client, index, user, reader):
    await create_or_update_documents(
        index, documents=[{"_id": "doc1", "image_field": "image.png"}], fields={"image_field": "image"}
    )

    await check(await client.get(f"index/{index}/multimedia"), 403)
    await check(await client.get(f"index/{index}/multimedia/get/image_field/image.png"), 403)
    await check(await client.post(f"index/{index}/multimedia/upload/image_field", json=[]), 403)

    await create_project_role(user, index, Roles.METAREADER)
    await create_project_role(reader, index, Roles.READER)
    await check(await client.get(f"index/{index}/multimedia", headers=build_headers(user)), 403)
    await check(
        await client.get(
            f"index/{index}/multimedia/get/image_field/image.png", params=dict(key=""), headers=build_headers(user)
        ),
        403,
    )
    await check(await client.post(f"index/{index}/multimedia/upload/image_field", json=[], headers=build_headers(reader)), 403)


@pytest.mark.anyio
@pytest.mark.httpx_mock(should_mock=not_localhost)
async def test_presigned(client, index, user):
    await create_or_update_documents(
        index, documents=[{"_id": "doc1", "image_field": "image.png"}], fields={"image_field": "image"}
    )
    await create_project_role(user, index, Roles.WRITER)

    assert await _get_names(client, index, user) == set()

    content = b"my beautiful image bytes"
    size = len(content)

    body = [{"filepath": "image.png", "size": size}]
    res = (await client.post(f"index/{index}/multimedia/upload/image_field", json=body, headers=build_headers(user))).json()
    assert set(res.keys()) == {"presigned_posts", "skipped", "max_total_size", "new_total_size"}
    assert res["new_total_size"] == len(content)

    post = res["presigned_posts"][0]
    assert set(post.keys()) == {"filepath", "url", "form_data"}

    ## The object should now already be registered in elastic, but with the last_synced field set to None.
    ## (This is important because now elastic knows about the object and size)
    res = await client.get(f"index/{index}/multimedia", headers=build_headers(user))
    data = res.json()
    assert data["objects"][0]["filepath"] == "image.png"
    assert data["objects"][0]["last_synced"] is None

    ## And if we try to get the object, we get a 404 (missing)
    await check(await client.get(f"index/{index}/multimedia/image_field/image.png", headers=build_headers(user)), 404)

    ## Now we can upload the file
    file = {"file": ("image.png", content)}

    ## TODO: somehow when the upload is forbidden, S3 returns a 307 redirect instead of an error.
    ## Figure out why and how to make it act less stupid.

    async with httpx.AsyncClient() as uploader:
        ## errors if key doesn't match key prefix
        assert (
            await uploader.post(
                url=post["url"],
                data={**post["form_data"], "key": "forbidden/file.png", "Content-Type": "image/png"},
                files=file,
            )
        ).status_code == 307
        ## errors if content type doesn't match type prefix
        assert (
            await uploader.post(
                url=post["url"],
                data={**post["form_data"], "Content-Type": "application/pdf"},
                files=file,
            )
        ).status_code == 307

        ## works with correct (unchanged) key and content type
        res = await uploader.post(url=post["url"], data={**post["form_data"]}, files=file)
        assert res.status_code == 204

    ## Now we should be able to get the file via the gatekeeper endpoint.
    ## This redirects to a presigned S3 GET url.
    ## We need to manually handle the redirect because of the testing client
    ## (we need to turn of mime checking, because the content we provided was not a proper image/png)
    res = await client.get(
        f"index/{index}/multimedia/get/image_field/image.png",
        params=dict(skip_mime_check=True),
        headers=build_headers(user),
    )
    assert res.status_code == 303
    presigned_get = res.headers["location"]
    async with httpx.AsyncClient() as downloader:
        res = await downloader.get(presigned_get)
    assert res.content == b"my beautiful image bytes"

    ## If we do not disable mime checking, we should get an error. This is the default because its safer.
    await check(
        await client.get(
            f"index/{index}/multimedia/get/image_field/image.png",
            headers=build_headers(user),
        ),
        400,
        msg="does not match its real content type",
    )

    ## At this point the file is still not 'synced' in the multimedia register. Syncing requires
    ## a manual refresh call. The purpose of syncing is purely for maintainance, and should ideally
    ## never be necessary. But if somehow s3 files go missing, they need to be removed from the
    ## register, and if files go missing from the register they need to be added.
    res = await client.get(f"index/{index}/multimedia", headers=build_headers(user))
    assert res.json()["objects"][0]["last_synced"] is None

    await check(await client.get(f"index/{index}/multimedia/refresh", headers=build_headers(user)), 200)

    res = await client.get(f"index/{index}/multimedia", headers=build_headers(user))
    assert res.json()["objects"][0]["last_synced"] is not None

    ## Delete the multimedia object
    delete = ["image.png"]
    res = await client.post(f"index/{index}/multimedia/image_field", json=delete, headers=build_headers(user))
    assert await _get_names(client, index, user) == set()


@pytest.mark.anyio
@pytest.mark.httpx_mock(should_mock=not_localhost)
async def test_list_pagination(client, index, reader, user):
    await create_project_role(user, index, Roles.WRITER)

    ## We'll add 15 documents with multimedia fields
    content = b"my beautiful image bytes"
    size = len(content)

    documents = [{"_id": f"doc_{i}", "image_field": f"image_{i}.png"} for i in range(15)]
    await create_or_update_documents(index, documents=documents, fields={"image_field": "image"})

    upload = (
        await client.post(
            f"index/{index}/multimedia/upload/image_field",
            json=[{"filepath": d["image_field"], "size": size} for d in documents],
            headers=build_headers(user),
        )
    ).json()

    assert upload["new_total_size"] == size * len(documents)

    ## Upload all files
    async with httpx.AsyncClient() as uploader:
        for u in upload["presigned_posts"]:
            file = {"file": (u["filepath"], content)}
            await uploader.post(url=u["url"], data={**u["form_data"]}, files=file)

    await create_project_role(reader, index, Roles.READER)

    ## TODO:
    # SeaweedFS kind of sucks. It doesn't delete directories, and if a directory already exists,
    # somehow it 'sometimes' doesn't show up in the listing.
    # might have something to do with allowemptyfolder (see docker compose)

    res = await client.get(f"index/{index}/multimedia", params=dict(page_size=6), headers=build_headers(reader))
    data = res.json()
    assert len(data["objects"]) == 6
    assert data["scroll_id"] is not None

    # Get next page
    res = await client.get(
        f"index/{index}/multimedia", headers=build_headers(reader), params=dict(scroll_id=data["scroll_id"])
    )
    data = res.json()
    assert len(data["objects"]) == 6
    assert data["scroll_id"] is not None

    # last page
    res = await client.get(
        f"index/{index}/multimedia", headers=build_headers(reader), params=dict(scroll_id=data["scroll_id"])
    )
    data = res.json()
    assert len(data["objects"]) == 3
    assert data["scroll_id"] is not None  ## no more pages, but scroll_id is still set

    res = await client.get(
        f"index/{index}/multimedia", headers=build_headers(reader), params=dict(scroll_id=data["scroll_id"])
    )
    data = res.json()
    assert len(data["objects"]) == 0
    assert data["scroll_id"] is None
