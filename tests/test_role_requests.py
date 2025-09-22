from amcat4.index import Role, get_role_requests, refresh_system_index, set_role_request


def test_role_requests(index):
    assert get_role_requests(index) == []
    set_role_request(index, "vanatteveldt@gmail.com", Role.ADMIN)
    refresh_system_index()
    requests = {r["email"]: r for r in get_role_requests(index)}
    assert len(requests) == 1
    result = requests["vanatteveldt@gmail.com"]
    assert result["role"] == "ADMIN"

    # Does re-filing the request update the timestamp
    set_role_request(index, "vanatteveldt@gmail.com", Role.ADMIN)
    refresh_system_index()
    requests = {r["email"]: r for r in get_role_requests(index)}
    assert len(requests) == 1
    assert requests["vanatteveldt@gmail.com"]["role"] == "ADMIN"
    assert requests["vanatteveldt@gmail.com"]["timestamp"] > result["timestamp"]

    # Updating a request
    set_role_request(index, "vanatteveldt@gmail.com", Role.METAREADER)
    refresh_system_index()
    requests = {r["email"]: r for r in get_role_requests(index)}
    assert len(requests) == 1
    assert requests["vanatteveldt@gmail.com"]["role"] == "METAREADER"

    # Cancelling a request
    set_role_request(index, "vanatteveldt@gmail.com", role=None)
    refresh_system_index()
    assert get_role_requests(index) == []
