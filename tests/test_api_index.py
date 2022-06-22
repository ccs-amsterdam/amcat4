from amcat4 import elastic
from amcat4.auth import Role
from amcat4.index import Index
from tests.tools import build_headers, post_json, get_json, check


def test_create_list_delete_index(client, index_name, user, writer, admin):
    """Test API endpoints to create/list/delete index"""
    # Anonymous or Unprivileged users cannot create indices
    check(client.post("/index/"), 401)
    check(client.post("/index/", headers=build_headers(user=user)), 401)

    # Writers can create indices
    r = post_json(client, "/index/", user=writer, json=dict(name=index_name, guest_role='METAREADER'))
    assert set(r.keys()) == {"guest_role", "name"}

    # All logged in users can list indices
    assert index_name in {ix['name'] for ix in get_json(client, "/index/", user=user)}

    # (Only) index owner/admin and global admin can change index guest role to admin
    check(client.put(f"/index/{index_name}"), 401)
    check(client.put(f"/index/{index_name}", headers=build_headers(user=user), json={'guest_role': 'METAREADER'}), 401)
    check(client.put(f"/index/{index_name}", headers=build_headers(user=writer), json={'guest_role': 'ADMIN'}), 200)
    assert Index.get(Index.name == index_name).guest_role == Role.ADMIN
    check(client.put(f"/index/{index_name}", headers=build_headers(user=admin), json={'guest_role': 'WRITER'}), 200)
    # Guest role is writer, so anyone can change it, but not to admin
    check(client.put(f"/index/{index_name}", headers=build_headers(user=user), json={'guest_role': 'ADMIN'}), 401)
    check(client.put(f"/index/{index_name}", headers=build_headers(user=user), json={'guest_role': 'METAREADER'}), 200)


def test_fields_upload(client, user, index):
    """test_fields: Can we upload docs and retrieve field mappings and values?"""
    body = {"documents": [{"title": f"doc {i}", "text": "t", "date": "2021-01-01", "x": x}
                          for i, x in enumerate(["a", "a", "b"])],
            "columns": {"x": "keyword"}}

    # You need METAREADER permissions to read fields, and WRITER to upload docs
    check(client.get(f"/index/{index.name}/fields"), 401)
    check(client.post(f"/index/{index.name}/documents", headers=build_headers(user), json=body), 401)

    fields = get_json(client, f"/index/{index.name}/fields", user=user)
    assert set(fields.keys()) == {"title", "date", "text", "url"}
    assert fields['date']['type'] == "date"

    index.set_role(user, Role.WRITER)
    ids = post_json(client, f"/index/{index.name}/documents", user=user, json=body)
    assert len(ids) == 3
    doc = get_json(client, f"/index/{index.name}/documents/{ids[0]}", user=user)
    assert set(doc.keys()) == {'date', 'text', 'title', 'x'}
    assert doc["title"] == "doc 0"

    # field selection
    assert set(get_json(client, f"/index/{index.name}/documents/{ids[0]}",
                        user=user, params={'fields': 'title'}).keys()) == {'title'}
    print(get_json(client, f"/index/{index.name}/fields", user=user))
    assert get_json(client, f"/index/{index.name}/fields", user=user)["x"]["type"] == "keyword"
    elastic.es().indices.refresh()
    assert set(get_json(client, f"/index/{index.name}/fields/x/values", user=user)) == {"a", "b"}


def test_set_get_delete_roles(client, admin, writer, user, index: Index):
    body = {"email": user.email, "role": "READER"}
    # Anon, unauthorized; READER can't add users
    check(client.post(f"/index/{index.name}/users", json=body), 401)
    check(client.post(f"/index/{index.name}/users", json=body, headers=build_headers(writer)), 401)
    index.set_role(writer, Role.READER)
    check(client.post(f"/index/{index.name}/users", json=body, headers=build_headers(writer)), 401)
    # WRITER can't add or change ADMIN
    index.set_role(writer, Role.WRITER)
    check(client.post(f"/index/{index.name}/users", json={"email": user.email, "role": "ADMIN"},
                      headers=build_headers(writer)), 401)
    index.set_role(writer, None)

    # Admin can add anyone
    post_json(client, f"/index/{index.name}/users", json={"email": writer.email, "role": "WRITER"}, user=admin)
    assert get_json(client, f"/index/{index.name}/users", user=writer) == [{"email": writer.email, "role": "WRITER"}]
    # Writer can now add a new user
    post_json(client, f"/index/{index.name}/users", json=body, user=writer)
    users = {u['email']: u['role'] for u in get_json(client, f"/index/{index.name}/users", user=writer)}
    assert users == {writer.email: "WRITER", user.email: "READER"}

    # Anon, unauthorized or READER can't change users
    writer_url = f"/index/{index.name}/users/{writer.email}"
    user_url = f"/index/{index.name}/users/{user.email}"
    check(client.put(writer_url, json={"role": "READER"}), 401)
    check(client.put(writer_url, json={"role": "READER"}, headers=build_headers(user)), 401)
    # Writer can change to writer
    check(client.put(user_url, json={"role": "WRITER"}, headers=build_headers(writer)), 200)
    users = {u['email']: u['role'] for u in get_json(client, f"/index/{index.name}/users", user=writer)}
    assert users == {writer.email: "WRITER", user.email: "WRITER"}
    # Writer can't change to admin
    check(client.put(writer_url, json={"role": "ADMIN"}, headers=build_headers(user)), 401)
    # Writer can't change from admin
    index.set_role(writer, Role.ADMIN)
    check(client.put(writer_url, json={"role": "WRITER"}, headers=build_headers(user)), 401)

    # Anon, unauthorized or READER can't delete users
    check(client.delete(writer_url), 401)
    check(client.delete(writer_url, headers=build_headers(user)), 401)
    # Writer can't delete admin
    index.set_role(user, Role.WRITER)
    check(client.delete(writer_url, headers=build_headers(user)), 401)
    # Admin can delete writer
    check(client.delete(user_url, headers=build_headers(writer)), 200)
    # Global admin can delete anyone
    check(client.delete(writer_url, headers=build_headers(admin)), 200)
    assert get_json(client, f"/index/{index.name}/users", user=admin) == []
