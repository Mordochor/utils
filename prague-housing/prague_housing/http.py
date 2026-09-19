from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol


class HttpClient(Protocol):
    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        pause_s: float = 0.0,
    ) -> Any: ...


class UrlLibHttp:
    def __init__(self, user_agent: str, timeout_s: int = 30) -> None:
        self.user_agent = user_agent
        self.timeout_s = timeout_s

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        pause_s: float = 0.0,
    ) -> Any:
        if params:
            query = urllib.parse.urlencode(
                {key: value for key, value in params.items() if value is not None}
            )
            url = f"{url}?{query}"
        request_headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        req = urllib.request.Request(url, headers=request_headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"HTTP {exc.code} for {url}: {detail}") from exc
        if pause_s:
            time.sleep(pause_s)
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))

    def post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
        data = json.dumps(payload).encode("utf-8")
        request_headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if headers:
            request_headers.update(headers)
        req = urllib.request.Request(url, data=data, headers=request_headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"HTTP {exc.code} for {url}: {detail}") from exc
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))


class SequenceHttp:
    """Test double that returns queued JSON payloads in order."""

    def __init__(self, responses: list[Any] | None = None, by_url: dict[str, Any] | None = None) -> None:
        self.responses = list(responses or [])
        self.by_url = dict(by_url or {})
        self.calls: list[str] = []

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        pause_s: float = 0.0,
    ) -> Any:
        del headers, pause_s
        if params:
            query = urllib.parse.urlencode(
                {key: value for key, value in params.items() if value is not None}
            )
            full = f"{url}?{query}"
        else:
            full = url
        self.calls.append(full)
        if url in self.by_url:
            return self.by_url[url]
        if full in self.by_url:
            return self.by_url[full]
        for prefix, payload in self.by_url.items():
            if full.startswith(prefix) or url.startswith(prefix):
                return payload
        if not self.responses:
            raise AssertionError(f"No queued HTTP response for {full}")
        return self.responses.pop(0)
