"""Auth: bcrypt password hashing + JWT bearer tokens.
Legacy PBKDF2 hashes still verify (so existing users keep working)."""
import hashlib
import hmac
import time

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .config import JWT_SECRET, JWT_TTL_HOURS
from .db import get_db
from .models import User

_bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(pw: str, stored: str) -> bool:
    if stored.startswith("pbkdf2$"):          # legacy hashes
        try:
            _, salt_hex, hash_hex = stored.split("$")
            dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), 200_000)
            return hmac.compare_digest(dk.hex(), hash_hex)
        except Exception:
            return False
    try:
        return bcrypt.checkpw(pw.encode()[:72], stored.encode())
    except Exception:
        return False


def create_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "exp": int(time.time()) + JWT_TTL_HOURS * 3600}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials = Depends(_bearer),
                 db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user
