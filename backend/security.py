import hashlib
import hmac
import os

ITERATIONS = 200_000
PREFIX = "pbkdf2"


def hash_password(password):
    """Return 'pbkdf2$iterations$salt$hash'. A new random salt is used every time."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"{PREFIX}${ITERATIONS}${salt.hex()}${digest.hex()}"


def is_hashed(value):
    return isinstance(value, str) and value.startswith(PREFIX + "$")


def verify_password(password, stored):
    """Check a typed password against the stored hash."""
    if not is_hashed(stored):
        return False

    _, iterations, salt, expected = stored.split("$")
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
    )
    return hmac.compare_digest(digest.hex(), expected)
