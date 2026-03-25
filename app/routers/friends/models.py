from pydantic import BaseModel


class PostMeRequest(BaseModel):
    name: str = None
    bio: str = None
    avatar_id: str = None
