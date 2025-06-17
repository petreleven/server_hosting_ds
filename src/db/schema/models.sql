-- name: CreateUserTable
CREATE TABLE IF NOT EXISTS users (id uuid PRIMARY KEY DEFAULT uuid_generate_v4(), email VARCHAR(255) UNIQUE, password VARCHAR(255), created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), exhausted_free BOOLEAN DEFAULT FALSE);
-- name: CreateGameTable
CREATE TABLE IF NOT EXISTS games (id uuid PRIMARY KEY DEFAULT uuid_generate_v4(), game_name VARCHAR(100), description TEXT, image_url VARCHAR(255), active BOOLEAN DEFAULT TRUE);
-- name: CreatePlansTable
CREATE TABLE IF NOT EXISTS plans (id uuid PRIMARY KEY DEFAULT uuid_generate_v4(), game_id uuid, plan_name VARCHAR(100), cpu_cores REAL, ram_gb REAL, storage_gb REAL, price_monthly REAL, max_players INTEGER, active BOOLEAN DEFAULT TRUE,
                                  FOREIGN KEY(game_id) REFERENCES games(id));
-- name: CreateSubscriptionsTable
CREATE TABLE IF NOT EXISTS subscriptions (id uuid PRIMARY KEY DEFAULT uuid_generate_v4(), user_id uuid, plan_id uuid, status VARCHAR(50), created_at TIMESTAMPTZ DEFAULT NOW(), expires_at TIMESTAMPTZ, last_billing_date TIMESTAMPTZ DEFAULT NOW(), next_billing_date TIMESTAMPTZ,
                                          FOREIGN KEY(user_id) REFERENCES users(id),
                                          FOREIGN KEY(plan_id) REFERENCES plans(id));
-- name: CreateBaremetalTable
CREATE TABLE IF NOT EXISTS baremetal (id uuid PRIMARY KEY DEFAULT uuid_generate_v4(), hostname VARCHAR(255), ip_address VARCHAR(45) UNIQUE, status VARCHAR(50), capacity_total REAL, capacity_used REAL);
-- name: CreateServersTable
CREATE TABLE IF NOT EXISTS servers (id uuid PRIMARY KEY DEFAULT uuid_generate_v4(), subscription_id uuid, status VARCHAR(50), ip_address VARCHAR(45), ports TEXT, docker_container_id VARCHAR(100), created_at TIMESTAMPTZ DEFAULT NOW(), config JSONB, sftp_username VARCHAR(200), sftp_password VARCHAR(200),
                                    FOREIGN KEY(subscription_id) REFERENCES subscriptions(id));
-- name: CreateTransactionsTable
CREATE TABLE IF NOT EXISTS transactions (id uuid PRIMARY KEY DEFAULT uuid_generate_v4(), user_id uuid, subscription_id uuid, amount REAL, description TEXT, created_at TIMESTAMPTZ DEFAULT NOW(), payment_method VARCHAR(50), payment_status VARCHAR(50),
                                         FOREIGN KEY(user_id) REFERENCES users(id),
                                         FOREIGN KEY(subscription_id) REFERENCES subscriptions(id));

