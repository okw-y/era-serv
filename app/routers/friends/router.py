import os.path
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .models import *
# from .utils import *

from app.database import get_db
from app.models import Room, Member, Message, MemberType, User, UserProfile
from app.security import verify_signature


router = APIRouter(prefix="/friends")


@router.get("/me")
async def get_me(
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
):
    user = await db.get(User, sender_pub_key)
    profile = await db.get(UserProfile, sender_pub_key)

    return {
        "status": "ok",
        "data": {
            "id": sender_pub_key,
            "meta": {
                "name": profile.name,
                "bio": profile.bio,
                "avatar_id": profile.avatar_id,
                "last_seen": profile.last_online,
                "created_at": user.created_at
            },
            "privacy": {
                "is_public": user.is_public,
                "avatar_privacy": user.avatar_privacy,
                "bio_privacy": user.bio_privacy,
                "last_seen_privacy": user.last_online_privacy
            }
        }
    }


@router.post("/me")
async def post_me(
        request: PostMeRequest,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
):
    profile = await db.get(UserProfile, sender_pub_key)

    if name := request.name:
        if len(name) > 32:
            raise HTTPException(403, "Max room name length = 32!")

        profile.name = name

    if bio := request.bio:
        if len(bio) > 256:
            raise HTTPException(403, "Max user bio length = 256!")

        profile.bio = bio

    if avatar_id := request.avatar_id:
        if not os.path.exists(os.path.join(os.environ["UPLOADS_LOCATION"], avatar_id)):
            raise HTTPException(403, "Photo was not found!")

        profile.avatar_id = avatar_id

    return {"status": "ok"}
