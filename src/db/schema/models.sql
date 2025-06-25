-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- For faster text searches

-- Custom types for better type safety
CREATE TYPE subscription_payment_status AS ENUM ('active', 'cancelled', 'paused', 'expired');
CREATE TYPE subscription_internal_status AS ENUM ('on', 'provisioning', 'unavailable', 'failed');
CREATE TYPE server_status AS ENUM ('provisioning', 'restarting', 'running', 'stopping', 'stopped', 'configured', 'failed', 'not_found');
CREATE TYPE baremetal_status AS ENUM ('active', 'maintenance', 'offline', 'decommissioned');

-- 1. Users table
CREATE TABLE users (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email            VARCHAR(255) UNIQUE NOT NULL,
    password         VARCHAR(255) NOT NULL, -- Store bcrypt hashed passwords
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    exhausted_free   BOOLEAN DEFAULT FALSE,
    paddle_customer_id VARCHAR(255),

    -- Constraints
    CONSTRAINT valid_email CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

-- 2. Catalog table (games and plans)
CREATE TABLE catalog (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    parent_id        UUID REFERENCES catalog(id) ON DELETE CASCADE,
    name             VARCHAR(100) NOT NULL,
    description      TEXT,
    image_url        VARCHAR(500),

    -- Plan-specific fields (NULL for games)
    cpu_cores        REAL CHECK (cpu_cores IS NULL OR cpu_cores > 0),
    ram_gb           REAL CHECK (ram_gb IS NULL OR ram_gb > 0),
    storage_gb       REAL CHECK (storage_gb IS NULL OR storage_gb > 0),
    max_players      INTEGER CHECK (max_players IS NULL OR max_players > 0),
    price_monthly    DECIMAL(10,2) CHECK (price_monthly IS NULL OR price_monthly >= 0),
    paddle_price_id  VARCHAR(255),

    active           BOOLEAN DEFAULT TRUE,
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Ensure games don't have plan-specific fields
    CONSTRAINT game_fields_check CHECK (
        (parent_id IS NULL AND cpu_cores IS NULL AND ram_gb IS NULL AND storage_gb IS NULL AND max_players IS NULL AND price_monthly IS NULL) OR
        (parent_id IS NOT NULL AND cpu_cores IS NOT NULL AND ram_gb IS NOT NULL AND storage_gb IS NOT NULL)
    )
);

-- 3. Subscriptions table
CREATE TABLE subscriptions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id             UUID NOT NULL REFERENCES catalog(id) ON DELETE RESTRICT,

    status              subscription_payment_status NOT NULL DEFAULT 'active',
    internal_status     subscription_internal_status NOT NULL DEFAULT 'provisioning',

    is_trial            BOOLEAN DEFAULT FALSE,
    trial_starts_at     TIMESTAMP WITH TIME ZONE,
    trial_expires_at    TIMESTAMP WITH TIME ZONE,

    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at          TIMESTAMP WITH TIME ZONE,
    last_billing_date   TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    next_billing_date   TIMESTAMP WITH TIME ZONE,

    -- Paddle integration
    paddle_subscription_id VARCHAR(255),
    paddle_customer_id  VARCHAR(255),

    -- Constraints
    CONSTRAINT unique_paddle_subscription UNIQUE (paddle_subscription_id),
    CONSTRAINT trial_dates_check CHECK (
        (is_trial = FALSE) OR
        (is_trial = TRUE AND trial_starts_at IS NOT NULL AND trial_expires_at IS NOT NULL AND trial_expires_at > trial_starts_at)
    ),
    CONSTRAINT billing_dates_check CHECK (next_billing_date > last_billing_date)
);

-- 4. Transactions table
CREATE TABLE transactions (
    id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subscription_id        UUID REFERENCES subscriptions(id) ON DELETE SET NULL,

    amount                 DECIMAL(10,2) NOT NULL CHECK (amount >= 0),
    description            TEXT NOT NULL,
    payment_method         VARCHAR(50) NOT NULL,
    payment_status         VARCHAR(50) NOT NULL,

    created_at             TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    paddle_transaction_id  VARCHAR(255) UNIQUE,

    -- Add metadata for better tracking
    currency               CHAR(3) DEFAULT 'USD',
    refunded               BOOLEAN DEFAULT FALSE,
    refund_amount          DECIMAL(10,2) DEFAULT 0 CHECK (refund_amount >= 0 AND refund_amount <= amount)
);

-- 5. Baremetal hosts table
CREATE TABLE baremetal (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hostname         VARCHAR(255) NOT NULL UNIQUE,
    ip_address       INET NOT NULL UNIQUE, -- Use INET type for IP addresses
    status           baremetal_status NOT NULL DEFAULT 'active',

    -- Resource tracking
    capacity_total   REAL NOT NULL CHECK (capacity_total > 0),
    capacity_used    REAL NOT NULL DEFAULT 0 CHECK (capacity_used >= 0 AND capacity_used <= capacity_total),

    -- Metadata
    region           VARCHAR(50),
    datacenter       VARCHAR(100),
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_health_check TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. Servers table
CREATE TABLE servers (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subscription_id      UUID NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    baremetal_id         UUID REFERENCES baremetal(id) ON DELETE SET NULL,

    status               server_status NOT NULL DEFAULT 'provisioning',
    ip_address           INET,
    ports                JSONB, -- Store ports as JSON for better structure
    docker_container_id  VARCHAR(100),

    -- Configuration and access
    config               JSONB, -- Store config as JSON
    sftp_username        VARCHAR(200),
    sftp_password        VARCHAR(200), -- Consider encrypting this

    -- Timestamps
    created_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed        TIMESTAMP WITH TIME ZONE,

    -- Resource usage tracking
    cpu_usage_percent    REAL CHECK (cpu_usage_percent >= 0 AND cpu_usage_percent <= 100),
    memory_usage_mb      INTEGER CHECK (memory_usage_mb >= 0),
    storage_usage_gb     REAL CHECK (storage_usage_gb >= 0),

    -- Ensure one server per subscription
    CONSTRAINT unique_subscription_server UNIQUE (subscription_id)
);

-- Performance Indexes
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_paddle_customer ON users(paddle_customer_id) WHERE paddle_customer_id IS NOT NULL;
CREATE INDEX idx_catalog_parent_id ON catalog(parent_id);
CREATE INDEX idx_catalog_active ON catalog(active) WHERE active = true;
CREATE INDEX idx_catalog_game_plans ON catalog(parent_id, active) WHERE active = true;
CREATE INDEX idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);
CREATE INDEX idx_subscriptions_internal_status ON subscriptions(internal_status);
CREATE INDEX idx_subscriptions_paddle_id ON subscriptions(paddle_subscription_id) WHERE paddle_subscription_id IS NOT NULL;
CREATE INDEX idx_subscriptions_expires_at ON subscriptions(expires_at);
CREATE INDEX idx_subscriptions_user_status ON subscriptions(user_id, status);
