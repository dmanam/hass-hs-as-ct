from __future__ import annotations

from homeassistant.util.color import color_hs_to_xy, color_xy_to_temperature

def color_hs_to_temperature(h: float, s: float) -> float:
    """Convert an hs color to a color temperature in Kelvin."""
    return color_xy_to_temperature(*color_hs_to_xy(h, s))
