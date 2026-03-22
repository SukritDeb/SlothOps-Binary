"""
SlothOps Engine — Authentication & Security
Handles JSON Web Token generation, validation, and password hashing 
for the Multi-Tenant SaaS dashboard.
"""

from typing import Optional
from datetime import datetime, timedelta
import os
import jwt
import bcrypt
from pydantic import BaseModel

SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-dev-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 Days



class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: Optional[str] = None
    workspace_id: Optional[str] = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        # bcrypt requires bytes
        return bcrypt.checkpw(
            plain_password[:72].encode('utf-8'), 
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password[:72].encode('utf-8'), salt).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        workspace_id: str = payload.get("workspace_id")
        return TokenData(user_id=user_id, workspace_id=workspace_id)
    except jwt.PyJWTError:
        return TokenData()
