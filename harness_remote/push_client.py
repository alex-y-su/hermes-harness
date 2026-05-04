from __future__ import annotations

import json
import socket
import ssl
from typing import Any
from urllib.parse import urlparse, urlunparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from harness.bridge.hmac import sign_push


class PushClientError(RuntimeError):
    pass


def build_push_event(
    *,
    team_name: str,
    task_id: str,
    state: str,
    sequence: int,
    message: str = "",
    artifacts: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "team_name": team_name,
        "task_id": task_id,
        "state": state,
        "sequence": sequence,
        "message": message,
        "metadata": metadata or {},
    }
    if artifacts is not None:
        event["artifacts"] = artifacts
    return event


def post_push_event(
    *,
    push_url: str,
    bearer_token: str,
    bridge_secret: str,
    event: dict[str, Any],
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    team_name = str(event["team_name"])
    task_id = str(event["task_id"])
    state = str(event["state"])
    sequence = int(event["sequence"])
    signature = sign_push(
        secret=bridge_secret,
        team_name=team_name,
        task_id=task_id,
        state=state,
        sequence=sequence,
        body=event,
    )
    payload = json.dumps(event, separators=(",", ":"), sort_keys=True).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-A2A-Notification-Token": signature,
    }
    request = Request(
        push_url,
        data=payload,
        method="POST",
        headers=headers,
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise PushClientError(f"push failed with HTTP {error.code}: {detail}") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        try:
            return post_https_json_ipv4(push_url, headers, payload, timeout_seconds)
        except PushClientError as fallback_error:
            raise PushClientError(f"push failed: {error}; IPv4 fallback failed: {fallback_error}") from error


def post_https_json_ipv4(push_url: str, headers: dict[str, str], payload: bytes, timeout_seconds: float) -> dict[str, Any]:
    """POST JSON over IPv4 for tunnel hosts that publish unusable IPv6 records."""
    parsed = urlparse(push_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise PushClientError("IPv4 fallback only supports https URLs")
    port = parsed.port or 443
    path = urlunparse(("", "", parsed.path or "/", "", parsed.query, ""))
    addresses = socket.getaddrinfo(parsed.hostname, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
    if not addresses:
        raise PushClientError(f"no IPv4 address found for {parsed.hostname}")
    request_headers = {
        "Host": parsed.netloc,
        "Content-Length": str(len(payload)),
        "Connection": "close",
        **headers,
    }
    header_text = "".join(f"{key}: {value}\r\n" for key, value in request_headers.items())
    request_bytes = f"POST {path} HTTP/1.1\r\n{header_text}\r\n".encode("utf-8") + payload
    last_error: Exception | None = None
    for _family, socktype, proto, _canonname, sockaddr in addresses:
        try:
            with socket.create_connection(sockaddr, timeout=timeout_seconds) as raw_sock:
                context = ssl.create_default_context()
                with context.wrap_socket(raw_sock, server_hostname=parsed.hostname) as tls_sock:
                    tls_sock.settimeout(timeout_seconds)
                    tls_sock.sendall(request_bytes)
                    chunks = []
                    while True:
                        chunk = tls_sock.recv(65536)
                        if not chunk:
                            break
                        chunks.append(chunk)
            return parse_http_json_response(b"".join(chunks))
        except Exception as error:  # pragma: no cover - network fallback path
            last_error = error
    raise PushClientError(str(last_error) if last_error else "IPv4 fallback failed")


def parse_http_json_response(response: bytes) -> dict[str, Any]:
    head, _, body = response.partition(b"\r\n\r\n")
    status_line = head.splitlines()[0].decode("iso-8859-1", errors="replace") if head else ""
    parts = status_line.split()
    if len(parts) < 2 or not parts[1].isdigit():
        raise PushClientError(f"invalid HTTP response: {status_line}")
    status = int(parts[1])
    text = body.decode("utf-8", errors="replace")
    if status < 200 or status >= 300:
        raise PushClientError(f"push failed with HTTP {status}: {text}")
    return json.loads(text) if text else {}
