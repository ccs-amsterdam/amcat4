from starlette.testclient import TestClient

from amcat4 import elastic
from amcat4.index import get_guest_role, Role, set_role, remove_role
from tests.tools import build_headers, post_json, get_json, check


def test_create_list_delete_index(client, index_name, user, writer, writer2, admin):
    """Test API endpoints to create/list/delete index"""
    # Anonymous or Unprivileged users cannot create indices
    check(client.post("/index/"), 401)
    check(client.post("/index/", headers=build_headers(user=user)), 401)

    # Authorized users should get 404 if index does not exist
    check(client.get(f"/index/{index_name}"), 401)
    check(client.get(f"/index/{index_name}", headers=build_headers(user=writer)), 404)

    # Writers can create indices
    post_json(client, "/index/", user=writer, json=dict(name=index_name))
    assert get_json(client, f"/index/{index_name}", user=writer) == {"index": index_name, "guest_role": "NONE"}

    # Users can GET their own index, global writer can GET all indices, others cannot GET non-public indices
    check(client.get(f"/index/{index_name}"), 401)
    check(client.get(f"/index/{index_name}", headers=build_headers(user=user)), 401)
    check(client.get(f"/index/{index_name}", headers=build_headers(user=writer)), 200)
    check(client.get(f"/index/{index_name}", headers=build_headers(user=writer2)), 200)

    # Users can only see indices that they have a role in or that have a guest role
    assert index_name not in {x['name'] for x in get_json(client, "/index/", user=user)}
    assert index_name in {x['name'] for x in get_json(client, "/index/", user=writer)}

    # (Only) index admin can change index guest role
    check(client.put(f"/index/{index_name}"), 401)
    check(client.put(f"/index/{index_name}", headers=build_headers(user=writer), json={'guest_role': 'METAREADER'}), 200)
    check(client.put(f"/index/{index_name}", headers=build_headers(user=writer2), json={'guest_role': 'READER'}), 401)
    check(client.put(f"/index/{index_name}", headers=build_headers(user=admin), json={'guest_role': 'READER'}), 200)
    assert get_guest_role(index_name).name == "READER"

    # Index should now be visible to non-authorized users
    assert index_name in {x['name'] for x in get_json(client, "/index/", user=writer)}
    check(client.get(f"/index/{index_name}", headers=build_headers(user=user)), 200)


def test_fields_upload(client: TestClient, user: str, index: str):
    """test_fields: Can we upload docs and retrieve field mappings and values?"""
    body = {"documents": [{"_id": str(i), "title": f"doc {i}", "text": "t", "date": "2021-01-01", "x": x}
                          for i, x in enumerate(["a", "a", "b"])],
            "columns": {"x": "keyword"}}

    # You need METAREADER permissions to read fields, and WRITER to upload docs
    check(client.get(f"/index/{index}/fields"), 401)
    check(client.post(f"/index/{index}/documents", headers=build_headers(user), json=body), 401)

    fields = get_json(client, f"/index/{index}/fields", user=user)
    assert set(fields.keys()) == {"title", "date", "text", "url"}
    assert fields['date']['type'] == "date"

    set_role(index, user, Role.WRITER)
    post_json(client, f"/index/{index}/documents", user=user, json=body)
    get_json(client, f"/index/{index}/refresh", expected=204)
    doc = get_json(client, f"/index/{index}/documents/0", user=user)
    assert set(doc.keys()) == {'date', 'text', 'title', 'x'}
    assert doc["title"] == "doc 0"

    # field selection
    assert set(get_json(client, f"/index/{index}/documents/0",
                        user=user, params={'fields': 'title'}).keys()) == {'title'}
    assert get_json(client, f"/index/{index}/fields", user=user)["x"]["type"] == "keyword"
    elastic.es().indices.refresh()
    assert set(get_json(client, f"/index/{index}/fields/x/values", user=user)) == {"a", "b"}


def test_set_get_delete_roles(client: TestClient, admin: str, writer: str, user: str, index: str):
    body = {"email": user, "role": "READER"}
    # Anon, unauthorized; READER can't add users
    check(client.post(f"/index/{index}/users", json=body), 401)
    check(client.post(f"/index/{index}/users", json=body, headers=build_headers(writer)), 401)
    set_role(index, writer, Role.READER)
    check(client.post(f"/index/{index}/users", json=body, headers=build_headers(writer)), 401)
    # WRITER can't add or change ADMIN
    set_role(index, writer, Role.WRITER)
    check(client.post(f"/index/{index}/users", json={"email": user, "role": "ADMIN"},
                      headers=build_headers(writer)), 401)
    remove_role(index, writer)

    # Global admin can add anyone
    post_json(client, f"/index/{index}/users", json={"email": writer, "role": "WRITER"}, user=admin)
    assert get_json(client, f"/index/{index}/users", user=writer) == [{"email": writer, "role": "WRITER"}]
    # Writer can now add a new user
    post_json(client, f"/index/{index}/users", json=body, user=writer)
    users = {u['email']: u['role'] for u in get_json(client, f"/index/{index}/users", user=writer)}
    assert users == {writer: "WRITER", user: "READER"}

    # Anon, unauthorized or READER can't change users
    writer_url = f"/index/{index}/users/{writer}"
    user_url = f"/index/{index}/users/{user}"
    check(client.put(writer_url, json={"role": "READER"}), 401)
    check(client.put(writer_url, json={"role": "READER"}, headers=build_headers(user)), 401)
    # Writer can change to writer
    check(client.put(user_url, json={"role": "WRITER"}, headers=build_headers(writer)), 200)
    users = {u['email']: u['role'] for u in get_json(client, f"/index/{index}/users", user=writer)}
    assert users == {writer: "WRITER", user: "WRITER"}
    # Writer can't change to admin
    check(client.put(writer_url, json={"role": "ADMIN"}, headers=build_headers(user)), 401)
    # Writer can't change from admin
    set_role(index, writer, Role.ADMIN)
    check(client.put(writer_url, json={"role": "WRITER"}, headers=build_headers(user)), 401)

    # Anon, unauthorized or READER can't delete users
    check(client.delete(writer_url), 401)
    check(client.delete(writer_url, headers=build_headers(user)), 401)
    # Writer can't delete admin
    set_role(index, user, Role.WRITER)
    check(client.delete(writer_url, headers=build_headers(user)), 401)
    # Admin can delete writer
    check(client.delete(user_url, headers=build_headers(writer)), 200)
    # Global admin can delete anyone
    check(client.delete(writer_url, headers=build_headers(admin)), 200)
    assert get_json(client, f"/index/{index}/users", user=admin) == []
