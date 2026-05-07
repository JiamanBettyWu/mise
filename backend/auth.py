import os

from fastapi import Header, HTTPException, status


def require_password(x_app_password: str | None = Header(default=None)) -> None:
    expected = os.environ.get("APP_PASSWORD")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="APP_PASSWORD not configured on server",
        )
    if x_app_password != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-App-Password header",
        )
