"""Forward to start, cup at the side to hold, forward again to fire."""

from __future__ import annotations

from anime_frame.attack import AttackEffect
from anime_frame.effects.base import FrameContext
from anime_frame.pose import kamehameha_pose


class Kamehameha(AttackEffect):
    id = "kamehameha"
    title = "Kamehameha"
    hint = "Forward, cup at your side, then forward to fire"
    order = 3
    core_color = (255, 245, 165)
    charge_sound = "kamehameha_charge"
    release_sound = "kamehameha_release"

    def pose_ok(self, ctx: FrameContext) -> bool:
        return kamehameha_pose(ctx.hands, ctx.pose_landmarks, ctx.pose_confidence)
