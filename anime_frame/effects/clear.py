"""Live mirrored video with nothing drawn on it."""

from __future__ import annotations

from anime_frame.effects.base import Effect, FrameContext


class Clear(Effect):
    id = "clear"
    title = "Clear"
    hint = "Mirrored live video"
    order = 0
    replaces_person = False

    def reset(self) -> None:
        return None

    def update(self, ctx: FrameContext):
        return ctx.frame
