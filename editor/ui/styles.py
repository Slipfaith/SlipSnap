# -*- coding: utf-8 -*-
from design_tokens import Palette, editor_main_stylesheet


class ModernColors:
    """Compatibility wrapper mapping to the global design palette."""

    # Primary colors
    PRIMARY = Palette.PRIMARY
    PRIMARY_HOVER = Palette.PRIMARY_HOVER
    PRIMARY_LIGHT = Palette.PRIMARY_LIGHT

    # Surface colors
    SURFACE = Palette.SURFACE
    SURFACE_VARIANT = Palette.SURFACE_VARIANT
    SURFACE_HOVER = Palette.SURFACE_HOVER

    # Border colors
    BORDER = Palette.BORDER
    BORDER_FOCUS = Palette.BORDER_FOCUS

    # Text colors
    TEXT_PRIMARY = Palette.TEXT_PRIMARY
    TEXT_SECONDARY = Palette.TEXT_SECONDARY
    TEXT_MUTED = Palette.TEXT_MUTED

    # Status colors
    SUCCESS = Palette.SUCCESS
    WARNING = Palette.WARNING
    ERROR = Palette.ERROR


def main_window_style() -> str:
    """Return the global stylesheet for the editor window."""

    return editor_main_stylesheet()