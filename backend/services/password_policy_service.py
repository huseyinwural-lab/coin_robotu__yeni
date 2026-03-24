import re

from fastapi import HTTPException, status


def validate_password_policy(password: str, *, minimum_length: int = 10) -> None:
    value = str(password or "")
    if len(value) < minimum_length:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"password_min_length_{minimum_length}")
    if not re.search(r"[A-Z]", value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password_requires_uppercase")
    if not re.search(r"[a-z]", value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password_requires_lowercase")
    if not re.search(r"\d", value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password_requires_number")
    if not re.search(r"[^A-Za-z0-9]", value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password_requires_symbol")
