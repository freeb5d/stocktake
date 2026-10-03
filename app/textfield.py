"""Free text somebody typed, held to the column it is going into.

The inputs carry `maxlength`, but that is the browser's courtesy and a direct
POST ignores it. SQLite stores any length in a `String(n)` column; Postgres
refuses with "value too long" and the request is a 500. So the server checks.

Refused, never cut: a note somebody typed is theirs, and a silently shortened
one is a sentence they did not write. (Values the app itself cuts to fit, such as
portfolio and API key names, are a separate decision.) The limit is read from the
column, so it cannot drift from the schema — the same idea as `money.parse` for
numbers.
"""

from __future__ import annotations


class TextError(ValueError):
    """Text too long for where it is going.

    A `ValueError`, so a caller that already catches that keeps working; its own
    type so a form can show this message instead of a generic one.
    """


def fit(text, column, name: str | None = None) -> str | None:
    """`text` stripped, or None when it is empty; `TextError` when it is too long.

    None for empty is right for an optional field such as a note. A required
    field, or one with a default, keeps its own rule for empty at the call site.
    The message says how long it was and how long it may be, and does not repeat
    the text: a form carries it in a query string, and a pasted page would make
    that URL too long.
    """
    value = str(text if text is not None else "").strip()
    if not value:
        return None
    limit = column.type.length
    if len(value) > limit:
        label = f"{name}: " if name else ""
        raise TextError(
            f"{label}that is {len(value):,} characters, and the most it can hold "
            f"is {limit:,}")
    return value


def problem(text, column, name: str | None = None) -> str | None:
    """The message `fit` would raise, or None — for a form that collects problems
    into one `or` chain instead of catching an exception."""
    try:
        fit(text, column, name)
    except TextError as exc:
        return str(exc)
    return None
