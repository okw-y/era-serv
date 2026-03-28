import os.path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import *

from app.database import get_db
from app.models import Member, User, UserProfile, Friendship, FriendshipType
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
                "last_seen": profile.last_seen,
                "created_at": user.created_at
            },
            "privacy": {
                "is_public": user.is_public,
                "avatar_privacy": user.avatar_privacy,
                "bio_privacy": user.bio_privacy,
                "last_seen_privacy": user.last_seen_privacy
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

    await db.commit()

    return {"status": "ok"}


@router.post("/publicity")
async def publicity(
        request: PublicityRequest,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
):
    user = await db.get(User, sender_pub_key)
    profile = await db.get(UserProfile, sender_pub_key)

    user.is_public = request.is_public
    if request.is_public:
        query = select(UserProfile).where(
            UserProfile.username == request.username
        )
        response = await db.scalar(query)
        if response:
            raise HTTPException(400, "The username is already taken!")

        profile.username = request.username
    else:
        profile.username = ""

    await db.commit()

    return {"status": "ok"}


@router.post("/privacy")
async def privacy(
        request: PrivacyRequest,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
):
    user = await db.get(User, sender_pub_key)

    if request.avatar_privacy:
        user.avatar_privacy = request.avatar_privacy

    if request.bio_privacy:
        user.bio_privacy = request.bio_privacy

    if request.last_seen_privacy:
        user.last_seen_privacy = request.last_seen_privacy

    return {"status": "ok"}


@router.post("/request")
async def request_friend(
        request: RequestFriendRequest,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
):
    sender_query = select(Member).where(
        Member.room_id == request.room_id,
        Member.acc_key == sender_pub_key
    )
    sender_response = await db.execute(sender_query)

    sender = sender_response.scalar_one_or_none()
    if not sender:
        raise HTTPException(403, "Not authorized to send friendship request!")

    query = select(Member).where(
        Member.room_id == request.room_id,
        Member.pub_room_key == request.pub_key
    )
    response = await db.execute(query)

    member = response.scalar_one_or_none()
    if not member:
        raise HTTPException(404, "Member not found!")

    friend = Friendship(
        user_a=sender_pub_key,
        user_b=member.acc_key,
        status=FriendshipType.PENDING
    )
    db.add(friend)

    await db.commit()


@router.post("/accept")
async def accept_friend(
        request: AcceptFriendRequest,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
):
    query = select(Friendship).where(
        Friendship.user_a == request.pub_key,
        Friendship.user_b == sender_pub_key,
        Friendship.status == FriendshipType.PENDING
    )
    response = await db.execute(query)

    application = response.scalar_one_or_none()
    if not application:
        raise HTTPException(404, "Application not found!")

    if request.deny:
        await db.delete(application)
    else:
        application.status = FriendshipType.ACCEPT

        await db.commit()


@router.post("/remove")
async def remove_friend(
        request: RemoveFriendRequest,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
):
    query = select(Friendship).where(
        Friendship.user_a == request.pub_key,
        Friendship.user_b == sender_pub_key,
        Friendship.status == FriendshipType.ACCEPT
    )
    response = await db.execute(query)

    friendship = response.scalar_one_or_none()
    if not friendship:
        raise HTTPException(404, "Friendship not found!")

    await db.delete(friendship)
