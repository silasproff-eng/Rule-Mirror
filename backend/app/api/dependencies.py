from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.base import SessionLocal

bearer = HTTPBearer(auto_error=False)


def database():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def current_user_id(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    if credentials is None:
        raise HTTPException(401, detail={"code": "invalid_access_token", "message": "Authentication is required"})
    try:
        return decode_access_token(credentials.credentials)
    except Exception as error:
        raise HTTPException(401, detail={"code": "invalid_access_token", "message": "Authentication is required"}) from error


Database = Session
