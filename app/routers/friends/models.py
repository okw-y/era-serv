from pydantic import BaseModel

from app.models import PrivacyType


class PostMeRequest(BaseModel):
    name: str = None
    bio: str = None
    avatar_id: str = None


class PublicityRequest(BaseModel):
    is_public: bool
    username: str


class PrivacyRequest(BaseModel):
    avatar_privacy: PrivacyType = None
    bio_privacy: PrivacyType = None
    last_seen_privacy: PrivacyType = None


class RequestFriendRequest(BaseModel):
    room_id: str
    pub_key: str


class AcceptFriendRequest(BaseModel):
    pub_key: str
    deny: bool = False

class RemoveFriendRequest(BaseModel):
    pub_key: str
