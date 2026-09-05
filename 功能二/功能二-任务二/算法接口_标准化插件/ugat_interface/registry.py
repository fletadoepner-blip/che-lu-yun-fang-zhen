"""Algorithm registry for selecting UGAT or future algorithms by name."""
from collections.abc import Callable
from typing import Any


class AlgorithmRegistry:
    def __init__(self):
        self._factories: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, factory: Callable[..., Any], *, overwrite: bool = False) -> None:
        key = name.strip().lower()
        if not key:
            raise ValueError("algorithm name cannot be empty")
        if key in self._factories and not overwrite:
            raise KeyError(f"algorithm already registered: {key}")
        self._factories[key] = factory

    def create(self, name: str, **kwargs: Any) -> Any:
        try:
            return self._factories[name.strip().lower()](**kwargs)
        except KeyError as exc:
            raise KeyError(f"unknown algorithm {name!r}; available={sorted(self._factories)}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


registry = AlgorithmRegistry()
