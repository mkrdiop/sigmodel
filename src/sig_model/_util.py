"""Internal helpers. Not part of the public API."""

from __future__ import annotations

import copy
import math
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping, Sequence, TypeVar

from .errors import SIGError, join_path

E = TypeVar("E", bound=Enum)

# JSON Schema patterns, applied with fullmatch (Python's "$" tolerates a trailing newline).
GRAPH_ID_RE = re.compile(r"[a-zA-Z0-9._-]+")
NODE_ID_RE = re.compile(r"[a-zA-Z0-9._:-]+")


class _Missing:
    """Singleton meaning "property absent", which is distinct from JSON ``null``."""

    __slots__ = ()
    _instance: "_Missing | None" = None

    def __new__(cls) -> "_Missing":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False

    def __copy__(self) -> "_Missing":
        return self

    def __deepcopy__(self, memo: dict) -> "_Missing":
        return self


MISSING = _Missing()


# ---------------------------------------------------------------- timestamps

def utcnow() -> datetime:
    """Current time, timezone-aware, truncated to whole seconds."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_datetime(value: Any, path: str = "") -> datetime:
    """Parse an RFC 3339 date-time. A UTC offset (or ``Z``) is mandatory."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value[:-1] + "+00:00" if value[-1:] in ("Z", "z") else value
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            raise SIGError(f"invalid date-time {value!r}", path) from None
    else:
        raise SIGError(f"expected a date-time string, got {type(value).__name__}", path)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise SIGError("date-time must include a UTC offset (for example 'Z')", path)
    return dt


def format_datetime(dt: datetime) -> str:
    """Serialize to RFC 3339, using ``Z`` for UTC."""
    if dt.utcoffset() == timedelta(0):
        return dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    return dt.isoformat()


# ---------------------------------------------------------------- validators

def coerce_enum(enum_cls: type[E], value: Any, path: str) -> E:
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(m.value for m in enum_cls)  # type: ignore[attr-defined]
        raise SIGError(f"invalid value {value!r}; expected one of: {allowed}", path) from None


def check_str(value: Any, path: str, *, non_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise SIGError(f"expected a string, got {type(value).__name__}", path)
    if non_empty and not value:
        raise SIGError("must not be empty", path)
    return value


def check_pattern(value: Any, pattern: re.Pattern[str], path: str) -> str:
    check_str(value, path)
    if not pattern.fullmatch(value):
        raise SIGError(f"{value!r} does not match the required pattern {pattern.pattern!r}", path)
    return value


def check_str_list(value: Any, path: str, *, unique: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise SIGError(f"expected a list, got {type(value).__name__}", path)
    for i, item in enumerate(value):
        check_str(item, f"{path}[{i}]")
    if unique and len(set(value)) != len(value):
        raise SIGError("items must be unique", path)
    return value


def check_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SIGError(f"expected an object, got {type(value).__name__}", path)
    return value


def check_confidence(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SIGError("must be a number", path)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise SIGError(f"must be between 0 and 1, got {value!r}", path)
    return float(value)


def check_line(value: Any, path: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise SIGError("must be an integer", path)
    if value < 1:
        raise SIGError("must be 1 or greater", path)
    return value


def dup_free(values: Sequence[str]) -> list[str]:
    """Return the values that occur more than once, in first-seen order."""
    seen: set[str] = set()
    dups: list[str] = []
    for v in values:
        if v in seen and v not in dups:
            dups.append(v)
        seen.add(v)
    return dups


# ---------------------------------------------------------------- reading

_KINDS: dict[str, tuple[type, ...]] = {
    "str": (str,),
    "int": (int,),
    "num": (int, float),
    "dict": (dict,),
    "list": (list,),
}


class Reader:
    """Shape-checked access to one JSON object.

    It verifies presence and JSON type only; semantic checks (patterns, ranges,
    enum membership) live in each model's ``__post_init__`` so that objects built
    in code and objects loaded from JSON follow identical rules.
    """

    def __init__(self, data: Any, path: str, strict: bool) -> None:
        if not isinstance(data, Mapping):
            raise SIGError(f"expected an object, got {type(data).__name__}", path)
        self._data = data
        self.path = path
        self.strict = strict
        self._seen: set[str] = set()

    def take(self, key: str, kind: str, *, required: bool = False, default: Any = None) -> Any:
        self._seen.add(key)
        where = join_path(self.path, key)
        if key not in self._data:
            if required:
                raise SIGError("required property is missing", where)
            return default
        value = self._data[key]
        if kind != "any":
            ok = isinstance(value, _KINDS[kind])
            if kind in ("int", "num") and isinstance(value, bool):
                ok = False
            if not ok:
                raise SIGError(f"expected {kind}, got {type(value).__name__}", where)
        # Never alias the caller's containers.
        return copy.deepcopy(value) if isinstance(value, (dict, list)) else value

    def str_list(self, key: str, *, required: bool = False) -> list[str]:
        raw = self.take(key, "list", required=required, default=[])
        where = join_path(self.path, key)
        for i, item in enumerate(raw):
            if not isinstance(item, str):
                raise SIGError(f"expected str, got {type(item).__name__}", f"{where}[{i}]")
        return raw

    def has(self, key: str) -> bool:
        return key in self._data

    def extras(self) -> dict[str, Any]:
        """Unknown keys. In strict mode any unknown key is an error."""
        unknown = {k: copy.deepcopy(v) for k, v in self._data.items() if k not in self._seen}
        if unknown and self.strict:
            names = ", ".join(repr(k) for k in unknown)
            noun = "property" if len(unknown) == 1 else "properties"
            raise SIGError(f"unknown {noun}: {names}", self.path)
        return unknown

    def rest(self) -> dict[str, Any]:
        """Unknown keys for objects whose schema allows additional properties."""
        return {k: copy.deepcopy(v) for k, v in self._data.items() if k not in self._seen}


def construct(cls: type, where: str, /, **kwargs: Any) -> Any:
    """Build a model object, attaching ``where`` to any validation error.

    Both leading parameters are positional-only so that model fields named ``path``
    (as on ``EvidenceSource``) pass through ``kwargs`` without colliding.
    """
    try:
        return cls(**kwargs)
    except SIGError as exc:
        raise exc.with_path(where) from None
