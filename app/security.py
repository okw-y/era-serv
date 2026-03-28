import nacl.signing
import nacl.exceptions
import nacl.encoding

import time

from fastapi import Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User


MAX_TIMESTAMP_DIFF = 60


async def verify_signature(request: Request, db: AsyncSession = Depends(get_db)):
    x_public_key = request.headers.get("X-Public-Key")
    x_signature = request.headers.get("X-Signature")
    x_timestamp = request.headers.get("X-Timestamp")

    if not all([x_public_key, x_signature, x_timestamp]):
        raise HTTPException(401, "Missing auth headers!")

    try:
        if abs(time.time() - int(x_timestamp)) > MAX_TIMESTAMP_DIFF:
            raise HTTPException(401, "Request expired!")
    except ValueError:
        raise HTTPException(400, "Invalid timestamp!")

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        body_str = ""
    else:
        body_bytes = await request.body()
        body_str = body_bytes.decode("utf-8")

    path = request.url.path
    method = request.method.upper()

    payload = f"{method}{path}{x_timestamp}{body_str}"

    try:
        verify_key = nacl.signing.VerifyKey(
            x_public_key.encode(), encoder=nacl.encoding.HexEncoder
        )
        verify_key.verify(payload.encode("utf-8"), bytes.fromhex(x_signature))
    except (nacl.exceptions.BadSignatureError, ValueError):
        raise HTTPException(401, "Invalid signature!")

    user = await db.get(User, x_public_key)
    if not user:
        user = User(
            public_key=x_public_key, created_at=int(time.time())
        )
        db.add(user)

        await db.commit()

    return x_public_key
