from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
DbSession = Annotated[Session, Depends(get_db)]
ROLE_RANK = {"viewer": 10, "tester": 20, "qa_lead": 30, "admin": 40}


def current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DbSession) -> User:
	try:
		user_id = int(decode_access_token(token))
	except (ValueError, TypeError, InvalidTokenError) as error:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from error
	user = db.get(User, user_id)
	if not user:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
	if (user.role or "").strip().lower() not in ROLE_RANK:
		user.role = "tester"
		db.add(user)
		db.commit()
		db.refresh(user)
	return user


def require_roles(*allowed_roles: str):
	allowed = {role.strip().lower() for role in allowed_roles if role.strip()}
	if not allowed:
		raise ValueError("At least one role is required")

	def _dependency(user: Annotated[User, Depends(current_user)]) -> User:
		user_role = (user.role or "tester").strip().lower()
		if user_role not in ROLE_RANK:
			raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid user role")
		if user_role not in allowed:
			raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this action")
		return user

	return _dependency