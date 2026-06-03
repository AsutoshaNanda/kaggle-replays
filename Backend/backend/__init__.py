"""Kaggle Replay Analytics — FastAPI backend package.

Wraps the Phase 1 async Playwright downloader (``downloader.py`` at the project
root) in a production-grade REST API with MySQL persistence, JWT authentication,
WebSocket progress streaming, and a comprehensive security layer.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
