import os
import shutil

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.responses import FileResponse

from uuid import uuid4

from app.security import verify_signature


router = APIRouter(prefix="/media")

os.makedirs(
    os.environ["UPLOADS_LOCATION"], exist_ok=True
)


@router.post("/upload")
async def upload_file(
        file: UploadFile = File(...),
        sender_pub_key: str = Depends(verify_signature)  # noqa
) -> dict[str, str]:
    file_id = str(uuid4())
    file_path = os.path.join(os.environ["UPLOADS_LOCATION"], file_id)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)  # noqa
    except Exception:
        raise HTTPException(500, "File save error!")

    return {"file_id": file_id}


@router.get("/{file_id}")
async def get_file(file_id: str):
    file_path = os.path.join(os.environ["UPLOADS_LOCATION"], file_id)
    if not os.path.exists(file_path):
        raise HTTPException(404, "Not found")

    return FileResponse(file_path, media_type="application/octet-stream")
