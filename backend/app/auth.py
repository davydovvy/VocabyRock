import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import AuthSession, User, now

COOKIE = "vacabyrock_session"
_attempts: dict[str, deque[float]] = defaultdict(deque)


def login_allowed(key: str) -> bool:
    attempts = _attempts[key]
    while attempts and attempts[0] < time.monotonic() - 300:
        attempts.popleft()
    return len(attempts) < 5


def record_failed_login(key: str):
    _attempts[key].append(time.monotonic())


def clear_failed_logins(key: str):
    _attempts.pop(key, None)


def verify_password(value: str) -> bool:
    expected = get_settings().admin_password
    if expected in {"change-me", "replace-with-a-long-password", ""}:
        return False
    return hmac.compare_digest(value.encode(), expected.encode())


def create_session(db: Session, response: Response, user: User):
    token = secrets.token_urlsafe(40)
    db.add(
        AuthSession(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            user_id=user.id,
            expires_at=now() + timedelta(days=get_settings().session_days),
        )
    )
    db.commit()
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="strict",
        max_age=get_settings().session_days * 86400,
        path="/",
    )


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Please choose your avatar")
    auth = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == hashlib.sha256(token.encode()).hexdigest()
        )
    )
    if not auth or auth.expires_at < now():
        raise HTTPException(401, "Session expired. Please sign in again")
    return auth.user


def parent(user: User = Depends(current_user)) -> User:
    if user.role != "parent":
        raise HTTPException(403, "Parent access required")
    return user


def child(user: User = Depends(current_user)) -> User:
    if user.role != "child":
        raise HTTPException(403, "Choose a child avatar to play")
    return user


def logout(request: Request, response: Response, db: Session):
    token = request.cookies.get(COOKIE)
    if token:
        auth = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == hashlib.sha256(token.encode()).hexdigest()
            )
        )
        if auth:
            db.delete(auth)
            db.commit()
    response.delete_cookie(COOKIE, path="/")
