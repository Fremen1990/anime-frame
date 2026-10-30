"""Temporal visual checks: movement, continuity, head alignment and stale masks."""
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from anime_frame.effects.base import FrameContext
from anime_frame.effects.super_saiyan import HairTreatment, SuperSaiyan, golden_hair
from anime_frame.hair_geometry import head_anchor, head_bounds, warp_mask
from anime_frame.vfx import silhouette_aura


def fixture():
    frame = np.full((220, 320, 3), (35, 55, 75), np.uint8)
    # Distinct strands: output variation proves texture is carried upward.
    for x in range(120, 181):
        frame[36:74, x] = (15 + x % 8 * 5, 20 + x % 8 * 5, 25 + x % 8 * 5)
    mask = np.zeros(frame.shape[:2], np.float32)
    mask[36:74, 120:181] = 1
    face = np.zeros((478, 2), np.float64)
    face[10], face[152] = (150, 80), (150, 180)
    return frame, mask, face


def ctx(frame, mask, face, now, stamp=0.0, reference=None):
    return FrameContext(frame, None, None, now, face=face, landmarks_at=now, hair_mask=mask, hair_mask_at=stamp, hair_reference_anchor=reference)


class TemporalTests(unittest.TestCase):
    def test_flames_have_no_jump_at_old_random_seed_boundary(self):
        frame = np.full((240, 320, 3), 40, np.uint8)
        mask = np.zeros(frame.shape[:2], np.float32)
        cv2.ellipse(mask, (160, 170), (60, 120), 0, 0, 360, 1, -1)
        deltas = []
        for start in (1.12, 1.13, 1.14, 1.15, 1.16):
            a = silhouette_aura(frame, mask, start, 1)
            b = silhouette_aura(frame, mask, start+0.01, 1)
            deltas.append(float(np.abs(a.astype(float)-b).mean()))
        self.assertLess(max(deltas), 0.25)
        self.assertLess(max(deltas), min(deltas)*3)

    def test_gold_follows_the_real_hair_and_keeps_its_texture(self):
        frame, mask, face = fixture()
        output = golden_hair(frame, mask, face, 1)
        np.testing.assert_array_equal(output[80:], frame[80:])
        np.testing.assert_array_equal(output[:30], frame[:30])
        changed = np.max(np.abs(output.astype(float)-frame), axis=2)
        self.assertGreater(float(changed[40:70, 125:175].mean()), 3)
        self.assertGreater(float(output[50, 125:175, 2].std()), 3)

    def test_reference_mask_moves_and_rotates_with_current_head(self):
        frame, mask, face = fixture()
        original = head_anchor(face)
        angle = np.deg2rad(15)
        rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        moved = face.copy()
        moved[[10, 152]] = (face[[10, 152]]-face[10]) @ rotation.T + face[10] + (35, 0)
        target = head_anchor(moved)
        bounds = head_bounds(target, frame.shape)
        shifted = warp_mask(mask, original, (0, 0), target, bounds)
        ys, xs = np.where(shifted > 0.8)
        center = (float(xs.mean()+bounds[0]), float(ys.mean()+bounds[1]))
        expected = (np.array((150, 54.5))-face[10]) @ rotation.T + face[10] + (35, 0)
        np.testing.assert_allclose(center, expected, atol=2)

    def test_prior_mask_is_aligned_before_blending_not_left_as_a_trail(self):
        frame, mask, face = fixture()
        treatment = HairTreatment()
        original = head_anchor(face)
        treatment.apply(frame, ctx(frame, mask, face, 0, reference=original), 1)
        moved_face = face + (50, 0)
        moved_mask = np.roll(mask, 50, axis=1)
        treatment.apply(frame, ctx(frame, moved_mask, moved_face, 0.1, stamp=0.1, reference=head_anchor(moved_face)), 1)
        ys, xs = np.where(treatment.mask > 0.8)
        self.assertAlmostEqual(float(xs.mean()+treatment.origin[0]), 200, delta=1)

    def test_stale_hair_fades_by_250ms_and_recovers_gradually(self):
        frame, mask, face = fixture()
        treatment = HairTreatment()
        reference = head_anchor(face)
        treatment.apply(frame, ctx(frame, mask, face, 0, reference=reference), 1)
        fresh = treatment.apply(frame, ctx(frame, mask, face, 0.14, reference=reference), 1)
        fading = treatment.apply(frame, ctx(frame, mask, face, 0.20, reference=reference), 1)
        stale = treatment.apply(frame, ctx(frame, mask, face, 0.25, reference=reference), 1)
        self.assertGreater(np.abs(fresh.astype(float)-frame).sum(), np.abs(fading.astype(float)-frame).sum())
        np.testing.assert_array_equal(stale, frame)
        recovered = treatment.apply(frame, ctx(frame, mask, face, 0.26, stamp=0.26, reference=reference), 1)
        self.assertLess(np.abs(recovered.astype(float)-frame).sum(), np.abs(fresh.astype(float)-frame).sum()*0.2)

    def test_face_loss_clears_hair_cache_without_disabling_aura(self):
        frame, mask, face = fixture()
        treatment = HairTreatment()
        treatment.apply(frame, ctx(frame, mask, face, 0), 1)
        missing = ctx(frame, mask, None, 0.1)
        np.testing.assert_array_equal(treatment.apply(frame, missing, 1), frame)
        self.assertIsNone(treatment.mask)
        with patch('anime_frame.audio.start_cue'), patch('anime_frame.audio.fade_stop'), patch('anime_frame.audio.playback_snapshot', return_value=None):
            effect = SuperSaiyan()
            current = ctx(frame, None, None, 0); current.keys = {'return'}; current.mask = np.zeros(frame.shape[:2], np.float32)
            current.mask[40:200, 100:210] = 1
            effect.update(current)
            current.time=2; current.keys=set(); current.landmarks_at=2
            self.assertFalse(np.array_equal(effect.update(current), frame))
