"""Authenticated identity supplied by a verified Firebase ID token."""

from pydantic import BaseModel, ConfigDict, Field


class AuthenticatedUser(BaseModel):
    """Trusted identity claims extracted by the Firebase Admin SDK."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    uid: str = Field(min_length=1)
    email: str = Field(min_length=3)
    email_verified: bool = False
