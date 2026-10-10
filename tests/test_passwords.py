from service.passwords import hash_password, verify_password


def test_password_roundtrip():
    stored = hash_password("changeme")
    assert verify_password("changeme", stored)
    assert not verify_password("wrong", stored)
