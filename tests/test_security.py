from app.core.security import hash_password, verify_password


def test_password_hashes_are_salted_and_verifiable():
    password = "a-long-password-for-testing"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash
    assert verify_password(password, first_hash)
    assert not verify_password("incorrect-password", first_hash)
    assert not verify_password(password, None)
