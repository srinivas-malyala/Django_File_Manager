"""Registration, login, token rotation, logout, and identity endpoints."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_

from ..config import Settings
from ..dependencies import CurrentUser, Database, get_settings
from ..models import RefreshToken, User
from ..responses import envelope
from ..schemas import RefreshRequest, RegisterRequest, TokenPairResponse, UserResponse
from ..security import authenticate, decode_token, hash_password, issue_token_pair

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Database):
    username = payload.username.strip()
    existing = (
        db.query(User)
        .filter(or_(User.username == username, User.email == payload.email))
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username or email already exists.")
    user = User(
        username=username,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return envelope(
        UserResponse.model_validate(user).model_dump(mode="json"),
        "Account created successfully",
    )


@router.post("/token", response_model=TokenPairResponse)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Database,
    settings: Annotated[Settings, Depends(get_settings)],
):
    user = authenticate(db, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return issue_token_pair(db, user, settings)


def _active_refresh(payload: RefreshRequest, db: Database, settings: Settings):
    try:
        claims = decode_token(payload.refresh_token, settings, "refresh")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None
    token = db.query(RefreshToken).filter(RefreshToken.jti == claims.get("jti")).first()
    expires_at = token.expires_at if token else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if (
        token is None
        or token.revoked_at is not None
        or expires_at <= datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=401, detail="Refresh token is revoked or expired."
        )
    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account is unavailable.")
    return token, user


@router.post("/token/refresh", response_model=TokenPairResponse)
def refresh(
    payload: RefreshRequest,
    db: Database,
    settings: Annotated[Settings, Depends(get_settings)],
):
    token, user = _active_refresh(payload, db, settings)
    token.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return issue_token_pair(db, user, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: RefreshRequest,
    db: Database,
    settings: Annotated[Settings, Depends(get_settings)],
):
    token, _ = _active_refresh(payload, db, settings)
    token.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return None


@router.get("/status")
def authentication_status(user: CurrentUser):
    return envelope(
        UserResponse.model_validate(user).model_dump(mode="json"),
        "Authentication successful",
    )
