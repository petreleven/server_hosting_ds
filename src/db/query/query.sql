-- name: InsertUser
INSERT INTO users (email, password)
VALUES ($1,
        $2) RETURNING id,
            email,
            created_at;
-- name: InsertSubscription
INSERT INTO subscriptions (user_id, plan_id, status, expires_at, next_billing_date)
VALUES ($1,
        $2,
        $3,
        $4,
        $5) RETURNING id,
            user_id,
            plan_id,
            status,
            expires_at,
            next_billing_date;
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
-- name: SelectPlanById
SELECT *
FROM plans
WHERE id = $1;
-- name: SelectGameById
SELECT *
FROM games
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
-- name: SelectServersBySubscription
SELECT *
FROM servers
WHERE subscription_id = $1;
-- name: UpdateServerStatus
UPDATE servers
SET status = $1,
             docker_container_id = $2
WHERE subscription_id = $3 RETURNING *;
-- name: UpdateSubscriptionStatus
UPDATE subscriptions
SET status = $1,
             last_billing_date = $2,
                                 next_billing_date = $3
WHERE id = $4 RETURNING *;

