"""Argon2 password hashing and rotating JWT token support."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from .config import Settings
from .models import RefreshToken, User

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("not-a-real-user-password")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        verify_password(password, DUMMY_HASH)
        return None
    if not user.is_active or not verify_password(password, user.password_hash):
        return None
    return user


def _encode(*, user: User, token_type: str, lifetime: timedelta, secret: str, jti: str):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user.id),
            "username": user.username,
            "type": token_type,
            "jti": jti,
            "iat": now,
            "exp": now + lifetime,
        },
        secret,
        algorithm=ALGORITHM,
    )


def issue_token_pair(db: Session, user: User, settings: Settings) -> dict[str, object]:
    refresh_jti = str(uuid4())
    access_seconds = settings.access_token_minutes * 60
    refresh_expiry = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_days
    )
    db.add(
        RefreshToken(
            jti=refresh_jti,
            user_id=user.id,
            expires_at=refresh_expiry,
        )
    )
    db.commit()
    return {
        "access_token": _encode(
            user=user,
            token_type="access",
            lifetime=timedelta(seconds=access_seconds),
            secret=settings.secret_key,
            jti=str(uuid4()),
        ),
        "refresh_token": _encode(
            user=user,
            token_type="refresh",
            lifetime=timedelta(days=settings.refresh_token_days),
            secret=settings.secret_key,
            jti=refresh_jti,
        ),
        "token_type": "bearer",
        "access_expires_in": access_seconds,
    }


def decode_token(token: str, settings: Settings, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except InvalidTokenError as exc:
        raise ValueError("Invalid or expired token.") from exc
    if payload.get("type") != expected_type or not payload.get("sub"):
        raise ValueError("Invalid token type.")
    return payload
