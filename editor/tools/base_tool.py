# -*- coding: utf-8 -*-
from PySide6.QtCore import QPointF


class BaseTool:
    """Base class for canvas tools."""

    def __init__(self, canvas):
        self.canvas = canvas

    def press(self, pos: QPointF):
        """Handle mouse press at scene position."""

    def move(self, pos: QPointF):
        """Handle mouse move while pressing."""

    def release(self, pos: QPointF):
        """Handle mouse release."""