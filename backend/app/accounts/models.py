"""Models returned by the protected account API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


AccountRole = Literal["free", "premium", "system_admin", "data_engineer"]
AccountStatus = Literal[
    "pending_verification",
    "active",
    "suspended",
    "deactivated",
]


class AccountModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UsageAllowance(AccountModel):
    user_id: str = Field(min_length=1)
    tier: Literal["free", "premium"]
    period_type: Literal["daily", "monthly"]
    period_start: datetime
    period_end: datetime
    submission_limit: int = Field(ge=0)
    successful_submissions: int = Field(ge=0)
    remaining_submissions: int = Field(ge=0)
    reset_at: datetime
    updated_at: datetime


class UserProfile(AccountModel):
    uid: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3)
    email_verified: bool
    role: AccountRole
    account_status: AccountStatus
    profile: dict[str, Any] = Field(default_factory=dict)
    storage_used_bytes: int = Field(ge=0)
    storage_quota_bytes: int = Field(ge=0)
    last_login_at: datetime | None = None
    allowance: UsageAllowance | None = None
    created_at: datetime
    updated_at: datetime


class ProfileUpdateRequest(AccountModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def normalise_name(cls, value: str) -> str:
        normalised = " ".join(value.split())
        if not normalised:
            raise ValueError("Name cannot be empty.")
        return normalised
