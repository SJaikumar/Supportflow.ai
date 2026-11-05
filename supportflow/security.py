"""Password hashing and role checks. Demo authentication, not production identity management."""
import hashlib
import hmac
import secrets

ITERATIONS = 360_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}'


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, expected_hex = stored.split('$')
        if scheme != 'pbkdf2_sha256':
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(actual, bytes.fromhex(expected_hex))
    except (TypeError, ValueError, AttributeError):
        return False


def may_review(role: str) -> bool:
    return role in ('approver', 'admin')


def may_manage_tickets(role: str) -> bool:
    return role in ('agent', 'approver', 'admin')
