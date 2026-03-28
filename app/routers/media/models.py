from pydantic import BaseModel


class UploadRequest(BaseModel):
    room_id: str = None

    is_eternal: bool = False
    is_encrypted: bool = True
