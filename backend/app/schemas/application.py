from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class ApplicationCreate(BaseModel):
	name: str = Field(min_length=1, max_length=120)
	platform: Literal["web", "android", "ios"]
	target: str = Field(min_length=1, max_length=2048)


class ApplicationResponse(ApplicationCreate):
	id: int

	model_config = {"from_attributes": True}


class ApplicationUpdate(BaseModel):
	name: str = Field(min_length=1, max_length=120)
	target: str = Field(min_length=1, max_length=2048)