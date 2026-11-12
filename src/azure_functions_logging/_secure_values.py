"""Single bounded sanitization engine shared by every redaction profile.

Both the legacy best-effort ``RedactionFilter`` and the fail-closed secure profile
traverse values through :class:`ValueMasker`; they differ only in the
:class:`RedactionProfile` policy (keys, patterns and ``fail_closed``). Traversal
budgets that genuinely belong to sanitization live here. Unrelated budgets
(attribute flattening depth, formatter serialization, isolated record copying)
keep their own named constants in their own modules.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
import re
from typing import Final

from ._redaction import MASK, is_sensitive
from ._redaction import mask_patterns as _mask_patterns

MAX_NODES: Final = 4096  # fail-closed node budget per record (legacy has none)
MAX_DEPTH: Final = 10  # container depth at which values are masked, both profiles
MAX_TEXT: Final = 65536  # fail-closed text length at which a string is masked in full


@dataclass(frozen=True, slots=True)
class RedactionProfile:
    """Policy input of the shared engine.

    ``fail_closed=False`` is the legacy compatibility profile: errors preserve the
    original value, opaque objects pass through and only ``dict``/``list``/``tuple``
    containers are traversed. ``fail_closed=True`` bounds nodes and text, renders
    opaque values safely and masks anything that cannot be converted.
    """

    keys: frozenset[str]
    patterns: tuple[re.Pattern[str], ...] = ()
    fail_closed: bool = False


def mask_text(text: str, patterns: tuple[re.Pattern[str], ...]) -> str:
    if len(text) > MAX_TEXT:
        return MASK
    for pattern in patterns:
        text = pattern.sub(lambda m: (m.groupdict().get("keep") or "") + MASK, text)
    return text


@dataclass(slots=True)
class ValueMasker:
    """Per-record traversal state for one profile; never retains opaque objects."""

    profile: RedactionProfile
    remaining: int = MAX_NODES
    keys: frozenset[str] = field(init=False)
    patterns: tuple[re.Pattern[str], ...] = field(init=False)

    def __post_init__(self) -> None:
        self.keys = self.profile.keys
        self.patterns = self.profile.patterns

    def mask(self, value: object, depth: int = 0, seen: frozenset[int] = frozenset()) -> object:
        if self.profile.fail_closed:
            return self._mask_closed(value, depth, seen)
        return self._mask_legacy(value, depth, seen)

    def _mask_legacy(self, value: object, depth: int, seen: frozenset[int]) -> object:
        """Best-effort traversal: any error preserves the value at that level."""
        try:
            if depth >= MAX_DEPTH:
                return MASK  # over-deep structures are treated as potentially sensitive
            if isinstance(value, str):
                return _mask_patterns(value, self.patterns) if self.patterns else value
            if isinstance(value, dict):
                if id(value) in seen:
                    return MASK
                ancestors = seen | {id(value)}
                return {
                    key: (
                        MASK
                        if isinstance(key, str) and is_sensitive(key, self.keys)
                        else self._mask_legacy(item, depth + 1, ancestors)
                    )
                    for key, item in value.items()
                }
            if isinstance(value, (list, tuple)):
                if id(value) in seen:
                    return MASK
                ancestors = seen | {id(value)}
                redacted = [self._mask_legacy(item, depth + 1, ancestors) for item in value]
                return tuple(redacted) if isinstance(value, tuple) else redacted
            return value
        except Exception:  # nosec B110 -- redaction must never raise
            return value

    def _mask_closed(self, value: object, depth: int, seen: frozenset[int]) -> object:
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
                        safe_key = self._mask_closed(key, depth + 1, ancestors)
                        result[safe_key] = (
                            MASK
                            if isinstance(key, str) and is_sensitive(key, self.keys)
                            else self._mask_closed(item, depth + 1, ancestors)
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
                        items.append(self._mask_closed(item, depth + 1, ancestors))
                    return tuple(items) if isinstance(value, tuple) else items
                case _:
                    return mask_text(repr(value), self.patterns)
        except Exception:
            # Arbitrary Mapping/repr/regex user code is a never-raise logging boundary.
            return MASK
