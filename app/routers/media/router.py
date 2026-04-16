# app/routers/media/router.py

import os
import uuid
import time

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse

from app.database import get_db
from app.models import Member, User, Friendship, Upload, PrivacyType, FriendshipType
from app.security import verify_signature


router = APIRouter(prefix="/media")


@router.post("/upload")
async def upload_file(
        room_id: str = Form(None),
        is_eternal: bool = Form(False),
        is_encrypted: bool = Form(False),
        file: UploadFile = File(...),
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    created_at = int(time.time())

    file_id = str(uuid.uuid4())
    file_path = os.path.join(os.environ["UPLOADS_LOCATION"], file_id)
    file_size = file.size or 0

    max_size = int(os.environ["STORAGE_MAX_ETERNAL_SIZE"])
    if is_eternal and file_size > max_size:
        raise HTTPException(400, f"The undeletable file weighs more than {max_size / 1024 / 1024}MB!")

    upload = Upload(
        id=file_id,
        path=file_path,
        size=file_size,

        acc_key=sender_pub_key,
        room_id=room_id,

        is_eternal=is_eternal,
        is_encrypted=is_encrypted,

        created_at=created_at
    )

    db.add(upload)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)  # noqa

        await db.commit()
    except Exception:
        raise HTTPException(500, "File save error!")

    return {
        "status": "ok",
        "data": {
            "id": file_id,
            "size": file_size,
            "created_at": created_at
        }
    }


@router.get("/{file_id}")
async def get_file(
        file_id: str,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
):
    file = await db.get(Upload, file_id)
    if not file:
        raise HTTPException(404, "File not found!")

    can_get = file.acc_key == sender_pub_key
    if not can_get and file.room_id:
        query = select(Member).where(Member.room_id == file.room_id, Member.acc_key == sender_pub_key)
        if (await db.execute(query)).scalar_one_or_none():
            can_get = True

    if not can_get and not file.is_encrypted:
        owner = await db.get(User, file.acc_key)

        match owner.avatar_privacy:
            case PrivacyType.ALL:
                can_get = True
            case PrivacyType.FRIENDS:
                friendship = select(Friendship).where(
                    (
                        ((Friendship.user_a == sender_pub_key) & (Friendship.user_b == file.acc_key)) |
                        ((Friendship.user_a == file.acc_key) & (Friendship.user_b == sender_pub_key))
                    ) &
                    Friendship.status == FriendshipType.ACCEPT
                )

                if (await db.execute(friendship)).scalar_one_or_none():
                    can_get = True

    if can_get:
        return FileResponse(str(file.path), media_type="application/octet-stream")
    else:
        raise HTTPException(403, "Access denied!")
