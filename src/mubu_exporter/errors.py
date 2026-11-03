"""Explicit failures shared by the exporter."""

class ExportError(ValueError):
    """Input or operation cannot be completed without losing integrity."""
