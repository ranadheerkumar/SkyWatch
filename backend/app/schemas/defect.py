from pydantic import BaseModel, Field


class DefectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    priority: str = Field(default="medium", max_length=20)
    severity: str = Field(default="major", max_length=20)
    status: str = Field(default="open", max_length=20)
    application_id: int | None = None


class ExternalLinkItem(BaseModel):
    id: int
    system: str
    external_key: str
    external_url: str

    model_config = {"from_attributes": True}


class DefectResponse(DefectCreate):
    id: int
    created_by: int
    external_links: list[ExternalLinkItem] = []

    model_config = {"from_attributes": True}


class DefectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    severity: str | None = None
    status: str | None = None
    application_id: int | None = None


class DefectExportRequest(BaseModel):
    connection_id: int | None = None
    project_key: str | None = None
    issue_type: str = "Bug"
    priority: str | None = None
    labels: list[str] | None = None


class DefectExportResponse(BaseModel):
    defect_id: int
    system: str
    external_key: str
    external_url: str
