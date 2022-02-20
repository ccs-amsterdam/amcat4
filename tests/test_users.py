from amcat4.auth import verify_user, verify_token, Role


def test_create_check_user(user):
    """Can we create a user and verify its password?"""
    u = verify_user(user.email, user.plaintext_password)
    assert u is not None, "User could not be found"
    assert verify_user(user.email, "fout") is None
    u.delete_instance()
    assert verify_user(user.email, user.plaintext_password) is None


def test_token(user):
    """Can we create a token and verify it?"""
    assert verify_token("invalid") is None
    token = user.create_token()
    assert verify_token(token).email == user.email


def test_token_expiry(user):
    """Can we create a token and verify it?"""
    token = user.create_token(days_valid=-1)
    assert verify_token(token) is None


def test_indices(user, index, guest_index):
    """Does user.indices return the correct results?"""
    assert set(user.indices(include_guest=False)) == set()
    assert guest_index in set(user.indices(include_guest=True))
    index.set_role(user, Role.WRITER)
    assert set(user.indices(include_guest=False)) == {index}
    assert {index, guest_index} - set(user.indices(include_guest=True)) == set()
