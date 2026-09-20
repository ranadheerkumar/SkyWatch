from typing import Literal
from pydantic import BaseModel, Field

try:
    import email_validator  # noqa: F401
    from pydantic import EmailStr
except Exception:
    EmailStr = str  # type: ignore[assignment,misc]


class RegisterRequest(BaseModel):
	email: EmailStr
	password: str = Field(min_length=12, max_length=128)


class LoginRequest(RegisterRequest):
	pass


class TokenResponse(BaseModel):
	access_token: str
	token_type: str = "bearer"


class UserProfileResponse(BaseModel):
	id: int
	email: EmailStr
	role: Literal["admin", "qa_lead", "tester", "viewer"]

	model_config = {"from_attributes": True}


class UserRoleUpdateRequest(BaseModel):
	role: Literal["admin", "qa_lead", "tester", "viewer"]