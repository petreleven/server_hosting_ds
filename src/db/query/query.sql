-- name: InsertUser
INSERT INTO users (email, password)
VALUES ($1,
        $2) RETURNING *
-- name: InsertSubscription
INSERT INTO subscriptions (user_id, plan_id, status, expires_at, next_billing_date, is_trial)
VALUES ($1,
        $2,
        $3,
        $4,
        $5,
        $6) RETURNING *
-- name: InsertServer
INSERT INTO servers (subscription_id, status, ip_address, ports, docker_container_id, config)
VALUES ($1,
        $2,
        $3,
        $4,
        $5,
        $6) RETURNING id,
            subscription_id,
            status,
            ip_address,
            ports,
            docker_container_id,
            config;
-- name: SelectUserByEmail
SELECT id,
       email,
       password,
       created_at
FROM users
WHERE email = $1;
-- name: SelectAllBaremetals
SELECT *
FROM baremetal;
-- name: SelectAllSubscriptions
SELECT *
FROM subscriptions
WHERE user_id = $1;
-- name: SelectAllPlansByGame
SELECT *
FROM catalog
WHERE parent_id = $1;
-- name: SelectPlanById
SELECT *
FROM catalog
WHERE id = $1;
-- name: SelectGameById
SELECT *
FROM catalog
WHERE id = $1;
-- name: SelectSubscriptionById
SELECT *
FROM subscriptions
WHERE id = $1;
-- name: SelectSubscriptionsByUser
SELECT *
FROM subscriptions
WHERE user_id = $1
ORDER BY created_at DESC;
-- name: SelectServerBySubscription
SELECT *
FROM servers
WHERE subscription_id = $1;
-- name: UpdateServerStatus
UPDATE servers
SET status = $1,
             docker_container_id = $2,
             ports = $3
WHERE subscription_id = $4 RETURNING *;
-- name: UpdateSubscriptionStatus
UPDATE subscriptions
SET status = $1
WHERE id = $2 RETURNING *;
-- name: UpdateSubscriptionIsTrial
UPDATE subscriptions
SET is_trial = $1
WHERE id = $2 RETURNING *;
-- name: UpdateServerConfig
UPDATE servers
SET config = $1
WHERE id = $2 RETURNING *;
-- name: UpdateServerSftp
UPDATE servers
SET sftp_username = $1,
    sftp_password = $2
WHERE id = $3 RETURNING *;

