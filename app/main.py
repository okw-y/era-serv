import asyncio
import os

import dotenv
import time

dotenv.load_dotenv(".env")

from fastapi import FastAPI
from sqlalchemy import delete

from app.models import Message
from app.routers import rooms, media, chat
from app.database import engine, Base, AsyncSessionLocal

app = FastAPI(title="paranoya")


async def clean_old_messages():
    while True:
        period = int(os.environ["STORAGE_PERIOD"])
        try:
            async with AsyncSessionLocal() as db:
                stmt = delete(Message).where(
                    Message.created_at < period
                )

                await db.execute(stmt)
                await db.commit()

        except Exception as error:
            print(f"cleanup error: {error}")

        start_time = time.time()
        start_path = os.environ["UPLOADS_LOCATION"]
        for file in os.listdir(start_path):
            if start_time - os.path.getctime(path := os.path.join(start_path, file)) > period:
                os.remove(path)

        await asyncio.sleep(int(os.environ["STORAGE_PERIOD_CHECK"]))


@app.on_event("startup")
async def startup():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    asyncio.create_task(clean_old_messages())


app.include_router(rooms.router)
app.include_router(media.router)
app.include_router(chat.router)
