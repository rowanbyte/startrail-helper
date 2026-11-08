"""Find the game's F 挑战 prompt by the button's icon and text, not scenery."""

from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image


ASSETS = Path(__file__).resolve().parent / "assets"
TEMPLATES = tuple(
    np.asarray(Image.open(ASSETS / name).convert("L"))[::3, ::3].astype(np.int16)
    for name in ("challenge_prompt.png", "challenge_prompt_current.png")
)
SEARCH_LEFT, SEARCH_TOP = 600, 400


def challenge_prompt(image: Image.Image) -> tuple[int, int] | None:
    """Return the prompt's tap point, or None when no real prompt is visible."""
    area = np.asarray(image.convert("L"))[SEARCH_TOP:850:3, SEARCH_LEFT:1850:3].astype(np.int16)
    for template in TEMPLATES:
        windows = sliding_window_view(area, template.shape)
        scores = np.mean(np.abs(windows - template), axis=(-2, -1))
        iy, ix = np.unravel_index(np.argmin(scores), scores.shape)
        # Match the fixed button and the dark 挑战 glyphs together, including
        # the wider prompt placement used by some flower challenges.
        candidate = windows[iy, ix]
        glyph_difference = np.mean((candidate[:, 15:] < 115) != (template[:, 15:] < 115))
        if scores[iy, ix] < 25 and glyph_difference < 0.10:
            return SEARCH_LEFT + int(ix) * 3 + 80, SEARCH_TOP + int(iy) * 3 + 19
    return None
