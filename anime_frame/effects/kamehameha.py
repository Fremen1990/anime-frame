"""Cup at your side to charge; push toward the camera to fire."""

from __future__ import annotations

from anime_frame.attack import AttackEffect
from anime_frame.effects.base import FrameContext
from anime_frame.pose import kamehameha_pose


class Kamehameha(AttackEffect):
    id = "kamehameha"
    title = "Kamehameha"
    hint = "Cup hands at your side, then push forward"
    order = 3
    core_color = (255, 245, 165)
    charge_sound = "kamehameha_charge"
    release_sound = "kamehameha_release"

    def pose_ok(self, ctx: FrameContext) -> bool:
        return kamehameha_pose(ctx.hands, ctx.pose_landmarks, ctx.pose_confidence)
