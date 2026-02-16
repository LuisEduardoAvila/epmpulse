# EPMPulse - EPM Job Status Dashboard
""" EPMPulse: EPM Job Status Dashboard.

This module provides real-time EPM job status updates to Slack Canvas.

Core Components:
- State Management: JSON file with atomic writes and file locking
- API Layer: Flask REST API with Pydantic validation
- Slack Integration: Canvas update with debouncing and retry logic
"""
