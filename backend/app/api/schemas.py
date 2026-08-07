from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AnalysisRequest(BaseModel):
    trade_id: str
    trade_revision_id: str | None = None
    retry_of_run_id: str | None = None
    strategy_slug: str = "vwap-reclaim"


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None
    row: int | None = None


class AnalysisRunView(BaseModel):
    id: str
    status: str
    created_at: datetime
