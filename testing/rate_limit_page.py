"""A refused request gets the tool's own page (TO DO FL-104, 26 October 2026).

phronon_common.rate_limit.RateLimitMiddleware answered every refused request
with a line of JSON, so a participant who joined too often from one classroom
connection saw `{"detail": "Too many requests..."}` instead of a page. Since
1.89.0 a tool passes `limited_response=` and the middleware answers with that
page, status 429 and Retry-After.

`refused_answer` drives the tool's real middleware stack: it makes the
limiter's window refuse the next request and returns what the client got, so
the check covers the tool's wiring and its page together. No pytest here (see
__init__.py); the tool's wrapper passes its own monkeypatch.
"""
from __future__ import annotations


def limiter(app):
    """The RateLimitMiddleware in a built middleware stack, or None."""
    node = getattr(app, "middleware_stack", None)
    while node is not None:
        if type(node).__name__ == "RateLimitMiddleware":
            return node
        node = getattr(node, "app", None)
    return None


def refused_answer(monkeypatch, client, path: str, data=None, retry_after: int = 30):
    """POST `path` with the limiter refusing it; returns the response."""
    client.get("/health")                     # builds the middleware stack
    found = limiter(client.app)
    assert found is not None, "the rate-limit middleware is not in the stack"
    assert found.config.get_rule(path) is not None, f"no rate-limit rule covers {path}"
    monkeypatch.setattr(found.window, "check",
                        lambda key, max_requests, window: (False, max_requests, retry_after))
    return client.post(path, data=data or {}, follow_redirects=False)


def assert_the_tools_page(response, words: str, retry_after: int = 30) -> None:
    """429 with Retry-After, an HTML page carrying `words`, and no JSON."""
    assert response.status_code == 429, response.status_code
    assert response.headers.get("retry-after") == str(retry_after)
    assert response.headers.get("content-type", "").startswith("text/html"), (
        "the refused request was answered with " + response.headers.get("content-type", "?"))
    assert words in response.text, f"the page does not say {words!r}"
    assert '"detail"' not in response.text, "the bare JSON answer is back"
