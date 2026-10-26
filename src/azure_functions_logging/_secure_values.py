"""Bounded fail-closed conversion of untrusted logging values."""

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Final

from ._redaction import MASK, is_sensitive

MAX_NODES: Final = 4096
MAX_DEPTH: Final = 10
MAX_TEXT: Final = 65536


def mask_text(text: str, patterns: tuple[re.Pattern[str], ...]) -> str:
    if len(text) > MAX_TEXT:
        return MASK
    for pattern in patterns:
        text = pattern.sub(lambda m: (m.groupdict().get("keep") or "") + MASK, text)
    return text


@dataclass(slots=True)
class ValueMasker:
    """Per-record traversal budget; never retains original opaque objects."""

    keys: frozenset[str]
    patterns: tuple[re.Pattern[str], ...]
    remaining: int = MAX_NODES

    def mask(self, value: object, depth: int = 0, seen: frozenset[int] = frozenset()) -> object:
        if depth >= MAX_DEPTH or self.remaining <= 0:
            return MASK
        self.remaining -= 1
        try:
            match value:
                case str() if type(value) is str:
                    return mask_text(value, self.patterns)
                case None | bool() | int() | float() if type(value) in (
                    type(None),
                    bool,
                    int,
                    float,
                ):
                    return value
                case Mapping():
                    if id(value) in seen:
                        return MASK
                    ancestors = seen | {id(value)}
                    result: dict[object, object] = {}
                    for key, item in value.items():
                        if self.remaining <= 0:
                            return MASK
                        self.remaining -= 1
                        safe_key = self.mask(key, depth + 1, ancestors)
                        result[safe_key] = (
                            MASK
                            if isinstance(key, str) and is_sensitive(key, self.keys)
                            else self.mask(item, depth + 1, ancestors)
                        )
                    return result
                case list() | tuple() | set() | frozenset():
                    if id(value) in seen:
                        return MASK
                    ancestors = seen | {id(value)}
                    items: list[object] = []
                    for item in value:
                        if self.remaining <= 0:
                            return MASK
                        items.append(self.mask(item, depth + 1, ancestors))
                    return tuple(items) if isinstance(value, tuple) else items
                case _:
                    return mask_text(repr(value), self.patterns)
        except Exception:
            # Arbitrary Mapping/repr/regex user code is a never-raise logging boundary.
            return MASK
