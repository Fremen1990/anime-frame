"""Synthetic pose, timing, and image checks for the signature moves."""

from __future__ import annotations

import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from anime_frame.app import CHOOSER_HEIGHT, ROW_HEIGHT, ROW_TOP, App, put_label, render_chooser, row_at
from anime_frame.effects.base import FrameContext
from anime_frame.effects.kamehameha import Kamehameha
from anime_frame.effects.kikoho import Kikoho
from anime_frame.effects.super_saiyan import SuperSaiyan, golden_hair
from anime_frame.hair import HairTracker
from anime_frame.pose import (
    PoseWindow, aimed_at_camera, forward_baseline, kamehameha_pose, kikoho_pose,
    pushed_forward, super_saiyan_pose,
)
from anime_frame.registry import load_effects
from anime_frame.vfx import camera_blast, charge_core, horizontal_beam, silhouette_aura, square_blast


def _body(wrists: tuple[tuple[float, float], tuple[float, float]]) -> np.ndarray:
    body = np.zeros((33, 2), np.float64)
    body[11], body[12] = (80, 100), (160, 100)
    body[13], body[14] = (70, 130), (170, 130)
    body[15], body[16] = wrists
    body[23], body[24] = (95, 245), (145, 245)
    return body


def _hand(wrist: tuple[float, float], cup: bool = False) -> np.ndarray:
    hand = np.zeros((21, 2), np.float64)
    hand[0] = (0, 0)
    for base, pip, tip in ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)):
        x = (base - 7) * 1.5
        hand[base] = (x, -12)
        hand[pip] = (x, -21)
        hand[tip] = (x + 1, -11)
    hand[4] = (3, -8)
    if cup:
        hand[8] = (-7, -27)
        hand[4] = (-2, -20)
    return hand + np.asarray(wrist)


def _world(pushed: bool = False, lean: float = 0.0, further: bool = False) -> np.ndarray:
    world = np.zeros((33, 3), np.float64)
    for side, shoulder, elbow, wrist in ((-1, 11, 13, 15), (1, 12, 14, 16)):
        world[shoulder] = (side * 0.25, 0.0, 0.0)
        world[elbow] = (side * 0.25, -0.2, -0.05)
        world[wrist] = (side * 0.1, -0.05, 0.15)
        if pushed:
            world[wrist] = (side * 0.25, -0.4, -0.25)
        if further:
            world[elbow] = (side * 0.25, 0.0, -0.2)
            world[wrist] = (side * 0.25, 0.0, -0.55)
    world[:, 2] += lean
    return world


def _context(now: float, world=None, observation: int | None = None, keys=()) -> FrameContext:
    return FrameContext(
        frame=np.full((240, 320, 3), 40, np.uint8), mask=np.ones((240, 320), np.float32),
        background=None, time=now, pose_world_landmarks=world, landmarks_at=now,
        landmark_timestamp_ms=observation, keys=set(keys),
    )


class PoseTests(unittest.TestCase):
    def test_three_poses_stay_distinct(self) -> None:
        power_body = _body(((37, 97), (203, 98)))
        power_hands = [_hand((37, 97)), _hand((203, 98))]
        self.assertTrue(super_saiyan_pose(power_hands[::-1], power_body))
        self.assertFalse(super_saiyan_pose(power_hands[:1], power_body))
        self.assertFalse(kamehameha_pose(power_hands, power_body))
        self.assertFalse(kikoho_pose(power_hands, power_body))

        beam_body = _body(((155, 145), (175, 145)))
        beam_hands = [_hand((155, 145), True), _hand((175, 145), True)]
        self.assertTrue(kamehameha_pose(beam_hands[::-1], beam_body))
        self.assertTrue(kamehameha_pose(beam_hands[:1], beam_body))
        self.assertFalse(kikoho_pose(beam_hands, beam_body))

        square_body = _body(((100, 145), (140, 145)))
        square_hands = [_hand((100, 145)), _hand((140, 145))]
        self.assertTrue(kikoho_pose(square_hands[::-1], square_body))
        self.assertTrue(kikoho_pose(square_hands[:1], square_body))
        self.assertTrue(kikoho_pose([], square_body))
        self.assertFalse(kamehameha_pose([], square_body))
        self.assertFalse(kikoho_pose(square_hands, _body(((30, 145), (210, 145)))))

    def test_pose_scale_mirror_and_tracking_confidence(self) -> None:
        body = _body(((155, 145), (175, 145)))
        hands = [_hand((155, 145), True), _hand((175, 145), True)]
        self.assertTrue(kamehameha_pose([hand * (-1.7, 1.7) for hand in hands], body * (-1.7, 1.7)))
        confidence = np.ones(33)
        confidence[15] = 0.2
        self.assertFalse(kamehameha_pose(hands, body, confidence))

    def test_push_uses_wrist_motion_relative_to_shoulders(self) -> None:
        baseline = forward_baseline(_world())
        self.assertIsNotNone(baseline)
        self.assertTrue(pushed_forward(baseline, _world(pushed=True)))
        self.assertFalse(pushed_forward(baseline, _world(lean=-0.35)))
        self.assertTrue(aimed_at_camera(_world(pushed=True)))
        self.assertFalse(aimed_at_camera(_world()))
        self.assertFalse(aimed_at_camera(_world(lean=-0.35)))

    def test_pose_window_does_not_count_one_observation_eight_times(self) -> None:
        window = PoseWindow()
        for index in range(12):
            window.update(True, index * 0.1, observation_id=7)
        self.assertEqual(window.true_count, 1)
        self.assertFalse(window.fired)


class AttackTests(unittest.TestCase):
    def setUp(self):
        self.play = patch("anime_frame.audio.play").start()
        self.loop = patch("anime_frame.audio.loop").start()
        self.stop = patch("anime_frame.audio.stop").start()
        self.start_audio = patch("anime_frame.audio.start_cue", return_value=123).start()
        self.release_audio = patch("anime_frame.audio.release_cue").start()
        self.fade_audio = patch("anime_frame.audio.fade_stop").start()
        patch("anime_frame.audio.playback_snapshot", return_value=None).start()
        self.addCleanup(patch.stopall)

    def context(self, now, stage="front", observation=None, keys=()):
        front = stage == "front"
        ctx = _context(now, _world(pushed=front), observation, keys)
        wrists = ((100, 145), (140, 145)) if front else ((155, 145), (175, 145))
        ctx.pose_landmarks = _body(wrists)
        ctx.hands = [_hand(wrist, True) for wrist in wrists]
        return ctx

    def start(self):
        effect = Kamehameha()
        for index in range(4):
            effect.update(self.context(index/10, "side"))
        self.assertEqual(effect.phase, "charging")
        return effect

    def ready(self):
        effect = self.start()
        for index in range(4, 12):
            effect.update(self.context(index/10, "side"))
        self.assertEqual(effect.phase, "ready")
        return effect

    def test_two_physical_stages_start_one_cue_then_release_it(self):
        effect = self.ready()
        self.start_audio.assert_called_once_with("kamehameha")
        self.loop.assert_not_called(); self.play.assert_not_called()
        effect.update(self.context(1.2)); self.assertEqual(effect.phase, "ready")
        effect.update(self.context(1.3)); self.assertEqual(effect.phase, "firing")
        self.release_audio.assert_called_once_with(123)
        effect.update(self.context(3)); self.assertEqual(effect.phase, "fading")
        effect.update(self.context(7.01)); self.assertEqual(effect.phase, "idle")

    def test_forward_pose_cannot_start_or_skip_side_confirmation(self):
        effect = Kamehameha()
        for index in range(15): effect.update(self.context(index/10))
        self.assertEqual(effect.phase, "idle")
        self.start_audio.assert_not_called()
        for index in range(15, 18): effect.update(self.context(index/10, "side"))
        self.assertEqual(effect.phase, "idle")

    def test_early_push_cancels_and_is_never_queued(self):
        effect = self.start()
        effect.update(self.context(0.4))
        self.assertEqual(effect.phase, "cancelling")
        for index in range(6, 20): effect.update(self.context(index/10))
        self.assertEqual(effect.phase, "idle")
        self.release_audio.assert_not_called()

    def test_full_sequence_mirrored_scaled_swapped_and_one_hidden_mesh(self):
        for scale in (0.6, 1.7):
            for direction in (-1, 1):
                effect = Kamehameha()
                for index, stage in enumerate(["side"]*12+["front"]*2):
                    ctx = self.context(index/10, stage)
                    ctx.pose_landmarks *= (scale*direction, scale)
                    ctx.hands = [hand*(scale*direction, scale) for hand in ctx.hands[::-1]][:1]
                    ctx.pose_world_landmarks[:, 0] *= direction
                    effect.update(ctx)
                self.assertEqual(effect.phase, "firing")

    def test_ready_waits_indefinitely_but_lean_one_hand_and_jitter_do_not_fire(self):
        effect = self.ready()
        for index in range(12, 100): effect.update(self.context(index/10, "side"))
        self.assertEqual(effect.phase, "ready")
        for index in range(100, 104):
            ctx = self.context(index/10); ctx.pose_world_landmarks = _world(lean=-0.4)
            effect.update(ctx)
        for index in range(104, 108):
            ctx = self.context(index/10); ctx.pose_world_landmarks[16] = _world()[16]
            effect.update(ctx)
        for index in range(108, 114): effect.update(self.context(index/10, "front" if index%2 else "side"))
        self.assertEqual(effect.phase, "ready")

    def test_stale_missing_repeated_or_invalid_depth_cancels_charging_and_ready(self):
        for make in (self.start, self.ready):
            for kind in ("stale", "missing", "repeated", "low_confidence", "nan"):
                effect = make(); last = float(effect.last_motion_observation)
                ctx = self.context(last+0.31)
                if kind == "stale": ctx.landmarks_at = last
                elif kind == "missing": ctx.pose_world_landmarks = None
                elif kind == "repeated": ctx.landmark_timestamp_ms = last
                elif kind == "low_confidence":
                    ctx.pose_confidence = np.ones(33); ctx.pose_confidence[13] = 0.1
                else: ctx.pose_world_landmarks[14, 2] = np.nan
                effect.update(ctx)
                self.assertEqual(effect.phase, "cancelling", kind)
                effect.update(_context(last+0.45))
                self.assertEqual(effect.phase, "idle")

    def test_keyboard_two_presses_no_tracking_no_auto_fire(self):
        effect = Kamehameha()
        effect.update(_context(0, keys={"return"}))
        effect.update(_context(0.1, keys={"return"}))
        self.assertEqual(effect.phase, "charging")
        effect.update(_context(0.71)); self.assertEqual(effect.phase, "ready")
        effect.update(_context(60)); self.assertEqual(effect.phase, "ready")
        effect.update(_context(60.1, keys={"return"})); self.assertEqual(effect.phase, "firing")
        effect.update(_context(60.2, keys={"return"})); self.release_audio.assert_called_once()

    def test_completed_blast_requires_release_before_recharging(self):
        effect = self.ready()
        effect.update(self.context(1.2)); effect.update(self.context(1.3))
        effect.update(self.context(7.1, "side"))
        for index in range(72, 82): effect.update(self.context(index/10, "side"))
        self.assertEqual(effect.phase, "idle")
        effect.update(self.context(8.2))
        for index in range(83, 87): effect.update(self.context(index/10, "side"))
        self.assertEqual(effect.phase, "charging")

    def test_release_starts_with_identical_orb_without_contraction(self):
        effect = Kamehameha()
        effect.update(_context(0, keys={"return"})); effect.update(_context(1))
        before = effect.update(_context(1.1))
        after = effect.update(_context(1.1, keys={"return"}))
        np.testing.assert_array_equal(before, after)

    def test_render_anchor_moves_between_tracking_samples_with_bounded_prediction(self):
        from anime_frame.attack import MotionAnchor
        anchor = MotionAnchor()
        first = self.context(0, "side", 0); anchor.update(first)
        moved = self.context(0.1, "side", 1); moved.pose_landmarks[:, 0] += 80
        point1, _ = anchor.update(moved)
        moved.time = 0.12
        point2, _ = anchor.update(moved)
        self.assertGreater(point2[0], point1[0])
        self.assertLess(point2[0], 265)

    def test_escape_and_shutdown_cancel_all_stages(self):
        for phase in ("charging", "ready", "firing", "fading"):
            effect = self.ready(); effect.phase = phase
            ctx = _context(1.2, keys={"escape"})
            np.testing.assert_array_equal(effect.update(ctx), ctx.frame)
            self.assertEqual(effect.phase, "idle")
            self.fade_audio.assert_called_with(123, 0.02)
        app = App(); app.active = effect
        with patch("anime_frame.audio.shutdown") as shutdown, patch("anime_frame.app.cv2.destroyAllWindows"):
            app.close(); shutdown.assert_called_once()

    def test_saiyan_opening_once_and_deactivation_fades(self):
        effect = SuperSaiyan()
        effect.update(_context(0, keys={"return"}))
        for now in (0.7, 1.7, 5.8, 60): effect.update(_context(now))
        self.assertEqual(effect.phase, "active")
        self.start_audio.assert_called_once_with("super_saiyan")
        effect.update(_context(60.1, keys={"escape"}))
        self.fade_audio.assert_called_with(123, 0.4)
        effect.update(_context(60.51)); self.assertEqual(effect.phase, "idle")

    def test_status_is_confined_to_chooser(self):
        effect = Kamehameha(); ctx = _context(0)
        np.testing.assert_array_equal(effect.update(ctx), ctx.frame)
        self.assertIn("Cup hands", effect.status)
        effect.update(_context(0.1, keys={"return"})); effect.update(_context(1))
        self.assertIn("Push both", effect.status)

    def test_kikoho_fires_once_without_charging_and_runs_for_whole_clip(self) -> None:
        effect = Kikoho()
        for now in (0, 0.1, 0.2):
            effect.update(self.context(now))
        self.assertEqual(effect.phase, "firing")
        self.play.assert_called_once_with("kikoho_release")
        self.loop.assert_not_called()
        for now in (0.3, 1, 2, 4.1):
            effect.update(self.context(now, keys={"return"}))
            self.assertEqual(effect.phase, "firing")
        self.play.assert_called_once()
        out = effect.update(self.context(4.224))
        self.assertEqual(effect.phase, "idle")
        np.testing.assert_array_equal(out, self.context(4.224).frame)
        for index in range(43, 50):
            effect.update(self.context(index / 10))
        self.assertEqual(effect.phase, "idle")
        effect.update(self.context(5.0, "side"))
        for now in (5.1, 5.2, 5.3):
            effect.update(self.context(now))
        self.assertEqual(effect.phase, "firing")
        self.assertEqual(self.play.call_count, 2)

    def test_kikoho_rejects_nonforward_stale_or_replayed_pose(self) -> None:
        for kind in ("not_forward", "stale", "repeated"):
            effect = Kikoho()
            for index in range(10):
                ctx = self.context(index / 10)
                if kind == "not_forward":
                    ctx.pose_world_landmarks = _world()
                elif kind == "stale":
                    ctx.landmarks_at = -1.0
                else:
                    ctx.landmark_timestamp_ms = 123
                effect.update(ctx)
            self.assertEqual(effect.phase, "idle")

    def test_kikoho_one_return_and_escape_during_playback(self) -> None:
        effect = Kikoho()
        effect.update(_context(0, keys={"return"}))
        self.assertEqual(effect.phase, "firing")
        out = effect.update(_context(0.1, keys={"escape"}))
        self.assertEqual(effect.phase, "idle")
        np.testing.assert_array_equal(out, _context(0.1).frame)
        self.stop.assert_any_call("kikoho_release")



class RenderingAndLifecycleTests(unittest.TestCase):
    def test_gold_stays_in_hair_and_face_remains_unchanged(self) -> None:
        frame = np.full((120, 120, 3), (25, 50, 80), np.uint8)
        mask = np.zeros((120, 120), np.float32)
        mask[12:35, 48:73] = 1
        face = np.zeros((478, 2), np.float64)
        face[10], face[152] = (60, 40), (60, 90)
        output = golden_hair(frame, mask, face, 1)
        self.assertFalse(np.array_equal(output[20, 60], frame[20, 60]))
        np.testing.assert_array_equal(output[70, 60], frame[70, 60])
        np.testing.assert_array_equal(output[100, 10], frame[100, 10])
        np.testing.assert_array_equal(output[7, 60], frame[7, 60])

    def test_light_falls_off_instead_of_painting_a_hard_shape(self) -> None:
        frame = np.full((240, 240, 3), (18, 24, 32), np.uint8)
        mask = np.zeros((240, 240), np.float32)
        mask[80:170, 80:170] = 1
        aura = silhouette_aura(frame, mask, 1.2, 1.0)
        np.testing.assert_array_equal(aura[125, 125], frame[125, 125])
        self.assertGreater(int(aura[68, 125].sum()), int(aura[4, 125].sum()))
        self.assertGreater(int(aura[68, 125].sum()), int(frame[68, 125].sum()))

        beam = horizontal_beam(frame, (40.0, 120.0), 1, 1.0, 1.0, 48.0)
        self.assertGreater(int(beam[120, 140].sum()), int(beam[8, 140].sum()))

        blast = square_blast(frame, (120.0, 120.0), 0.35, 1.0, 40.0)
        self.assertGreater(int(blast[120, 120].sum()), int(blast[4, 4].sum()))

        core = charge_core(frame, (120.0, 120.0), 28.0, 1.0, (255, 230, 170))
        self.assertGreater(int(core[120, 120].sum()), int(core[120, 8].sum()))

        frontal = camera_blast(frame, (120.0, 120.0), 0.9, 1.0, (255, 245, 165))
        self.assertGreater(int(frontal[120, 120].sum()), 600)
        self.assertGreater(int(frontal[120, 120].sum()), int(frontal[2, 2].sum()))
        later = silhouette_aura(frame, mask, 1.7, 1.0)
        self.assertFalse(np.array_equal(aura, later))

    def test_chooser_fits_all_rows_and_draws_macrons(self) -> None:
        effects = load_effects()
        for index in range(len(effects) + 1):
            self.assertEqual(row_at(40, ROW_TOP + index * ROW_HEIGHT + 20, len(effects) + 1), index)
        self.assertLess(ROW_TOP + (len(effects) + 1) * ROW_HEIGHT, CHOOSER_HEIGHT)
        self.assertEqual(render_chooser(effects, "kikoho", "").shape[:2], (CHOOSER_HEIGHT, 980))
        plain = np.zeros((45, 200, 3), np.uint8)
        accented = plain.copy()
        put_label(plain, "Kikoho", (3, 33), 0.7, (255, 255, 255))
        put_label(accented, "Kikōhō", (3, 33), 0.7, (255, 255, 255))
        self.assertGreater(int(accented.sum()), int(plain.sum()))

    def test_hair_worker_discards_result_after_reset(self) -> None:
        started, finish = threading.Event(), threading.Event()

        def infer(_tracker, generation, frame, timestamp, now):
            started.set()
            finish.wait(2)
            return generation, now, np.ones(frame.shape[:2], np.float32)

        tracker = HairTracker(Path("unused"))
        self.addCleanup(tracker.close)
        with patch.object(HairTracker, "_infer", infer):
            frame = np.zeros((8, 8, 3), np.uint8)
            tracker.sample(frame, 1, 0.0)
            self.assertTrue(started.wait(2))
            tracker.reset()
            finish.set()
            tracker._future.result(timeout=2)
            mask, _ = tracker.sample(frame, 2, 0.2)
            self.assertIsNone(mask)

    def test_switching_camera_invalidates_room_and_effect_state(self) -> None:
        class FakeCamera:
            def __init__(self, index):
                self.index = index
            def release(self):
                pass
        app = App()
        app.camera = FakeCamera(0)
        app.effects = load_effects()
        app.active = app.effects[2]
        app.active.phase = "active"
        app.background.image = np.ones((2, 2, 3), np.uint8)
        with patch("anime_frame.app.list_camera_names", return_value=["Built-in", "USB"]), patch("anime_frame.app.Camera", FakeCamera), patch.object(app, "_remember_camera"):
            app._switch_camera(1)
        self.assertIsNone(app.background.image)
        self.assertEqual(app.active.phase, "idle")


if __name__ == "__main__":
    unittest.main()
