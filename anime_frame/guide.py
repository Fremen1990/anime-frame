"""Pose cards for the chooser. The preview never draws these."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

GUIDE_STILL = Path(__file__).resolve().parent.parent / "assets" / "instant_transmission_guide.png"
_STILL: np.ndarray | None | bool = False

INK = (236, 236, 236)
MUTED = (168, 176, 186)
CYAN = (235, 230, 210)

GUIDES: dict[str, tuple[str, ...]] = {
    "clear": (
        "Mirrored live video.",
        "Nothing is drawn on the preview.",
        "Click this row, or press 0.",
    ),
    "instant_transmission": (
        "Put your index and middle fingers together.",
        "Keep them straight. Fold the ring finger and pinky.",
        "Hold the tips on your forehead for about a second.",
        "Vertical lines pull you out through that point.",
        "The same pose brings you back.",
        "Return fires it. Escape brings you back.",
    ),
    "super_saiyan": (
        "Clench both fists beside your shoulders.",
        "Hold for about a second to power up.",
        "Gold hair, flames, and lightning stay on.",
        "The opening plays once; only the aura sound repeats.",
        "Repeat the pose or press Escape to turn it off.",
    ),
    "kamehameha": (
        "1. Hands together toward the camera. Hold briefly.",
        "2. Cup them beside either side of your torso.",
        "The blue-white core stays ready until you fire.",
        "3. Push both hands toward the camera again.",
        "Return advances one stage. Escape cancels.",
    ),
    "kikoho": (
        "Hands together at chest height, aimed at the camera.",
        "One gesture fires the complete attack immediately.",
        "The sound and dying glow last about four seconds.",
        "Lower your hands before another attack.",
        "Return fires once. Escape cancels.",
    ),
}


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if cv2.getTextSize(trial, cv2.FONT_HERSHEY_SIMPLEX, 0.46, 1)[0][0] <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _head(image: np.ndarray, center: tuple[int, int], radius: int) -> None:
    cv2.circle(image, center, radius, INK, 2, cv2.LINE_AA)
    cv2.ellipse(image, (center[0], center[1] + radius + 8), (radius + 16, 18), 0, 0, 180, INK, 2, cv2.LINE_AA)


def _draw_clear(image: np.ndarray, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) // 2, y0 + 78
    _head(image, (cx, cy), 34)
    cv2.line(image, (cx, cy + 36), (cx, cy + 110), INK, 2, cv2.LINE_AA)
    cv2.line(image, (cx - 46, cy + 62), (cx + 46, cy + 62), INK, 2, cv2.LINE_AA)


def _draw_transmission(image: np.ndarray, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, _y1 = box
    cx = (x0 + x1) // 2 + 8
    cy = y0 + 150
    for offset in (-92, -76, -60):
        cv2.line(image, (cx + offset, cy - 70), (cx + offset, cy + 80), CYAN, 1, cv2.LINE_AA)
    _head(image, (cx, cy), 36)
    shoulder = (cx + 34, cy + 56)
    elbow = (cx + 78, cy + 6)
    wrist = (cx + 42, cy - 18)
    cv2.line(image, shoulder, elbow, INK, 2, cv2.LINE_AA)
    cv2.line(image, elbow, wrist, INK, 2, cv2.LINE_AA)
    tip = (cx + 8, cy - 40)
    cv2.line(image, wrist, tip, CYAN, 2, cv2.LINE_AA)
    cv2.line(image, (wrist[0] + 6, wrist[1] + 2), (tip[0] + 6, tip[1] + 2), CYAN, 2, cv2.LINE_AA)
    cv2.line(image, (cx - 6, cy - 36), (cx + 22, cy - 36), (255, 255, 255), 2, cv2.LINE_AA)


def _draw_power(image: np.ndarray, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, _ = box
    cx, cy = (x0 + x1) // 2, y0 + 135
    _head(image, (cx, cy), 32)
    cv2.line(image, (cx, cy + 34), (cx, cy + 117), INK, 2, cv2.LINE_AA)
    for side in (-1, 1):
        cv2.line(image, (cx + side * 28, cy + 53), (cx + side * 70, cy + 65), INK, 2, cv2.LINE_AA)
        cv2.line(image, (cx + side * 70, cy + 65), (cx + side * 78, cy + 10), INK, 2, cv2.LINE_AA)
        cv2.circle(image, (cx + side * 78, cy + 10), 10, CYAN, 2, cv2.LINE_AA)
        cv2.line(image, (cx + side * 35, cy - 9), (cx + side * 28, cy - 59), (60, 200, 255), 2, cv2.LINE_AA)
        cv2.ellipse(image, (cx, cy + 45), (85, 132), 0, 15, 165, (60, 200, 255), 2, cv2.LINE_AA)


def _draw_kame(image: np.ndarray, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, _ = box
    step = (x1 - x0) // 3
    cy = y0 + 125
    for index, label in enumerate(("1 START", "2 HOLD", "3 FIRE")):
        cx = x0 + step * index + step // 2
        _head(image, (cx, cy), 16)
        cv2.line(image, (cx, cy + 20), (cx, cy + 90), INK, 2, cv2.LINE_AA)
        hx, hy = (cx + 28, cy + 68) if index == 1 else (cx, cy + 46)
        for side in (-1, 1):
            cv2.line(image, (cx + side * 20, cy + 30), (hx + side * 5, hy), INK, 2, cv2.LINE_AA)
            cv2.circle(image, (hx + side * 5, hy), 7, CYAN, 2, cv2.LINE_AA)
        if index == 1:
            cv2.circle(image, (hx, hy), 17, (255, 235, 155), 1, cv2.LINE_AA)
        else:
            cv2.ellipse(image, (hx, hy), (23, 18), 0, 0, 360, CYAN, 1, cv2.LINE_AA)
        cv2.putText(image, label, (cx - 30, cy + 118), cv2.FONT_HERSHEY_SIMPLEX, 0.35, INK, 1, cv2.LINE_AA)
        if index < 2:
            cv2.arrowedLine(image, (cx + 30, cy - 40), (cx + step - 30, cy - 40), CYAN, 1, cv2.LINE_AA, tipLength=0.3)


def _draw_kiko(image: np.ndarray, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, _ = box
    cx, cy = (x0 + x1) // 2, y0 + 135
    _head(image, (cx, cy), 32)
    cv2.line(image, (cx, cy + 34), (cx, cy + 125), INK, 2, cv2.LINE_AA)
    cv2.line(image, (cx - 34, cy + 56), (cx - 10, cy + 92), INK, 2, cv2.LINE_AA)
    cv2.line(image, (cx + 34, cy + 56), (cx + 10, cy + 92), INK, 2, cv2.LINE_AA)
    for radius in (12, 26, 42):
        cv2.rectangle(image, (cx - radius, cy + 96 - radius), (cx + radius, cy + 96 + radius), (70, 200, 255), 1, cv2.LINE_AA)


DRAW = {
    "clear": _draw_clear,
    "instant_transmission": _draw_transmission,
    "super_saiyan": _draw_power,
    "kamehameha": _draw_kame,
    "kikoho": _draw_kiko,
}


def transmission_still() -> np.ndarray | None:
    """The local Goku still. Missing file falls back to the line drawing."""
    global _STILL
    if _STILL is False:
        image = cv2.imread(str(GUIDE_STILL), cv2.IMREAD_COLOR) if GUIDE_STILL.is_file() else None
        _STILL = image if image is not None and image.size else None
    return _STILL


def _fit(canvas: np.ndarray, photo: np.ndarray, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    photo_height, photo_width = photo.shape[:2]
    scale = min(width / photo_width, height / photo_height)
    fitted_width = max(1, int(photo_width * scale))
    fitted_height = max(1, int(photo_height * scale))
    resized = cv2.resize(photo, (fitted_width, fitted_height), interpolation=cv2.INTER_AREA)
    left = x0 + (width - fitted_width) // 2
    top = y0 + (height - fitted_height) // 2
    canvas[top : top + fitted_height, left : left + fitted_width] = resized


def draw_countdown(image: np.ndarray, box: tuple[int, int, int, int], seconds: int) -> None:
    x0, y0, x1, y1 = box
    cv2.rectangle(image, (x0, y0), (x1, y1), (46, 46, 52), -1)
    cv2.rectangle(image, (x0, y0), (x1, y1), (150, 186, 210), 1, cv2.LINE_AA)
    title = "Step out of the chair"
    title_size = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 1)[0]
    cv2.putText(
        image,
        title,
        ((x0 + x1 - title_size[0]) // 2, y0 + 72),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        INK,
        1,
        cv2.LINE_AA,
    )
    number = str(max(0, seconds))
    number_size = cv2.getTextSize(number, cv2.FONT_HERSHEY_SIMPLEX, 4.4, 6)[0]
    cv2.putText(
        image,
        number,
        ((x0 + x1 - number_size[0]) // 2, (y0 + y1) // 2 + number_size[1] // 3),
        cv2.FONT_HERSHEY_SIMPLEX,
        4.4,
        (245, 245, 245),
        6,
        cv2.LINE_AA,
    )
    note = "Capturing the empty room"
    note_size = cv2.getTextSize(note, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)[0]
    cv2.putText(
        image,
        note,
        ((x0 + x1 - note_size[0]) // 2, y1 - 64),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        MUTED,
        1,
        cv2.LINE_AA,
    )


def draw_card(image: np.ndarray, effect_id: str, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    cv2.rectangle(image, (x0, y0), (x1, y1), (46, 46, 52), -1)
    cv2.rectangle(image, (x0, y0), (x1, y1), (78, 82, 92), 1, cv2.LINE_AA)
    still = transmission_still() if effect_id == "instant_transmission" else None
    if still is not None:
        _fit(image, still, (x0 + 16, y0 + 16, x1 - 16, y0 + 250))
        text_left = x0 + 20
        text_width = x1 - text_left - 20
        y = y0 + 274
    else:
        draw = DRAW.get(effect_id, _draw_clear)
        draw(image, (x0 + 16, y0 + 16, x0 + 250, y1 - 16))
        text_left = x0 + 268
        text_width = x1 - text_left - 18
        y = y0 + 36
    for paragraph in GUIDES.get(effect_id, ()):
        for line in _wrap(paragraph, text_width):
            cv2.putText(
                image,
                line,
                (text_left, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                MUTED,
                1,
                cv2.LINE_AA,
            )
            y += 22
        y += 8
