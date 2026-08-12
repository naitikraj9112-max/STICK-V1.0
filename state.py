"""Presentation state factory — content lifecycle is owned per session."""

from presentation_cover import create_cover_scene
from session import new_presentation_state

__all__ = ["new_presentation_state", "create_cover_scene"]
