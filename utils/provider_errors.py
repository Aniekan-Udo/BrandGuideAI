"""Telling a model provider's outage apart from a bug in our own code."""
import importlib
import re


def provider_errors() -> tuple:
    """Errors that mean the model provider could not answer, not that our code is wrong.

    Kept narrow on purpose: a bug in a node must still fail loudly, not be
    reported as an outage.
    """
    errors: list = [TimeoutError, ConnectionError]
    for module, name in (("httpx", "HTTPError"), ("openai", "APIError"), ("groq", "APIError"),
                         ("anthropic", "APIError"), ("google.api_core.exceptions", "GoogleAPIError")):
        try:
            errors.append(getattr(importlib.import_module(module), name))
        except (ImportError, AttributeError):
            continue
    return tuple(errors)


def _status(exc) -> int | None:
    for source in (exc, getattr(exc, "response", None)):
        code = getattr(source, "status_code", None)
        if isinstance(code, int):
            return code
    match = re.search(r"Error code: (\d{3})", str(exc))
    return int(match.group(1)) if match else None


def retry_after(exc, overloaded_wait: float = 10.0) -> float | None:
    """Seconds to wait before one retry, or None when retrying cannot help.

    A rate limit says how long to wait ("Please retry in 46.9s"); a daily quota
    says hours, which is reported as its real delay so the caller can refuse it.
    An overloaded model (503) gets a short fixed wait.
    """
    status = _status(exc)
    if status == 429:
        text = str(exc)
        match = (re.search(r"retry in ([\d.]+)\s*s", text, re.I)
                 or re.search(r"retryDelay'?\"?:\s*'?\"?(\d+)s", text))
        return float(match.group(1)) if match else 30.0
    if status in (500, 502, 503, 504):
        return overloaded_wait
    return None
