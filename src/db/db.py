import asyncio
import datetime
import logging
import re
import os
import sys
import threading
from typing import Any, Dict, List, Optional, Tuple

import asyncpg
import dotenv
from asyncpg import Pool, Record
from redis.asyncio import Redis
from pathlib import Path
import enum

sys.path.append(str(Path(__file__).resolve().parent.parent))
import helper_classes.custom_dataclass as cdata

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


class QUERY_TYPE(enum.Enum):
    EXECUTE = 0
    FETCH = 1
    FETCHROW = 2


class SUBSCRIPTION_STATUS(enum.Enum):
    PROVISIONING = "provisioning"
    UNAVAILABLE = "unavailable"  # RESOURCES FULL
    TRIAL = "trial"  # free trial
    ACTIVE = "active"  # paying and active
    EXPIRED = "expired"
    FAILED = "failed"  # can handles also miscenallnious failures


class SERVER_STATUS(enum.Enum):
    PROVISIONING = "provisioning"
    RESTARTING = "restarting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    CONFIGURED = "configured"
    # the rest should ideally not happen
    FAILED = "failed"
    NOT_FOUND = "not_found"


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
        queries_path = str(Path(__file__).parent) + "/query/query.sql"
        all_paths = [queries_path]

        for p in all_paths:
            if not Path(p).exists():
                logger.error(f"SQL file not found: {p}")
                raise

            data: str = Path(p).read_text().strip()
            all_statements = re.split("-- name: (.*)", data)[1:]
            for i in range(0, len(all_statements) - 1, 2):
                SQL_QUERIES[all_statements[i].strip()] = all_statements[i + 1].strip()

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

                # pool = await asyncpg.create_pool(dsn=NEON_URL)
                PG_LOCAL = os.getenv("PG_LOCAL")
                pool = await asyncpg.create_pool(dsn=PG_LOCAL)
                logger.info("Database connection pool created")
            except Exception as e:
                logger.error(f"Failed to create connection pool: {str(e)}")
                raise RuntimeError(f"Failed to create connection pool: {str(e)}")

    return pool


async def conn_manager(qt: QUERY_TYPE, transaction=False, *args) -> Any:
    pool = await get_pool()
    if not pool:
        return None, "Database connection failed"
    conn: asyncpg.connection.Connection

    async def run(conn):
        match qt:
            case QUERY_TYPE.EXECUTE:
                return await conn.execute(*args)
            case QUERY_TYPE.FETCH:
                return await conn.fetch(*args)
            case QUERY_TYPE.FETCHROW:
                return await conn.fetchrow(*args)

    async with pool.acquire() as conn:
        if not transaction:
            return await run(conn)
        else:
            async with conn.transaction():
                return await run(conn)


async def create_tables():
    models_path = str(Path(__file__).parent) + "/schema/models.sql"
    p = await get_pool()
    await conn_manager(QUERY_TYPE.EXECUTE, True, Path(models_path).read_text())


async def db_createalldbs() -> bool:
    """Create all database tables."""
    try:
        qs = f"""
                CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
                {SQL_QUERIES["CreateUserTable"]}
                {SQL_QUERIES["CreateGameTable"]}
                {SQL_QUERIES["CreatePlansTable"]}
                {SQL_QUERIES["CreateSubscriptionsTable"]}
                {SQL_QUERIES["CreateBaremetalTable"]}
                {SQL_QUERIES["CreateServersTable"]}
                {SQL_QUERIES["CreateTransactionsTable"]}
            """
        await conn_manager(QUERY_TYPE.EXECUTE, True, qs)
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
        return await conn_manager(
            QUERY_TYPE.FETCHROW,
            True,
            SQL_QUERIES["InsertUser"],
            data.email,
            data.password,
        ), None
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
    is_trial=False,
) -> Tuple[asyncpg.Record | None, str | None]:
    """Insert a new subscription and return its record."""
    try:
        return await conn_manager(
            QUERY_TYPE.FETCHROW,
            False,
            SQL_QUERIES["InsertSubscription"],
            user_id,
            plan_id,
            status,
            expires_at,
            next_billing_date,
            is_trial,
        ), None
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

        return await conn_manager(
            QUERY_TYPE.FETCHROW,
            False,
            SQL_QUERIES["InsertServer"],
            subscription_id,
            status,
            ip_address,
            ports,
            docker_container_id,
            cfg,
        ), None

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

        return await conn_manager(
            QUERY_TYPE.FETCHROW, False, SQL_QUERIES["SelectUserByEmail"], email
        ), None

    except Exception as e:
        logger.error(f"Error selecting user by email: {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_select_all_baremetals() -> Tuple[List[asyncpg.Record], str | None]:
    """Get all bare metal servers."""
    try:
        return await conn_manager(
            QUERY_TYPE.FETCH, False, SQL_QUERIES["SelectAllBaremetals"]
        ), None
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

        return await conn_manager(
            QUERY_TYPE.FETCH, False, SQL_QUERIES["SelectAllSubscriptions"], user_id
        ), None

    except Exception as e:
        logger.error(f"Error selecting all subscriptions: {str(e)}")
        return [], f"Database error: {str(e)}"


async def db_select_all_plans_by_game(
    game_id: str,
) -> Tuple[List[asyncpg.Record], str | None]:
    """Get all subscriptions for a user."""
    try:
        if not game_id:
            return [], "game_name is required"

        return await conn_manager(
            QUERY_TYPE.FETCH, False, SQL_QUERIES["SelectAllPlansByGame"], game_id
        ), None

    except Exception as e:
        logger.error(f"Error selecting all plans: {str(e)}")
        return [], f"Database error: {str(e)}"


async def db_select_plan_by_id(
    plan_id: str,
) -> Tuple[asyncpg.Record | None, str | None]:
    """Get a plan by its ID."""
    try:
        if not plan_id:
            return None, "Plan ID is required"

        return await conn_manager(
            QUERY_TYPE.FETCHROW, False, SQL_QUERIES["SelectPlanById"], plan_id
        ), None
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

        return await conn_manager(
            QUERY_TYPE.FETCHROW, False, SQL_QUERIES["SelectGameById"], game_id
        ), None

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

        return await conn_manager(
            QUERY_TYPE.FETCHROW, False, SQL_QUERIES["SelectSubscriptionById"], sub_id
        ), None

    except Exception as e:
        logger.error(f"Error selecting subscription by ID: {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_select_all_subscriptions_by_user(
    user_id: str,
) -> Tuple[List[asyncpg.Record], str | None]:
    """List all subscriptions for a given user."""
    try:
        if not user_id:
            return [], "User ID is required"

        return await conn_manager(
            QUERY_TYPE.FETCH,
            False,
            SQL_QUERIES["SelectAllSubscriptionsByUser"],
            user_id,
        ), None

    except Exception as e:
        logger.error(f"Error selecting subscriptions by user: {str(e)}")
        return [], f"Database error: {str(e)}"


async def db_select_server_by_subscription(
    subscription_id: str,
) -> Tuple[asyncpg.Record | None, str | None]:
    """select_server_by_subscription"""
    try:
        if not subscription_id:
            return None, "Subscription ID is required"

        return await conn_manager(
            QUERY_TYPE.FETCHROW,
            False,
            SQL_QUERIES["SelectServerBySubscription"],
            subscription_id,
        ), None
    except Exception as e:
        logger.error(f"Error selecting servers by subscription: {str(e)}")
        return None, f"Database error: {str(e)}"


# ------------UPDATES--------------
async def db_update_server_status(
    status: str,
    docker_container_id: str,
    subscription_id: str,
    ports: str,
) -> Tuple[asyncpg.Record | None, str | None]:
    """Update server status by subscription ID."""
    try:
        if not subscription_id:
            return None, "Subscription ID is required"

        result = await conn_manager(
            QUERY_TYPE.FETCHROW,
            False,
            SQL_QUERIES["UpdateServerStatus"],
            status,
            docker_container_id,
            ports,
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
) -> Tuple[asyncpg.Record | None, str | None]:
    """Update subscription status and billing dates."""
    try:
        if not subscription_id:
            return None, "Subscription ID is required"

        result = await conn_manager(
            QUERY_TYPE.FETCHROW,
            False,
            SQL_QUERIES["UpdateSubscriptionStatus"],
            status,
            subscription_id,
        )
        if not result:
            return None, "Subscription not found"
        return result, None
    except Exception as e:
        logger.error(f"Error updating subscription status: {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_update_subscription_is_trial(
    subscription_id: str, is_trial: bool
) -> Tuple[asyncpg.Record | None, str | None]:
    """Update subscription status and billing dates."""
    try:
        if not subscription_id:
            return None, "Subscription ID is required"

        result = await conn_manager(
            QUERY_TYPE.FETCHROW,
            False,
            SQL_QUERIES["UpdateSubscriptionIsTrial"],
            is_trial,
            subscription_id,
        )
        if not result:
            return None, "Subscription not found"
        return result, None
    except Exception as e:
        logger.error(f"Error updating subscription trial: {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_update_server_config(
    config: str, server_id: str
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        if not server_id:
            return None, "Server id is required"

        result = await conn_manager(
            QUERY_TYPE.FETCHROW,
            False,
            SQL_QUERIES["UpdateServerConfig"],
            config,
            server_id,
        )
        if not result:
            return None, "Server not found"
        return result, None
    except Exception as e:
        logger.error(f"Error updating config of Server {server_id}: {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_update_server_sftp(
    sftp_username, sftp_password, server_id
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        if not server_id:
            return None, "Server id is required"

        result = await conn_manager(
            QUERY_TYPE.FETCHROW,
            False,
            SQL_QUERIES["UpdateServerSftp"],
            sftp_username,
            sftp_password,
            server_id,
        )
        if not result:
            return None, "Server not found"
        return result, None
    except Exception as e:
        logger.error(f"Error on update_server_sftp Server {server_id}: {str(e)}")
        return None, f"Database error: {str(e)}"


# Initialize SQL queries on module load
try:
    load_sql_queries()
except Exception as e:
    logger.critical(f"Failed to load SQL queries: {str(e)}")
    sys.exit(1)
# loop = asyncio.get_event_loop()
# loop.run_until_complete(create_tables())
# print("done")
