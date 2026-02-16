"""Pydantic validators for EPMPulse API requests."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
import re


VALID_STATUSES = {"Blank", "Loading", "OK", "Warning"}
VALID_APPS = {"Planning", "FCCS", "ARCS"}


class StatusUpdateRequest(BaseModel):
    """Request model for single status update."""
    app: str = Field(..., description="Application name")
    domain: str = Field(default="default", description="Domain within application")
    status: str = Field(..., description="New status value")
    job_id: Optional[str] = Field(None, description="Job correlation ID")
    message: Optional[str] = Field(None, description="Optional status message")
    timestamp: Optional[str] = Field(None, description="Event timestamp (ISO format)")
    
    @field_validator('app')
    @classmethod
    def validate_app(cls, v: str) -> str:
        """Validate app name against allowed values."""
        if v not in VALID_APPS:
            raise ValueError(f"App must be one of: {', '.join(VALID_APPS)}")
        return v
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status value."""
        if v not in VALID_STATUSES:
            raise ValueError(f"Status must be one of: {', '.join(VALID_STATUSES)}")
        return v
    
    @field_validator('message')
    @classmethod
    def validate_message(cls, v: Optional[str]) -> Optional[str]:
        """Validate message length."""
        if v and len(v) > 200:
            raise ValueError("Message must be 200 characters or less")
        return v
    
    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v: Optional[str]) -> Optional[str]:
        """Validate timestamp format."""
        if v:
            try:
                datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                raise ValueError("Timestamp must be ISO 8601 format")
        return v


class BatchStatusUpdateRequest(BaseModel):
    """Request model for batch status updates."""
    updates: List[StatusUpdateRequest] = Field(
        ..., 
        description="List of status updates"
    )
    job_id: Optional[str] = Field(None, description="Correlation ID for batch")
    timestamp: Optional[str] = Field(None, description="Batch timestamp")


class HealthCheckResponse(BaseModel):
    """Response model for health check."""
    status: str
    checks: dict


class SuccessResponse(BaseModel):
    """Standard success response model."""
    success: bool = True
    data: Optional[dict] = None
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response model."""
    success: bool = False
    error: dict
