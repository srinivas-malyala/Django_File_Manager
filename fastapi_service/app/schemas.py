"""Validated request and response schemas."""

from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=150, pattern=r"^[\w.@+-]+$")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("A valid email address is required.")
        return normalized


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class FileUpdateRequest(BaseModel):
    description: str | None = Field(default=None, max_length=10_000)
    model_config = ConfigDict(extra="forbid")


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class FileResponse(BaseModel):
    id: str
    original_filename: str
    file_size: int
    file_type: str
    mime_type: str
    description: str | None
    upload_date: datetime
    model_config = ConfigDict(from_attributes=True)


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_in: int
