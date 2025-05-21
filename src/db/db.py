import datetime
import logging
import re
import os
import sys
import threading
from typing import Dict, List, Tuple

import asyncpg
import dotenv
from asyncpg import Pool
from redis.asyncio import Redis
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
import custom_dataclass as cdata

dotenv.load_dotenv()

# Configure logger
logger = logging.getLogger("backendlogger")

# Database connection parameters
NEON_URL = os.getenv("NEON_URL")
REDIS_URL = os.getenv("REDIS_URL")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_CLIENT: Redis | None = None
SQL_QUERIES: Dict[str, str] = {}

pool: Pool | None = None
_conn_lock = threading.Lock()


def get_redis_client() -> Redis:
    global REDIS_CLIENT
    if REDIS_CLIENT is None:
        try:
            REDIS_CLIENT = Redis(
                host=str(REDIS_URL),
                port=int(REDIS_PORT),
                max_connections=20,
            )
        except Exception as e:
            logger.error(f"Failed to create Redis client: {str(e)}")
            raise
    return REDIS_CLIENT


def load_sql_queries() -> None:
    """Load SQL queries from files into memory."""
    try:
        models_path = str(Path(__file__).parent) + "/schema/models.sql"
        queries_path = str(Path(__file__).parent) + "/query/query.sql"
        allpaths = [models_path, queries_path]

        for p in allpaths:
            if not Path(p).exists():
                logger.error(f"SQL file not found: {p}")
                raise

            data: str = Path(p).read_text().strip()
            allstatements = re.split("-- name: (.*)", data)[1:]
            for i in range(0, len(allstatements) - 1, 2):
                SQL_QUERIES[allstatements[i].strip()] = allstatements[i + 1].strip()

        logger.info(f"Loaded {len(SQL_QUERIES)} SQL queries")
    except Exception as e:
        logger.error(f"Error loading SQL queries: {str(e)}")
        raise


async def get_pool() -> Pool | None:
    """Get or create a database connection pool."""
    global pool

    with _conn_lock:
        if pool is None:
            try:
                if not NEON_URL:
                    logger.error("NEON_URL environment variable not set")
                    raise

                pool = await asyncpg.create_pool(dsn=NEON_URL)
                logger.info("Database connection pool created")
            except Exception as e:
                logger.error(f"Failed to create connection pool: {str(e)}")
                return None
    return pool


async def db_createalldbs() -> bool:
    """Create all database tables."""
    try:
        pool: Pool | None = await get_pool()
        if not pool:
            logger.error("Failed to get database pool")
            return False

        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"""
                    {SQL_QUERIES["CreateUserTable"]}
                    {SQL_QUERIES["CreateGameTable"]}
                    {SQL_QUERIES["CreatePlansTable"]}
                    {SQL_QUERIES["CreateSubscriptionsTable"]}
                    {SQL_QUERIES["CreateBaremetalTable"]}
                    {SQL_QUERIES["CreateServersTable"]}
                    {SQL_QUERIES["CreateTransactionsTable"]}
                    """)
        logger.info("All database tables created successfully")
        return True
    except Exception as e:
        logger.error(f"Error creating database tables: {str(e)}")
        raise


async def db_insert_user(
    data: cdata.RegisterUserData,
) -> Tuple[asyncpg.Record | None, str | None]:
    """Insert a new user into the database and return the new record."""
    try:
        if not data.email or not data.password:
            return None, "Email and password are required"

        pool = await get_pool()
        if not pool:
            return None, "Database connection failed"

        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                f"{SQL_QUERIES['InsertUser']}",
                data.email,
                data.password,
            )
            return result, None
    except asyncpg.UniqueViolationError:
        logger.warning(f"Attempt to create duplicate user: {data.email}")
        return None, "User with that email already exists"
    except Exception as e:
        logger.error(f"Error inserting user: {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_insert_subscription(
    user_id: str,
    plan_id: str,
    status: str,
    expires_at: datetime.datetime,
    next_billing_date: datetime.datetime,
) -> Tuple[asyncpg.Record | None, str | None]:
    """Insert a new subscription and return its record."""
    try:
        if not user_id or not plan_id:
            return None, "User ID and plan ID are required"

        pool = await get_pool()
        if not pool:
            return None, "Database connection failed"

        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                f"{SQL_QUERIES['InsertSubscription']}",
                user_id,
                plan_id,
                status,
                expires_at,
                next_billing_date,
            )
            return result, None
    except asyncpg.ForeignKeyViolationError:
        logger.warning(
            f"Foreign key violation on subscription insert: user_id={user_id}, plan_id={plan_id}"
        )
        return None, "User or plan does not exist"
    except Exception as e:
        logger.error(f"Error inserting subscription: {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_insert_server(
    subscription_id: str,
    status: str,
    ip_address: str,
    ports: str,
    docker_container_id: str,
    cfg: str,
) -> Tuple[asyncpg.Record | None, str | None]:
    """Insert a new server and return its record."""
    try:
        if not subscription_id:
            return None, "Subscription ID is required"

        pool = await get_pool()
        if not pool:
            return None, "Database connection failed"

        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                f"{SQL_QUERIES['InsertServer']}",
                subscription_id,
                status,
                ip_address,
                ports,
                docker_container_id,
                cfg,
            )
            return result, None
    except asyncpg.ForeignKeyViolationError:
        logger.warning(
            f"Foreign key violation on server insert: subscription_id={subscription_id}"
        )
        return None, "Subscription does not exist"
    except Exception as e:
        logger.error(f"Error inserting server: {str(e)}")
        return None, f"Database error: {str(e)}"


# ----- SELECT OPERATIONS -----


async def db_select_user_by_email(
    email: str,
) -> Tuple[asyncpg.Record | None, str | None]:
    """Select a user by email address."""
    try:
        if not email:
            return None, "Email is required"

        pool = await get_pool()
        if not pool:
            return None, "Database connection failed"

        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                f"{SQL_QUERIES['SelectUserByEmail']}",
                email,
            )
            return result, None
    except Exception as e:
        logger.error(f"Error selecting user by email: {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_select_all_baremetals() -> Tuple[List[asyncpg.Record], str | None]:
    """Get all bare metal servers."""
    try:
        pool = await get_pool()
        if not pool:
            return [], "Database connection failed"

        async with pool.acquire() as conn:
            result = await conn.fetch(f"{SQL_QUERIES['SelectAllBaremetals']}")
            return result, None
    except Exception as e:
        logger.error(f"Error selecting all baremetals: {str(e)}")
        return [], f"Database error: {str(e)}"


async def db_select_all_subscriptions(
    user_id: str,
) -> Tuple[List[asyncpg.Record], str | None]:
    """Get all subscriptions for a user."""
    try:
        if not user_id:
            return [], "User ID is required"

        pool = await get_pool()
        if not pool:
            return [], "Database connection failed"

        async with pool.acquire() as conn:
            result = await conn.fetch(
                f"{SQL_QUERIES['SelectAllSubscriptions']}",
                user_id,
            )
            return result, None
    except Exception as e:
        logger.error(f"Error selecting all subscriptions: {str(e)}")
        return [], f"Database error: {str(e)}"


async def db_select_plan_by_id(
    plan_id: str,
) -> Tuple[asyncpg.Record | None, str | None]:
    """Get a plan by its ID."""
    try:
        if not plan_id:
            return None, "Plan ID is required"

        pool = await get_pool()
        if not pool:
            return None, "Database connection failed"

        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                f"{SQL_QUERIES['SelectPlanById']}",
                plan_id,
            )
            return result, None
    except Exception as e:
        logger.error(f"Error selecting plan by ID: {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_select_game_by_id(
    game_id: str,
) -> Tuple[asyncpg.Record | None, str | None]:
    """Get a game by its ID."""
    try:
        if not game_id:
            return None, "Game ID is required"

        pool = await get_pool()
        if not pool:
            return None, "Database connection failed"

        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                f"{SQL_QUERIES['SelectGameById']}",
                game_id,
            )
            return result, None
    except Exception as e:
        logger.error(f"Error selecting game by ID: {str(e)}")
        return None, f"Database error: {str(e)}"


# ----- OPTIONAL ADDITIONAL SELECTS -----
async def db_select_subscription_by_id(
    sub_id: str,
) -> Tuple[asyncpg.Record | None, str | None]:
    """Get a subscription by its ID."""
    try:
        if not sub_id:
            return None, "Subscription ID is required"

        pool = await get_pool()
        if not pool:
            return None, "Database connection failed"

        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                f"{SQL_QUERIES['SelectSubscriptionById']}",
                sub_id,
            )
            return result, None
    except Exception as e:
        logger.error(f"Error selecting subscription by ID: {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_select_subscription_by_user(
    user_id: str,
) -> Tuple[List[asyncpg.Record], str | None]:
    """List all subscriptions for a given user."""
    try:
        if not user_id:
            return [], "User ID is required"

        pool = await get_pool()
        if not pool:
            return [], "Database connection failed"

        async with pool.acquire() as conn:
            result = await conn.fetch(
                f"{SQL_QUERIES['SelectSubscriptionsByUser']}",
                user_id,
            )
            return result, None
    except Exception as e:
        logger.error(f"Error selecting subscriptions by user: {str(e)}")
        return [], f"Database error: {str(e)}"


async def db_select_servers_by_subscription(
    subscription_id: str,
) -> Tuple[asyncpg.Record | None, str | None]:
    """List all servers under a specific subscription."""
    try:
        if not subscription_id:
            return None, "Subscription ID is required"

        pool = await get_pool()
        if not pool:
            return None, "Database connection failed"

        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                f"{SQL_QUERIES['SelectServersBySubscription']}",
                subscription_id,
            )
            return result, None
    except Exception as e:
        logger.error(f"Error selecting servers by subscription: {str(e)}")
        return None, f"Database error: {str(e)}"


# ------------UPDATES--------------
async def db_update_server_status(
    status: str,
    docker_container_id: str,
    subscription_id: str,
) -> Tuple[asyncpg.Record | None, str | None]:
    """Update server status by subscription ID."""
    try:
        if not subscription_id:
            return None, "Subscription ID is required"

        pool = await get_pool()
        if not pool:
            return None, "Database connection failed"

        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                f"{SQL_QUERIES['UpdateServerStatus']}",
                status,
                docker_container_id,
                subscription_id,
            )
            if not result:
                return None, "Server not found"
            return result, None
    except Exception as e:
        logger.error(f"Error updating server status: {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_update_subscription_status(
    subscription_id: str,
    status: str,
    last_billing_date: datetime.datetime,
    next_billing_date: datetime.datetime,
) -> Tuple[asyncpg.Record | None, str | None]:
    """Update subscription status and billing dates."""
    try:
        if not subscription_id:
            return None, "Subscription ID is required"

        pool = await get_pool()
        if not pool:
            return None, "Database connection failed"

        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                f"{SQL_QUERIES['UpdateSubscriptionStatus']}",
                status,
                last_billing_date,
                next_billing_date,
                subscription_id,
            )
            if not result:
                return None, "Subscription not found"
            return result, None
    except Exception as e:
        logger.error(f"Error updating subscription status: {str(e)}")
        return None, f"Database error: {str(e)}"


# Initialize SQL queries on module load
try:
    load_sql_queries()
except Exception as e:
    logger.critical(f"Failed to load SQL queries: {str(e)}")
    sys.exit(1)
