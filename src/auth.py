from dataclasses import dataclass
from datetime import datetime, timedelta, UTC

import jwt
from fastapi import Header, HTTPException


@dataclass
class CurrentUser:
    id: str
    github_login: str
    token: str


def generate_service_token(secret: str) -> str:
    """Generate a JWT for service-to-service calls (e.g. webhook flows)."""
    now = datetime.now(UTC)
    payload = {
        "sub": "service:deployments",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def get_current_user(authorization: str = Header(...)) -> CurrentUser:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = authorization.removeprefix("Bearer ")

    from src.main import settings

    try:
        claims = jwt.decode(token, settings.auth.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=str(e))

    return CurrentUser(
        id=claims["sub"],
        github_login=claims.get("github_login", ""),
        token=token,
    )
