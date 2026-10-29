"""Load every effect module and return instances in menu order."""

from __future__ import annotations

import importlib
from pathlib import Path

from anime_frame.effects.base import Effect


def load_effects() -> list[Effect]:
    package = Path(__file__).resolve().parent / "effects"
    effects: list[Effect] = []
    for path in sorted(package.glob("*.py")):
        if path.name.startswith("_") or path.name == "base.py":
            continue
        module = importlib.import_module(f"anime_frame.effects.{path.stem}")
        for obj in vars(module).values():
            if not isinstance(obj, type) or not issubclass(obj, Effect):
                continue
            if obj is Effect or obj.__module__ != module.__name__:
                continue
            effects.append(obj())
    effects.sort(key=lambda effect: (effect.order, effect.title))
    return effects
