from __future__ import annotations
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Any
from .fingerprint import Fingerprint, fingerprint


class FrozenDict(dict):
    """JSON-compatible dictionary that cannot be changed after publication."""

    def _immutable(self, *args: object, **kwargs: object) -> None:
        raise TypeError("published artifact values are immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _immutable

    def __deepcopy__(self, memo: dict[int, object]) -> "FrozenDict":
        return self


class FrozenList(list):
    """JSON-compatible list that cannot be changed after publication."""

    def _immutable(self, *args: object, **kwargs: object) -> None:
        raise TypeError("published artifact values are immutable")

    __setitem__ = __delitem__ = append = clear = extend = insert = pop = remove = reverse = sort = __iadd__ = __imul__ = _immutable

    def __deepcopy__(self, memo: dict[int, object]) -> "FrozenList":
        return self


def _freeze(value: Any) -> Any:
    if isinstance(value, FrozenDict | FrozenList):
        return value
    if isinstance(value, Mapping):
        return FrozenDict((key, _freeze(item)) for key, item in value.items())
    if isinstance(value, list):
        return FrozenList(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze(item) for item in value)
    return value


def freeze_value(value: Any) -> Any:
    """Return a recursively immutable, JSON-compatible public snapshot."""
    return _freeze(value)

@dataclass(frozen=True, slots=True)
class StageArtifact:
    kind: str
    schema_version: str
    conversion_id: str
    parent_fingerprint: Fingerprint|None
    payload: Mapping[str,Any]
    artifact_fingerprint: Fingerprint

    def __post_init__(self) -> None:
        if not all(isinstance(item, str) and item for item in (self.kind, self.schema_version, self.conversion_id)):
            raise ValueError("artifact identity fields must be non-empty strings")
        if not isinstance(self.payload, Mapping):
            raise TypeError("artifact payload must be a mapping")
        object.__setattr__(self, "payload", MappingProxyType(_freeze(self.payload)))
        if self.kind == "initial":
            if self.parent_fingerprint is not None:
                raise ValueError("initial artifact cannot have a parent")
            expected = fingerprint("stage-artifact", {"kind":"initial","conversion_id":self.conversion_id,"payload":{"stage_order":list(self.payload.get("stage_order",()))}})
        else:
            if self.parent_fingerprint is None:
                raise ValueError("non-initial artifact requires a parent fingerprint")
            serial = {key:list(value) if isinstance(value,tuple) else value for key,value in self.payload.items()}
            expected = fingerprint("stage-artifact", {"kind":self.kind,"conversion_id":self.conversion_id,"parent":self.parent_fingerprint.value,"payload":serial})
        if expected != self.artifact_fingerprint:
            raise ValueError("artifact fingerprint does not match immutable payload")

    @classmethod
    def initial(cls, conversion_id:str)->"StageArtifact":
        payload={"stage_order":()}
        return cls("initial","0.1",conversion_id,None,payload,fingerprint("stage-artifact",{"kind":"initial","conversion_id":conversion_id,"payload":{"stage_order":[]}}))
