"""Models returned by the protected account API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.accounts.roles import OperationalRole, stored_operational_roles, stored_account_type


AccountRole = Literal[
    "free",
    "premium",
    "system_admin",
    "data_engineer",
    "staff",
]

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
    account_type: Literal["app", "staff"]
    operational_roles: list[OperationalRole] = Field(default_factory=list, max_length=2)
    account_status: AccountStatus
    profile: dict[str, Any] = Field(default_factory=dict)
    storage_used_bytes: int = Field(ge=0)
    storage_quota_bytes: int = Field(ge=0)
    last_login_at: datetime | None = None
    allowance: UsageAllowance | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def legacy_portal_access(cls, value):
        if isinstance(value, dict):
            kind = stored_account_type(value)
            value = {**value, "account_type": kind}
            if kind == "app" or "operational_roles" not in value:
                value["operational_roles"] = stored_operational_roles(value)
            if kind == "staff":
                value["allowance"] = None
        return value

    @field_validator("operational_roles")
    @classmethod
    def unique_portal_roles(cls, value):
        return sorted(set(value))


class ProfileUpdateRequest(AccountModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def normalise_name(cls, value: str) -> str:
        normalised = " ".join(value.split())
        if not normalised:
            raise ValueError("Name cannot be empty.")
        return normalised


class AdminStatusUpdateRequest(AccountModel):
    account_status: Literal["active", "suspended"]
    reason: str = Field(default="", max_length=1000)


class PortalRoleUpdateRequest(AccountModel):
    operational_roles: list[OperationalRole] = Field(max_length=2)
    expected_roles: list[OperationalRole] = Field(max_length=2)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def required_reason(cls, value):
        if not value.strip():
            raise ValueError("Provide a reason for the permission change.")
        return value.strip()


class ProvisionAccountRequest(AccountModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    operational_roles: list[OperationalRole] = Field(min_length=1, max_length=2)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("email", "reason", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class StaffToAppRequest(AccountModel):
    confirm_conversion: Literal[True]
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def nonempty_reason(cls, value):
        if not value.strip():
            raise ValueError("Provide a reason for converting the account.")
        return value.strip()
