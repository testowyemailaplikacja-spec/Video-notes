"""Predictable user-facing failures. Never include private transcripts in errors."""


class VideoNotesError(Exception):
    """A local processing or data-validation error."""
