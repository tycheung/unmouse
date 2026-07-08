from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")
ExceptionTypes = type[BaseException] | tuple[type[BaseException], ...]


def prefer_or_fallback(
    *,
    prefer: bool,
    make_preferred: Callable[[], T],
    make_fallback: Callable[[], T],
    exceptions: ExceptionTypes | None = (ImportError,),
) -> T:
    if not prefer:
        return make_fallback()

    if exceptions is None:
        return make_preferred()

    try:
        return make_preferred()
    except exceptions:
        return make_fallback()

