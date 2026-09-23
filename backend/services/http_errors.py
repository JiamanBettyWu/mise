"""Secret-safe descriptions and wrappers for HTTP client failures.

httpx exceptions can embed the full request URL in their string and traceback.
Several upstreams used by mise put credentials in that URL, so callers must not
log or re-raise the raw exception across a traceback-logging boundary.
"""

import httpx


class UpstreamHTTPError(RuntimeError):
    """An HTTP failure whose message contains no request URL."""


def describe_http_error(exc: httpx.HTTPError) -> str:
    """Return useful diagnostics without stringifying ``exc`` or its request."""

    status = getattr(getattr(exc, "response", None), "status_code", None)
    return f"{type(exc).__name__} (status={status})"


def sanitized_http_error(provider: str, exc: httpx.HTTPError) -> UpstreamHTTPError:
    """Replace a URL-bearing httpx exception before it reaches outer logging."""

    return UpstreamHTTPError(f"{provider} request failed: {describe_http_error(exc)}")
