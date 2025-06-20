-- CUserst
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE TABLE users (
id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
email            VARCHAR(255) UNIQUE NOT NULL,
password         VARCHAR(255) NOT NULL,
created_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
updated_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
exhausted_free   BOOLEAN DEFAULT FALSE,
paddle_customer_id VARCHAR(255)
);
-- 2. Catalog table (games and plans together)
CREATE TABLE catalog (
id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
parent_id        UUID,                          -- NULL means this row is a Game; otherwise it's a Plan
name             VARCHAR(100) NOT NULL,
description      TEXT,
image_url        VARCHAR(255),
cpu_cores        REAL,                          -- only for Plans
ram_gb           REAL,
storage_gb       REAL,
max_players      INTEGER,
price_monthly    REAL,
paddle_price_id  VARCHAR(255),
active           BOOLEAN DEFAULT TRUE,
FOREIGN KEY (parent_id) REFERENCES catalog(id)
);

-- 3. Subscriptions table
CREATE TABLE subscriptions (
id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
user_id             UUID NOT NULL,
plan_id             UUID NOT NULL,
status              VARCHAR(50) DEFAULT 'trial',   -- e.g. 'provisioning', 'unavailable','trial', 'active', 'expired'
is_trial            BOOLEAN DEFAULT FALSE,
trial_starts_at     TIMESTAMP WITH TIME ZONE,
trial_expires_at    TIMESTAMP WITH TIME ZONE,
created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
expires_at          TIMESTAMP WITH TIME ZONE,
last_billing_date   TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
next_billing_date   TIMESTAMP WITH TIME ZONE,
paddle_subscription_id VARCHAR(255),
paddle_customer_id  VARCHAR(255),
FOREIGN KEY (user_id) REFERENCES users(id),
FOREIGN KEY (plan_id) REFERENCES catalog(id)
);

-- 4. Transactions table
CREATE TABLE transactions (
id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
user_id                UUID,
subscription_id        UUID,
amount                 REAL,
description            TEXT,
payment_method         VARCHAR(50),
payment_status         VARCHAR(50),
created_at             TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
paddle_transaction_id  VARCHAR(255),
FOREIGN KEY (user_id) REFERENCES users(id),
FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
);

-- 5. Baremetal hosts table
CREATE TABLE baremetal (
id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
hostname         VARCHAR(255),
ip_address       VARCHAR(45) UNIQUE,
status           VARCHAR(50),
capacity_total   REAL,
capacity_used    REAL
);

-- 6. Servers table (linked to subscriptions)
CREATE TABLE servers (
id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
subscription_id      UUID NOT NULL,
status               VARCHAR(50), -- provisioning, restarting, stopping, stopped, running
ip_address           VARCHAR(45),
ports                TEXT,
docker_container_id  VARCHAR(100),
created_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
config               TEXT,
sftp_username        VARCHAR(200),
sftp_password        VARCHAR(200),
FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
);
