-- name: InsertUser
INSERT INTO users (email, password)
VALUES ($1, $2)
RETURNING id, email, created_at, updated_at, exhausted_free, paddle_customer_id;

-- name: InsertSubscription
INSERT INTO subscriptions (user_id, plan_id, status, internal_status, expires_at, next_billing_date, is_trial)
VALUES ($1, $2, $3, $4, $5, $6, $7)
RETURNING *;

-- name: InsertSubscriptionWithPayment
INSERT INTO subscriptions (user_id, plan_id, status, paddle_subscription_id, paddle_customer_id, expires_at, next_billing_date, is_trial)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
RETURNING *;

-- name: InsertServer
INSERT INTO servers (subscription_id, status, ip_address, ports, docker_container_id, config)
VALUES ($1, $2, $3, $4, $5, $6)
RETURNING *;

-- name: InsertTransaction
INSERT INTO transactions (user_id, subscription_id, amount, description, payment_method, payment_status, created_at, paddle_transaction_id)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
RETURNING *;

-- name: SelectUserByEmail
SELECT id, email, password, created_at, updated_at, exhausted_free, paddle_customer_id
FROM users
WHERE email = $1;

-- name: SelectUserById
SELECT id, email, created_at, updated_at, exhausted_free, paddle_customer_id
FROM users
WHERE id = $1;

-- name: SelectAllBaremetals
SELECT id, hostname, ip_address, status, capacity_total, capacity_used
FROM baremetal
WHERE status = 'active'
ORDER BY capacity_used ASC;

-- name: SelectAllSubscriptions
SELECT s.*, c.name as plan_name, c.price_monthly
FROM subscriptions s
JOIN catalog c ON s.plan_id = c.id
WHERE s.user_id = $1
ORDER BY s.created_at DESC;

-- name: SelectAllPlansByGame
SELECT id, name, description, image_url, cpu_cores, ram_gb, storage_gb, max_players, price_monthly, paddle_price_id
FROM catalog
WHERE parent_id = $1 AND active = true
ORDER BY price_monthly ASC;

-- name: SelectAllGames
SELECT id, name, description, image_url
FROM catalog
WHERE parent_id IS NULL AND active = true
ORDER BY name ASC;

-- name: SelectPlanById
SELECT *
FROM catalog
WHERE id = $1 AND active = true;

-- name: SelectGameById
SELECT *
FROM catalog
WHERE id = $1 AND parent_id IS NULL AND active = true;

-- name: SelectSubscriptionById
SELECT s.*, c.name as plan_name, c.cpu_cores, c.ram_gb, c.storage_gb, c.max_players
FROM subscriptions s
JOIN catalog c ON s.plan_id = c.id
WHERE s.id = $1;

-- name: SelectSubscriptionsByUser
SELECT s.*, c.name as plan_name, c.price_monthly
FROM subscriptions s
JOIN catalog c ON s.plan_id = c.id
WHERE s.user_id = $1
ORDER BY s.created_at DESC;

-- name: SelectServerBySubscription
SELECT *
FROM servers
WHERE subscription_id = $1;

-- name: SelectServerById
SELECT *
FROM servers
WHERE id = $1;

-- name: SelectSubscriptionByPaddleId
SELECT s.*, c.name as plan_name
FROM subscriptions s
JOIN catalog c ON s.plan_id = c.id
WHERE s.paddle_subscription_id = $1;

-- name: SelectActiveSubscriptionsByUser
SELECT s.*, c.name as plan_name
FROM subscriptions s
JOIN catalog c ON s.plan_id = c.id
WHERE s.user_id = $1 AND s.status = 'active'
ORDER BY s.created_at DESC;

-- name: SelectExpiredSubscriptions
SELECT *
FROM subscriptions
WHERE status = 'active' AND expires_at < NOW();

-- name: SelectTransactionsByUser
SELECT *
FROM transactions
WHERE user_id = $1
ORDER BY created_at DESC
LIMIT $2 OFFSET $3;

-- name: UpdateServerStatus
UPDATE servers
SET status = $1,
    docker_container_id = $2,
    ports = $3
WHERE subscription_id = $4
RETURNING *;

-- name: UpdateSubscriptionStatus
UPDATE subscriptions
SET status = $1
WHERE id = $2
RETURNING *;

-- name: UpdateSubscriptionInternalStatus
UPDATE subscriptions
SET internal_status = $1
WHERE id = $2
RETURNING *;

-- name: UpdateSubscriptionIsTrial
UPDATE subscriptions
SET is_trial = $1
WHERE id = $2
RETURNING *;

-- name: UpdateServerConfig
UPDATE servers
SET config = $1
WHERE id = $2
RETURNING *;

-- name: UpdateServerSftp
UPDATE servers
SET sftp_username = $1,
    sftp_password = $2
WHERE id = $3
RETURNING *;

-- name: UpdateSubscription
UPDATE subscriptions
SET status = $1,
    plan_id = $2,
    next_billing_date = $3,
    expires_at = $4
WHERE paddle_subscription_id = $5 AND user_id = $6
RETURNING *;

-- name: CancelSubscription
UPDATE subscriptions
SET status = $1
WHERE paddle_subscription_id = $2
RETURNING *;

-- name: MarkSubscriptionExpired
UPDATE subscriptions
SET status = $1
WHERE paddle_subscription_id = $2 AND user_id = $3
RETURNING *;

-- name: MarkSubscriptionPaused
UPDATE subscriptions
SET status = $1
WHERE paddle_subscription_id = $2 AND user_id = $3
RETURNING *;

-- name: UpdateUserExhaustedFree
UPDATE users
SET exhausted_free = $1
WHERE id = $2
RETURNING *;

-- name: UpdateUserPaddleCustomerId
UPDATE users
SET paddle_customer_id = $1
WHERE id = $2
RETURNING *;

-- name: DeleteServer
DELETE FROM servers
WHERE id = $1
RETURNING *;

-- name: SoftDeleteSubscription
UPDATE subscriptions
SET status = 'cancelled'
WHERE id = $1
RETURNING *;
