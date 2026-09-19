from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import DbSession, current_user, require_roles
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserProfileResponse, UserRoleUpdateRequest
from app.services.audit import log_audit_event


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(request: RegisterRequest, db: DbSession) -> TokenResponse:
	if db.query(User).filter(User.email == request.email).first():
		raise HTTPException(status_code=409, detail="Email already registered")
	user = User(email=request.email, password_hash=hash_password(request.password), role="tester")
	db.add(user)
	db.commit()
	db.refresh(user)
	log_audit_event(
		db,
		user_id=user.id,
		action="auth.register.completed",
		resource_type="user",
		resource_id=user.id,
		metadata={"email": user.email, "role": user.role},
	)
	db.commit()
	return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: DbSession) -> TokenResponse:
	user = db.query(User).filter(User.email == request.email).first()
	if not user or not verify_password(request.password, user.password_hash):
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
	log_audit_event(
		db,
		user_id=user.id,
		action="auth.login",
		resource_type="user",
		resource_id=user.id,
		metadata={"email": user.email},
	)
	db.commit()
	return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserProfileResponse)
def me(user: User = Depends(current_user)) -> User:
	return user


@router.put("/users/{user_id}/role", response_model=UserProfileResponse)
def update_user_role(
	user_id: int,
	request: UserRoleUpdateRequest,
	db: DbSession,
	admin_user: User = Depends(require_roles("admin")),
) -> User:
	user = db.get(User, user_id)
	if not user:
		raise HTTPException(status_code=404, detail="User not found")
	user.role = request.role
	db.add(user)
	log_audit_event(
		db,
		user_id=admin_user.id,
		action="auth.role.update",
		resource_type="user",
		resource_id=user.id,
		metadata={"new_role": request.role},
	)
	db.commit()
	db.refresh(user)
	return user