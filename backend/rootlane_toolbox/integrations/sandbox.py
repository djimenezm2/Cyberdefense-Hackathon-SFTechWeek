import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from ..core.guards import GuardError

METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
DROPPED_HEADERS = {
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "upgrade",
    "te",
    "trailer",
    "expect",
    "proxy-authorization",
    "proxy-connection",
}
EXCERPT_CHARS = 500
_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_UNSAFE_PATH = re.compile(r"[\s\\\x00-\x1f\x7f]")


class Reproduction(BaseModel):
    """
    The agent's reproduction request, replayed only against a replica.

    Attributes:
        method (str): HTTP method, upper-cased.
        path (str): Origin-relative path with optional query, e.g. `/rest/basket/2?x=1`.
        headers (dict[str, str]): Request headers; host and hop-by-hop headers are dropped.
        body (Any): None, a string sent as-is, or a JSON value.
        expected_blocked_status (int): The 4xx status that means the request was rejected.
    """

    method: str
    path: str
    headers: dict[str, str] = {}
    body: Any = None
    expected_blocked_status: int = Field(ge=400, le=499)

    @field_validator("method")
    @classmethod
    def _method(cls, value: str) -> str:
        method = value.upper()
        if method not in METHODS:
            raise ValueError(f"method not allowed: {value!r}")
        return method

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        parts = urlsplit(value)
        if (not value.startswith("/") or value.startswith("//") or parts.scheme or parts.netloc
                or _UNSAFE_PATH.search(value)):
            raise ValueError(f"path must be origin-relative: {value!r}")
        return value

    @field_validator("headers")
    @classmethod
    def _headers(cls, value: dict[str, str]) -> dict[str, str]:
        kept = {}
        for name, header in value.items():
            if not _TOKEN.match(name) or "\r" in header or "\n" in header:
                raise ValueError(f"illegal header: {name!r}")
            if name.lower() not in DROPPED_HEADERS:
                kept[name] = header
        return kept


def parse_reproduction(data: dict) -> Reproduction:
    """
    Validate an agent-supplied reproduction.

    Raises:
        GuardError: If any field is missing or unsafe.
    """
    try:
        return Reproduction.model_validate(data)
    except ValidationError as exc:
        reasons = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise GuardError(f"invalid reproduction: {reasons}") from None


def replica_url(base_url: str, path: str) -> str:
    """
    Join the replica base URL and a reproduction path.

    Raises:
        GuardError: If the result would point anywhere but the replica.
    """
    url = httpx.URL(base_url + path)
    base = httpx.URL(base_url)
    if (url.scheme, url.host, url.port) != (base.scheme, base.host, base.port):
        raise GuardError(f"path leaves the replica: {path!r}")
    return str(url)


def replay(client: httpx.Client, base_url: str, reproduction: Reproduction) -> dict:
    """
    Send the reproduction to a replica.

    Args:
        client (httpx.Client): HTTP client with bounded timeouts.
        base_url (str): The replica origin, e.g. `http://127.0.0.1:3001`.
        reproduction (Reproduction): The validated request.

    Returns:
        dict: `{"status": int, "excerpt": str}`, the excerpt being the first characters of the body.
    """
    kwargs: dict[str, Any] = {"headers": reproduction.headers, "follow_redirects": False}
    if isinstance(reproduction.body, str):
        kwargs["content"] = reproduction.body
    elif reproduction.body is not None:
        kwargs["json"] = reproduction.body
    url = replica_url(base_url, reproduction.path)
    response = client.request(reproduction.method, url, **kwargs)
    return {"status": response.status_code, "excerpt": response.text[:EXCERPT_CHARS]}
