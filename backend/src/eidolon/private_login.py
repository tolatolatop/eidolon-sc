"""Optional single-owner password authentication and its process-wide failure limit."""

import hashlib
import hmac
import math
import re
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable

_HASH = re.compile(r"scrypt-v1:([0-9a-f]{32}):([0-9a-f]{64})")
_FAILURES = 5
_WINDOW = 60


def valid_password_hash(value: str) -> bool:
    """Whether a stored value uses the one supported scrypt format."""
    return _HASH.fullmatch(value) is not None


def _digest(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)


def hash_password(password: str) -> str:
    """Hash an 8–256 character password with a fresh cryptographic 16-byte salt."""
    if not 8 <= len(password) <= 256:
        raise ValueError("访问口令须为 8～256 个字符")
    salt = secrets.token_bytes(16)
    return f"scrypt-v1:{salt.hex()}:{_digest(password, salt).hex()}"


def verify_password(password: object, password_hash: str) -> bool:
    """Check a password without exposing it or accepting alternate hash parameters."""
    match = _HASH.fullmatch(password_hash)
    if match is None or not isinstance(password, str) or not 8 <= len(password) <= 256:
        return False
    try:
        actual = _digest(password, bytes.fromhex(match[1]))
    except UnicodeEncodeError:
        return False
    return hmac.compare_digest(actual, bytes.fromhex(match[2]))


class LoginCooling(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("访问口令尝试次数过多，请稍后重试")
        self.retry_after = retry_after


class PasswordLogin:
    """One shared failure window; checking, hashing and recording hold the same lock."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._failures: deque[float] = deque()
        self._lock = threading.Lock()

    def verify(self, password: object, password_hash: str) -> bool:
        with self._lock:
            now = self._clock()
            while self._failures and self._failures[0] <= now - _WINDOW:
                self._failures.popleft()
            if len(self._failures) >= _FAILURES:
                raise LoginCooling(max(1, math.ceil(self._failures[0] + _WINDOW - now)))
            valid = verify_password(password, password_hash)
            if not valid:
                self._failures.append(self._clock())
            return valid


# All clients and app instances in this process share the same budget, without trusting
# peer addresses or forwarded headers. A process restart starts a fresh window.
LOGIN_LIMITER = PasswordLogin()
