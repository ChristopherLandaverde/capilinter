"""The only module in CAPILinter that may reach the network.

Every request passes `check_request` first: GET only, to
https://graph.facebook.com/<API_VERSION>/dataset_quality. Anything else raises
RequestRefused before a connection is opened. Redirects are never followed. The access token travels in the
Authorization header, never in the URL, and is redacted from every error.

Fixture mode: if CAPILINTER_LIVE_FIXTURE names a file, the guard still runs on
the URL that would have been called, then the file's JSON is returned instead of
a network response. Tests and the recorded runs use this; no real token or
account is involved.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

GRAPH_HOST = "graph.facebook.com"
API_VERSION = "v25.0"
ALLOWED_PATH = f"/{API_VERSION}/dataset_quality"
TIMEOUT_SECONDS = 30
FIXTURE_ENV = "CAPILINTER_LIVE_FIXTURE"
# The name of an environment variable, not a secret.
TOKEN_ENV = "META_ACCESS_TOKEN"  # nosec B105


class RequestRefused(ValueError):
    """The request guard stopped a request before it was sent."""


class LiveError(Exception):
    """A live-read failure. kind: usage, credentials, api or refused."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def check_request(method: str, url: str) -> None:
    """Raise RequestRefused unless this is GET https://graph.facebook.com/<version>/dataset_quality."""
    if method != "GET":
        raise RequestRefused(f"Only GET is allowed, got {method!r}.")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https":
        raise RequestRefused(f"Only https is allowed, got {parts.scheme!r}.")
    if parts.hostname != GRAPH_HOST or parts.port is not None or parts.username or parts.password:
        raise RequestRefused(f"Only {GRAPH_HOST} is allowed, got {parts.netloc!r}.")
    if parts.path != ALLOWED_PATH:
        raise RequestRefused(f"Only {ALLOWED_PATH} is allowed, got {parts.path!r}.")


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect.

    urllib copies every header except content headers onto the redirected
    request, so following one would send the Authorization token to whatever
    host the redirect names.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        parts = urllib.parse.urlsplit(newurl)
        raise RequestRefused(f"HTTP {code} redirect to {parts.scheme}://{parts.netloc}{parts.path} refused.")


_OPENER = urllib.request.build_opener(_RefuseRedirects())


def _open(request: urllib.request.Request) -> Any:
    # Only reached after check_request has approved the URL.
    return _OPENER.open(request, timeout=TIMEOUT_SECONDS)


def _redact(text: str, token: str) -> str:
    return text.replace(token, "[redacted]") if token else text


def redact_env_token(text: str) -> str:
    """Remove the configured token (raw and stripped) from any text before it is shown."""
    raw = os.environ.get(TOKEN_ENV, "")
    for candidate in {raw, raw.strip()}:
        if candidate:
            text = text.replace(candidate, "[redacted]")
    return text


def _raise_for_graph_error(body: Any, token: str) -> None:
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        err = body["error"]
        message = str(err.get("message", "Graph API error"))
        code = err.get("code")
        detail = f"{message} (code {code})" if code is not None else message
        raise LiveError("api", _redact(f"Meta Graph API: {detail}", token))


def get_json(params: dict[str, str], token: str) -> Any:
    """GET the Dataset Quality endpoint with query params; return parsed JSON."""
    url = f"https://{GRAPH_HOST}{ALLOWED_PATH}?{urllib.parse.urlencode(params)}"
    check_request("GET", url)

    fixture = os.environ.get(FIXTURE_ENV)
    if fixture:
        try:
            body = json.loads(Path(fixture).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LiveError("usage", f"Could not read {FIXTURE_ENV} file: {exc}") from None
        _raise_for_graph_error(body, token)
        return body

    request = urllib.request.Request(
        url, method="GET", headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    try:
        with _open(request) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise LiveError("api", f"Meta Graph API returned HTTP {exc.code}.") from None
        _raise_for_graph_error(body, token)
        raise LiveError("api", f"Meta Graph API returned HTTP {exc.code}.") from None
    except RequestRefused:
        raise
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LiveError("api", _redact(f"Could not reach {GRAPH_HOST}: {exc}", token)) from None
    except Exception as exc:  # anything else from the transport, e.g. http.client header errors
        raise LiveError("api", _redact(f"Request to {GRAPH_HOST} failed: {type(exc).__name__}: {exc}", token)) from None
    _raise_for_graph_error(body, token)
    return body
