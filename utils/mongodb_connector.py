import os
import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class MongoDBConnector:
    _client: Optional[AsyncIOMotorClient] = None
    _db: Optional[AsyncIOMotorDatabase] = None

    @classmethod
    async def initialize(cls) -> None:
        """MongoDB 연결 초기화"""
        if cls._client is not None:
            return

        load_dotenv()

        try:
            mongodb_uri = os.getenv('MONGODB_URI')
            db_name = os.getenv('MONGODB_DB_NAME')

            if not mongodb_uri or not db_name:
                raise ValueError("MongoDB configuration is missing in environment variables")

            # MongoDB 클라이언트 생성
            cls._client = AsyncIOMotorClient(mongodb_uri)
            # 데이터베이스 연결 확인
            await cls._client.admin.command('ping')

            cls._db = cls._client[db_name]
            logger.info("MongoDB connection established successfully")

        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
        except Exception as e:
            logger.error(f"Error initializing MongoDB connection: {e}")
            raise

    @classmethod
    async def get_database(cls) -> AsyncIOMotorDatabase:
        """데이터베이스 객체 반환"""
        if cls._client is None or cls._db is None:
            await cls.initialize()
        return cls._db

    @classmethod
    async def get_collection(cls, collection_name: str) -> AsyncIOMotorCollection:
        """컬렉션 객체 반환"""
        db = await cls.get_database()
        return db[collection_name]

    @classmethod
    async def close(cls) -> None:
        """MongoDB 연결 종료"""
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            cls._db = None
            logger.info("MongoDB connection closed")