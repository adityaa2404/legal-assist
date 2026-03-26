from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Singleton MongoDB client — shared across all services
_client: AsyncIOMotorClient = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            maxPoolSize=50,
            minPoolSize=5,
            serverSelectionTimeoutMS=5000,
        )
    return _client


def get_database():
    return get_mongo_client()[settings.MONGO_DB_NAME]


async def create_indexes():
    """Create MongoDB indexes on startup. Safe to call multiple times."""
    db = get_database()

    # Users: unique email for fast lookups
    await db.users.create_index("email", unique=True)

    # Sessions: unique session_id for fast lookups
    await db.sessions.create_index("session_id", unique=True)

    # Sessions: TTL index — MongoDB auto-deletes expired docs
    await db.sessions.create_index("expires_at", expireAfterSeconds=0)

    # History: user email for fast lookups, sorted by date
    await db.analysis_history.create_index(
        [("user_email", 1), ("created_at", -1)]
    )

    logger.info("MongoDB indexes created/verified")


async def close_mongo_connection():
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("MongoDB connection closed")
