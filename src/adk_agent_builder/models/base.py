"""Pydantic v1 / v2 compatible base model for deterministic validation and serialization."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound="CompatModel")


def _normalize_primitives(obj: Any) -> Any:
    """Recursively convert Enums and Paths into plain YAML/JSON-safe primitives."""
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return { _normalize_primitives(k): _normalize_primitives(v) for k, v in obj.items() }
    if isinstance(obj, (list, tuple)):
        return [_normalize_primitives(item) for item in obj]
    return obj


class CompatModel(BaseModel):
    """Base model providing unified serialization across Pydantic v1 and v2."""

    class Config:
        extra = "allow"
        arbitrary_types_allowed = True

    def to_dict(self, *, exclude_none: bool = False) -> Dict[str, Any]:
        """Convert model to a plain primitive dictionary across Pydantic v1 and v2."""
        if hasattr(self, "model_dump"):
            raw = self.model_dump(exclude_none=exclude_none)  # type: ignore[attr-defined]
        else:
            raw = self.dict(exclude_none=exclude_none)
        return _normalize_primitives(raw)

    def to_json(self, *, indent: int = 2, exclude_none: bool = False) -> str:
        """Deterministically serialize model to JSON string."""
        data = self.to_dict(exclude_none=exclude_none)
        return json.dumps(data, indent=indent, sort_keys=True, default=str)

    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        """Validate and construct model from dictionary across Pydantic v1 and v2."""
        if hasattr(cls, "model_validate"):
            return cls.model_validate(data)  # type: ignore[attr-defined]
        return cls.parse_obj(data)
