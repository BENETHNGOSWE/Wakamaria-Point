"""Turn a provider failure into one line an operator can act on.

Pure: no Frappe import. Deliberately returns only the HTTP status and the
provider's own message body. Request headers are never touched, so an API key
cannot leak into the Error Log or the Settings form.
"""


def describe_error(error, limit=160):
    response = getattr(error, "response", None)
    if response is None:
        return f"{type(error).__name__}: {error}"[:200]

    body = ""
    try:
        body = " ".join((response.text or "").split())[:limit]
    except Exception:
        body = ""

    status = getattr(response, "status_code", "?")
    return f"HTTP {status} {body}".strip()
