import asyncio
import datetime
import logging
import re
import os
import sys
import bcrypt
from typing import Any, Dict, List, Optional, Tuple
from contextlib import asynccontextmanager

import asyncpg
import dotenv
from asyncpg import Pool, Record
from redis.asyncio import Redis
from pathlib import Path
import enum


sys.path.append(str(Path(__file__).parent.parent))

import helper_classes.custom_dataclass as cdata

dotenv.load_dotenv()

# Configure logger
logger = logging.getLogger("backendlogger")

# Database connection parameters
DATABASE_URL = (
    os.getenv("DATABASE_URL") or os.getenv("NEON_URL") or os.getenv("PG_LOCAL")
)
REDIS_URL = os.getenv("REDIS_URL")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

if not DATABASE_URL:
    logger.error("No database URL found in environment variables")
    raise ValueError("DATABASE_URL, NEON_URL, or PG_LOCAL must be set")

REDIS_CLIENT: Redis | None = None
SQL_QUERIES: Dict[str, str] = {}
pool: Pool | None = None
_pool_lock = asyncio.Lock()


class QUERY_TYPE(enum.Enum):
    EXECUTE = "execute"
    FETCH = "fetch"
    FETCHROW = "fetchrow"


class INTERNAL_SUBSCRIPTION_STATUS(enum.Enum):
    """Subscription flags for servers - internal use only"""

    ON = "on"
    PROVISIONING = "provisioning"
    UNAVAILABLE = "unavailable"
    FAILED = "failed" #will need user to report this can be miscellanious or important


class SUBSCRIPTION_STATUS(enum.Enum):
    """Subscription payment status"""

    ACTIVE = "active"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    EXPIRED = "expired"


class SERVER_STATUS(enum.Enum):
    """Server status enumeration"""

    PROVISIONING = "provisioning"
    RESTARTING = "restarting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    CONFIGURED = "configured"
    FAILED = "failed"
    NOT_FOUND = "not_found"


# Password Security Functions
def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# Redis Connection
async def get_redis_client() -> Redis:
    """Get Redis client with connection pooling"""
    global REDIS_CLIENT
    if REDIS_CLIENT is None:
        try:
            REDIS_CLIENT = Redis(
                host=str(REDIS_URL),
                port=REDIS_PORT,
                max_connections=20,
                decode_responses=True,
                retry_on_timeout=True,
            )
            # Test connection
            await REDIS_CLIENT.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to create Redis client: {str(e)}")
            raise
    return REDIS_CLIENT


def load_sql_queries() -> None:
    """Load SQL queries from files into memory with better error handling"""
    try:
        queries_path = Path(__file__).parent / "query" / "query.sql"

        if not queries_path.exists():
            logger.error(f"SQL file not found: {queries_path}")
            raise FileNotFoundError(f"SQL file not found: {queries_path}")

        data = queries_path.read_text().strip()

        # Split queries by -- name: pattern
        all_statements = re.split(r"-- name:\s*(\w+)", data)[1:]

        if len(all_statements) % 2 != 0:
            logger.error(
                "Invalid SQL file format - mismatched query names and statements"
            )
            raise ValueError("Invalid SQL file format")

        # Parse name-query pairs
        for i in range(0, len(all_statements), 2):
            query_name = all_statements[i].strip()
            query_sql = all_statements[i + 1].strip()

            if not query_name or not query_sql:
                logger.warning(f"Empty query name or SQL for index {i}")
                continue

            SQL_QUERIES[query_name] = query_sql

        logger.info(f"Loaded {len(SQL_QUERIES)} SQL queries")

        # Log loaded query names for debugging
        logger.debug(f"Available queries: {list(SQL_QUERIES.keys())}")

    except Exception as e:
        logger.error(f"Error loading SQL queries: {str(e)}")
        raise


async def get_pool() -> Pool:
    """Get or create database connection pool with improved error handling"""
    global pool

    async with _pool_lock:
        if pool is None:
            try:
                pool = await asyncpg.create_pool(
                    dsn=DATABASE_URL,
                    min_size=5,
                    max_size=20,
                    command_timeout=60,
                    server_settings={
                        "jit": "off"  # Disable JIT for better performance on simple queries
                    },
                )
                logger.info("Database connection pool created")

                # Test the connection
                async with pool.acquire() as conn:
                    await conn.execute("SELECT 1")

            except Exception as e:
                logger.error(f"Failed to create connection pool: {str(e)}")
                raise RuntimeError(f"Database connection failed: {str(e)}")

    return pool


@asynccontextmanager
async def get_db_connection():
    """Context manager for database connections"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def execute_query(
    query_type: QUERY_TYPE, query_name: str, *args, use_transaction: bool = False
) -> Any:
    """
    Execute database queries with improved error handling and logging

    Args:
        query_type: Type of query to execute
        query_name: Name of the query from SQL_QUERIES
        *args: Query parameters
        use_transaction: Whether to use a transaction

    Returns:
        Query result based on query_type
    """
    if query_name not in SQL_QUERIES:
        logger.error(f"Query '{query_name}' not found in loaded queries")
        raise ValueError(f"Unknown query: {query_name}")

    query_sql = SQL_QUERIES[query_name]

    try:
        async with get_db_connection() as conn:
            if use_transaction:
                async with conn.transaction():
                    return await _execute_query_by_type(
                        conn, query_type, query_sql, args
                    )
            else:
                return await _execute_query_by_type(conn, query_type, query_sql, args)

    except asyncpg.PostgresError as e:
        logger.error(f"Database error in {query_name}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in {query_name}: {e}")
        raise


async def _execute_query_by_type(
    conn, query_type: QUERY_TYPE, query_sql: str, args: tuple
) -> Any:
    """Execute query based on type"""
    match query_type:
        case QUERY_TYPE.EXECUTE:
            return await conn.execute(query_sql, *args)
        case QUERY_TYPE.FETCH:
            return await conn.fetch(query_sql, *args)
        case QUERY_TYPE.FETCHROW:
            return await conn.fetchrow(query_sql, *args)
        case _:
            raise ValueError(f"Unknown query type: {query_type}")


# USER OPERATIONS
async def db_insert_user(
    data: cdata.RegisterUserData,
) -> Tuple[Optional[Record], Optional[str]]:
    """Insert a new user with hashed password"""
    try:
        hashed_password = hash_password(data.password)

        result = await execute_query(
            QUERY_TYPE.FETCHROW,
            "InsertUser",
            data.email,
            hashed_password,
            use_transaction=True,
        )
        return result, None

    except asyncpg.UniqueViolationError:
        logger.warning(f"Attempt to create duplicate user: {data.email}")
        return None, "User with that email already exists"
    except Exception as e:
        logger.error(f"Error inserting user: {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_authenticate_user(
    email: str, password: str
) -> Tuple[Optional[Record], Optional[str]]:
    """Authenticate user by email and password"""
    try:
        user = await execute_query(QUERY_TYPE.FETCHROW, "SelectUserByEmail", email)

        if not user:
            return None, "User not found"

        if not verify_password(password, user["password"]):
            return None, "Invalid password"

        # Return user without password field - create a new dict to avoid modifying the original
        user_dict = dict(user)
        user_dict["password"] = ""
        return user_dict, None

    except Exception as e:
        logger.error(f"Error authenticating user: {str(e)}")
        return None, f"Authentication error: {str(e)}"


async def db_select_user_by_email(email: str) -> Tuple[Optional[Record], Optional[str]]:
    """Select user by email (without password)"""
    try:
        if not email:
            return None, "Email is required"

        result = await execute_query(QUERY_TYPE.FETCHROW, "SelectUserByEmail", email)
        if result:
            # Remove password from result - create a new dict to avoid modifying the original
            result_dict = dict(result)
            result_dict["password"] = ""
            return result_dict, None
        return None, "User not found"

    except Exception as e:
        logger.error(f"Error selecting user by email: {str(e)}")
        return None, f"Database error: {str(e)}"


# SUBSCRIPTION OPERATIONS
async def db_insert_free_subscription(
    user_id: str,
    plan_id: str,
    internal_status: str,
    trial_starts_at,
    trial_expires_at,
    status: str,
    expires_at: datetime.datetime,
    next_billing_date: datetime.datetime,
    is_trial: bool = False,
) -> Tuple[Optional[Record], Optional[str]]:
    """Insert a new subscription"""
    try:
        result = await execute_query(
            QUERY_TYPE.FETCHROW,
            "InsertFreeSubscription",
            user_id,
            plan_id,
            status,
            internal_status,
            trial_starts_at,
            trial_expires_at,
            expires_at,
            next_billing_date,
            is_trial,
            use_transaction=True,
        )
        return result, None

    except asyncpg.ForeignKeyViolationError:
        logger.warning(f"Foreign key violation: user_id={user_id}, plan_id={plan_id}")
        return None, "User or plan does not exist"
    except Exception as e:
        logger.error(f"Error inserting subscription: {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_select_subscriptions_by_user(
    user_id: str,
) -> Tuple[List[Record], Optional[str]]:
    """Get all subscriptions for a user with plan details"""
    try:
        if not user_id:
            return [], "User ID is required"

        result = await execute_query(
            QUERY_TYPE.FETCH, "SelectAllSubscriptions", user_id
        )
        return result or [], None

    except Exception as e:
        logger.error(f"Error selecting subscriptions: {str(e)}")
        return [], f"Database error: {str(e)}"


# SERVER OPERATIONS
async def db_insert_server(
    subscription_id: str,
    status: str,
    ip_address: str = "",
    ports: str = "",
    docker_container_id: str = "",
    config: str = "",
) -> Tuple[Optional[Record], Optional[str]]:
    """Insert a new server"""
    try:
        if not subscription_id:
            return None, "Subscription ID is required"

        result = await execute_query(
            QUERY_TYPE.FETCHROW,
            "InsertServer",
            subscription_id,
            status,
            ip_address,
            ports,
            docker_container_id,
            config,
            use_transaction=True,
        )
        return result, None

    except asyncpg.ForeignKeyViolationError:
        logger.warning(f"Foreign key violation: subscription_id={subscription_id}")
        return None, "Subscription does not exist"
    except Exception as e:
        logger.error(f"Error inserting server: {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_update_server_status(
    subscription_id: str,
    status: str,
    docker_container_id: str = "",
    ports: str = "",
) -> Tuple[Optional[Record], Optional[str]]:
    """Update server status"""
    try:
        if not subscription_id:
            return None, "Subscription ID is required"

        result = await execute_query(
            QUERY_TYPE.FETCHROW,
            "UpdateServerStatus",
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


# CATALOG OPERATIONS
async def db_select_games() -> Tuple[List[Record], Optional[str]]:
    """Get all available games"""
    try:
        result = await execute_query(QUERY_TYPE.FETCH, "SelectAllGames")
        return result or [], None

    except Exception as e:
        logger.error(f"Error selecting games: {str(e)}")
        return [], f"Database error: {str(e)}"


async def db_select_plans_by_game(game_id: str) -> Tuple[List[Record], Optional[str]]:
    """Get all plans for a specific game"""
    try:
        if not game_id:
            return [], "Game ID is required"

        result = await execute_query(QUERY_TYPE.FETCH, "SelectAllPlansByGame", game_id)
        return result or [], None

    except Exception as e:
        logger.error(f"Error selecting plans: {str(e)}")
        return [], f"Database error: {str(e)}"


async def db_select_subscription_by_id(
    subscription_id: str,
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        if not subscription_id:
            return None, "Subscription ID is required"
        result = await execute_query(
            QUERY_TYPE.FETCHROW, "SelectSubscriptionById", subscription_id
        )
        return result or None, None
    except Exception as e:
        logger.error(f"Error selecting subscription : {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_select_server_by_subscription_id(
    subscription_id: str,
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        if not subscription_id:
            return None, "Subscription ID is required"
        result = await execute_query(
            QUERY_TYPE.FETCHROW, "SelectServerBySubscription", subscription_id
        )
        return result or None, None
    except Exception as e:
        logger.error(f"Error selecting server by subscription_id : {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_select_server_by_id(
    server_id: str,
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        if not server_id:
            return None, "Server ID is required"
        result = await execute_query(QUERY_TYPE.FETCHROW, "SelectServerById", server_id)
        return result or None, None
    except Exception as e:
        logger.error(f"Error selecting server by server_id : {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_select_plan_by_id(
    plan_id: str,
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        if not plan_id:
            return None, "Plan ID is required"
        result = await execute_query(QUERY_TYPE.FETCHROW, "SelectPlanById", plan_id)
        return result or None, None
    except Exception as e:
        logger.error(f"Error selecting plan by id : {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_select_game_by_id(
    game_id: str,
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        if not game_id:
            return None, "Game ID is required"
        result = await execute_query(QUERY_TYPE.FETCHROW, "SelectGameById", game_id)
        return result or None, None
    except Exception as e:
        logger.error(f"Error selecting game by id : {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_insert_subscription_with_payment(
    user_id: str,
    plan_id: str,
    status: str,
    paddle_subscription_id: str,
    paddle_customer_id: str,
    expires_at: datetime.datetime,
    next_billing_date: datetime.datetime,
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        result = await execute_query(
            QUERY_TYPE.FETCHROW,
            "InsertSubscriptionWithPayment",
            user_id,
            plan_id,
            status,
            paddle_subscription_id,
            paddle_customer_id,
            expires_at,
            next_billing_date,
            False,  # Changed from FALSE to False
        )
        return result or None, None
    except Exception as e:
        logger.error(f"Error db_insert_subscription_with_payment  : {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_update_subscription_internal_status(
    subscription_id: str, internal_status: str
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        if not subscription_id:
            return None, "Subscription ID is required"
        result = await execute_query(
            QUERY_TYPE.FETCHROW,
            "UpdateSubscriptionInternalStatus",
            internal_status,
            subscription_id,
        )
        return result or None, None
    except Exception as e:
        logger.error(f"Error updating subscription_internal_status : {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_update_subscription_is_trial(
    is_trial: bool,
    subscription_id: str,
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        if not subscription_id:
            return None, "Subscription ID is required"
        result = await execute_query(
            QUERY_TYPE.FETCHROW, "UpdateSubscriptionIsTrial", is_trial, subscription_id
        )
        return result or None, None
    except Exception as e:
        logger.error(f"Error in db_update_subscription_is_trial  : {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_cancel_subscription(
    paddle_subscription_id: str,
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        if not paddle_subscription_id:
            return None, "paddle_subscription_id is required"
        result = await execute_query(
            QUERY_TYPE.FETCHROW,
            "CancelSubscription",
            SUBSCRIPTION_STATUS.CANCELLED.value,  # Use .value to get the string
            paddle_subscription_id,
        )
        return result or None, None
    except Exception as e:
        logger.error(f"Error in db_cancel_subscription  : {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_mark_subscription_expired(
    paddle_subscription_id: str, user_id: str
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        if not paddle_subscription_id or not user_id:
            return None, "paddle_subscription_id and user_id is required"
        result = await execute_query(
            QUERY_TYPE.FETCHROW,
            "MarkSubscriptionExpired",
            SUBSCRIPTION_STATUS.EXPIRED.value,  # Use .value to get the string
            paddle_subscription_id,
            user_id,
        )
        return result or None, None
    except Exception as e:
        logger.error(f"Error in db_mark_subscription_expired : {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_mark_subscription_paused(
    paddle_subscription_id: str, user_id: str
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        if not paddle_subscription_id or not user_id:
            return None, "paddle_subscription_id and user_id is required"
        result = await execute_query(
            QUERY_TYPE.FETCHROW,
            "MarkSubscriptionPaused",
            SUBSCRIPTION_STATUS.PAUSED.value,  # Changed from EXPIRED to PAUSED and use .value
            paddle_subscription_id,
            user_id,
        )
        return result or None, None
    except Exception as e:
        logger.error(f"Error in db_mark_subscription_paused  : {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_update_subscription(
    status: str,
    plan_id: str,
    next_billing_date: datetime.datetime,
    expires_at: datetime.datetime,
    paddle_subscription_id: str,
    user_id: str,
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        result = await execute_query(
            QUERY_TYPE.FETCHROW,
            "UpdateSubscription",
            status,
            plan_id,
            next_billing_date,
            expires_at,
            paddle_subscription_id,
            user_id,
        )
        return result or None, None
    except Exception as e:
        logger.error(f"Error in db_update_subscription : {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_update_server_sftp(
    sftp_username: str, sftp_password: str, server_id: str
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        if not server_id:
            return None, "Server ID is required"
        result = await execute_query(
            QUERY_TYPE.FETCHROW,
            "UpdateServerSftp",
            sftp_username,
            sftp_password,
            server_id,
        )
        return result or None, None
    except Exception as e:
        logger.error(f"Error in db_update_server_sftp  : {str(e)}")
        return None, f"Database error: {str(e)}"


async def db_select_all_baremetals() -> Tuple[List[Record], Optional[str]]:
    try:
        result = await execute_query(QUERY_TYPE.FETCH, "SelectAllBaremetals")
        return result or [], None
    except Exception as e:
        logger.error(f"Error in db_select_all_baremetals : {str(e)}")
        return [], f"Database error: {str(e)}"


async def db_update_server_config(
    config: str, server_id: str
) -> Tuple[Optional[Record], Optional[str]]:
    try:
        if not server_id:
            return None, "Server ID is required"
        result = await execute_query(
            QUERY_TYPE.FETCHROW,
            "UpdateServerConfig",
            config,
            server_id,
        )
        return result or None, None
    except Exception as e:
        logger.error(f"Error in db_update_server_config  : {str(e)}")
        return None, f"Database error: {str(e)}"


# DATABASE INITIALIZATION
async def initialize_database():
    """Initialize database with all tables"""
    global pool
    try:
        # Load queries first
        load_sql_queries()

        # Test connection
        pool = await get_pool()
        # models_path = Path(__file__).parent / "schema" / "models.sql"
        # async with pool.acquire() as conn:
        #     await conn.execute(models_path.read_text())

        logger.info("Database initialized successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise


# loop = asyncio.new_event_loop()
# loop.run_until_complete(initialize_database())

# Initialize on module load
try:
    load_sql_queries()
except Exception as e:
    logger.critical(f"Failed to load SQL queries on module import: {str(e)}")
    sys.exit(1)
