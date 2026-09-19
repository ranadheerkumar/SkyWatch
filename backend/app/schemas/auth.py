from pydantic import BaseModel, EmailStr, Field
from typing import Literal


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