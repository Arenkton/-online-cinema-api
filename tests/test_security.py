from src.security import hash_password, verify_password


def test_hash_password():
    password = "MySecurePassword123!"

    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$argon2")


def test_verify_correct_password():
    password = "MySecurePassword123!"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_verify_wrong_password():
    hashed = hash_password("MySecurePassword123!")

    assert verify_password("WrongPassword", hashed) is False


def test_hashes_are_different():
    password = "MySecurePassword123!"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash


def test_verify_invalid_hash():
    assert verify_password(
        "MySecurePassword123!",
        "invalid_hash"
    ) is False
