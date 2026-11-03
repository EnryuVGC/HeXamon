from motor.motor_asyncio import AsyncIOMotorClient


def open_client(uri: str) -> AsyncIOMotorClient:
    return AsyncIOMotorClient(uri)
