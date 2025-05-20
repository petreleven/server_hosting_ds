import datetime
import logging
import os
import threading
from typing import Optional

import asyncpg
import dotenv
from asyncpg import Pool
from redis.asyncio import Redis

import custom_dataclass as cdata

dotenv.load_dotenv()


# Database connection parameters
NEON_URL = os.getenv("NEON_URL")
REDIS_URL = os.getenv("REDIS_URL")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_CLIENT: Redis | None = None


pool: Pool | None = None
_conn_lock = threading.Lock()


def get_redis_client() -> Redis:
    global REDIS_CLIENT
    if REDIS_CLIENT is None:
        REDIS_CLIENT = Redis(
            host=str(REDIS_URL),
            port=int(REDIS_PORT),
            max_connections=20,
        )
    return REDIS_CLIENT


async def get_pool() -> Pool | None:
    global pool

    with _conn_lock:
        if pool is None:
            pool = await asyncpg.create_pool(dsn=NEON_URL)
    return pool


async def db_createalldbs() -> None:
    await db_drop_table("subscriptions")
    await db_drop_table("servers")
    await db_drop_table("users")
    await db_drop_table("games")
    await db_drop_table("plans")
    await db_drop_table("baremetal")
    await db_drop_table("transactions")

    """Create all database tables if they don't exist"""
    pool: Pool | None = await get_pool()

    if not pool:
        return
    # Users table
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
            ''')
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id   uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),,
            email VARCHAR(255) UNIQUE,
            password VARCHAR(255),
            created_at TIMESTAMPTZ  DEFAULT  NOW(),
            updated_at TIMESTAMPTZ  DEFAULT  NOW()
        );""")

        # Games table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id   uuid  PRIMARY KEY DEFAULT uuid_generate_v4(),,
            game_name VARCHAR(100),
            description TEXT,
            image_url VARCHAR(255),
            active BOOLEAN  DEFAULT  TRUE
        );""")

        # Plans table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id   uuid   PRIMARY KEY DEFAULT uuid_generate_v4(),,
            game_id uuid,
            plan_name VARCHAR(100),
            cpu_cores REAL,
            ram_gb REAL,
            storage_gb REAL,
            price_monthly REAL,
            max_players INTEGER,
            active BOOLEAN DEFAULT  TRUE,
            FOREIGN KEY(game_id) REFERENCES games(id)
        );""")

        # Subscriptions table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id   uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),,
            user_id uuid,
            plan_id uuid,
            status VARCHAR(50),
            created_at  TIMESTAMPTZ  DEFAULT  NOW(),
            expires_at TIMESTAMPTZ,
            last_billing_date   TIMESTAMPTZ  DEFAULT  NOW(),
            next_billing_date TIMESTAMPTZ,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(plan_id) REFERENCES plans(id)
        );""")

        # BAREMETAL table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS baremetal (
            id   uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),,
            hostname VARCHAR(255),
            ip_address VARCHAR(45) UNIQUE,
            status VARCHAR(50),
            capacity_total REAL,
            capacity_used REAL
        );""")

        # Servers table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS servers (
            id   uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),,
            subscription_id uuid,
            status VARCHAR(50),
            ip_address VARCHAR(45),
            ports TEXT,
            docker_container_id VARCHAR(100),
            created_at TIMESTAMPTZ  DEFAULT  NOW(),
            config JSONB,
            FOREIGN KEY(subscription_id) REFERENCES subscriptions(id)
        );""")

        # Transactions table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id   uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),,
            user_id uuid,
            subscription_id uuid,
            amount REAL,
            description TEXT,
            created_at TIMESTAMPTZ  DEFAULT  NOW(),
            payment_method VARCHAR(50),
            payment_status VARCHAR(50),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(subscription_id) REFERENCES subscriptions(id)
        );""")


# ----- DROP -----


async def db_drop_table(table: str) -> None:
    """Drop a specific table if it exists."""
    pool = await get_pool()
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {table};")
    except Exception as e:
        logger = logging.getLogger("backendlogger")
        logger.error(f"Unable to drop table {table} ", e)
        pass


# ----- INSERT OPERATIONS -----


async def db_insert_user(data: cdata.RegisterUserData) -> asyncpg.Record | None:
    """Insert a new user into the database and return the new record."""
    pool = await get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO users (email, password)
            VALUES ($1, $2)
            RETURNING id, email, created_at;
            """,
            data.email,
            data.password,
        )


async def db_insert_subscription(
    user_id: str,
    plan_id: str,
    status: str,
    expires_at: datetime.datetime,
    next_billing_date: datetime.datetime,
) -> asyncpg.Record | None:
    """Insert a new subscription and return its record."""
    pool = await get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO subscriptions
            (user_id, plan_id, status, expires_at, next_billing_date)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING
            id, user_id, plan_id, status, expires_at, next_billing_date;
            """,
            user_id,
            plan_id,
            status,
            expires_at,
            next_billing_date,
        )


async def db_insert_server(
    subscription_id: str,
    status: str,
    ip_address: str,
    ports: str,
    docker_container_id: str,
    cfg: str,
) -> asyncpg.Record | None:
    """Insert a new server and return its record."""
    pool = await get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO servers
            (subscription_id, status, ip_address, ports, docker_container_id, config)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING
            id, subscription_id, status, ip_address, ports, docker_container_id, config;
            """,
            subscription_id,
            status,
            ip_address,
            ports,
            docker_container_id,
            cfg,
        )


# ----- SELECT OPERATIONS -----


async def db_select_user_by_email(email: str) -> asyncpg.Record | None:
    """Select a user by email address."""
    pool = await get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, email, password, created_at
            FROM users
            WHERE email = $1;
            """,
            email,
        )


async def db_select_all_baremetals() -> list[asyncpg.Record]:
    """Get all bare metal servers."""
    pool = await get_pool()
    if not pool:
        return []
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT *
            FROM baremetal;
            """,
        )


async def db_select_all_subscriptions(user_id: str) -> list[asyncpg.Record]:
    """Get all bare metal servers."""
    pool = await get_pool()
    if not pool:
        return []
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT *
            FROM subscriptions
            WHERE user_id=$1;
            """,
            user_id,
        )


async def db_select_plan_by_id(plan_id: str) -> asyncpg.Record | None:
    """Get a plan by its ID."""
    pool = await get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM plans
            WHERE id = $1;
            """,
            plan_id,
        )


async def db_select_game_by_id(game_id: str) -> asyncpg.Record | None:
    """Get a game by its ID."""
    pool = await get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM games
            WHERE id = $1;
            """,
            game_id,
        )


# ----- OPTIONAL ADDITIONAL SELECTS -----
async def db_select_subscription_by_id(sub_id: str) -> Optional[asyncpg.Record]:
    """List all subscriptions for a given user."""
    pool = await get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM subscriptions
            WHERE id = $1;
            """,
            sub_id,
        )


async def db_select_subscription_by_user(user_id: str) -> list[asyncpg.Record]:
    """List all subscriptions for a given user."""
    pool = await get_pool()
    if not pool:
        return []
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT *
            FROM subscriptions
            WHERE user_id = $1
            ORDER BY created_at DESC;
            """,
            user_id,
        )


async def db_select_servers_by_subscription(
    subscription_id: str,
) -> asyncpg.Record | None:
    """List all servers under a specific subscription."""
    pool = await get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM servers
            WHERE subscription_id = $1;
            """,
            subscription_id,
        )


# ------------UPDATES--------------
async def db_update_server_status(
    status: str,
    docker_container_id: str,
    subscription_id: str,
) -> asyncpg.Record | None:
    pool = await get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE servers
            SET status=$1 , docker_container_id=$2
            WHERE subscription_id=$3
            RETURNING *;
            """,
            status,
            docker_container_id,
            subscription_id,
        )


async def db_update_subscription_status(
    subscription_id: str,
    status: str,
    last_billing_date: datetime.datetime,
    next_billing_date: datetime.datetime,
) -> asyncpg.Record | None:
    pool = await get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE subscriptions
            SET status=$1, last_billing_date=$2, next_billing_date=$3
            WHERE id = $4
            RETURNING *
            """,
            status,
            last_billing_date,
            next_billing_date,
            subscription_id,
        )
