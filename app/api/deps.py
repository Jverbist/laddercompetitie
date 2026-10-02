from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, UserRole

DbSession = Annotated[Session, Depends(get_db)]


def authenticated_user(request: Request, db: DbSession) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in is required.")
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown or inactive user.")
    return user


AuthenticatedUser = Annotated[User, Depends(authenticated_user)]


def current_user(user: AuthenticatedUser) -> User:
    if user.must_reset_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A password reset is required.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def admin_user(user: CurrentUser) -> User:
    if user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator permission required.")
    return user


AdminUser = Annotated[User, Depends(admin_user)]
