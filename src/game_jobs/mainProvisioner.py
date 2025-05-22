import datetime
import logging
from typing import Any, Dict, Optional

import asyncpg

import custom_dataclass as cdata
from db import db
from game_jobs.provisioner_factory import ProvisionerFactory


class MainProvisioner:
    """Main provisioner class that orchestrates the provisioning of game servers.
    Uses a factory pattern to create game-specific provisioners.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger("backendlogger")
        self.redisClient = db.get_redis_client()
        # Load all available provisioners
        ProvisionerFactory.load_provisioners()

    async def job_update_config(
        self,
        server_id: str,
        game_server_ip: str,
        game_name: str,
        subscription_id: str,
        config_values: dict,
    ) -> None:
        """Update the configuration for a running game server.

        Args:
            server_id: The ID of the server in the database
            game_server_ip: The IP address of the game server
            game_name: The name of the game
            subscription_id: The subscription ID associated with the server
            config_values: The configuration values to update

        """
        provisioner = ProvisionerFactory.get_provisioner(game_name)
        if not provisioner:
            self.logger.error(f"No provisioner found for game: {game_name}")
            return

        await provisioner.job_update_config(
            server_id,
            game_server_ip,
            game_name,
            subscription_id,
            config_values,
        )

    async def job_notify_admin(self, msg: str) -> None:
        """Send a notification to the admin.

        Args:
            msg: The message to send

        """
        # Implementation for admin notifications

    async def job_order_new_server(self, data: cdata.RegisterUserData) -> None:
        """Orchestrates the provisioning of a new game server for a registered user.

        Args:
            data: The registration data for the user

        """
        print(data)
        user_id = await self._get_user_id(data.email)
        if user_id is None:
            self.logger.warning("User not found for email %s", data.email)
            return

        subscription = await self._create_subscription(user_id, data.plan_id)
        if subscription is None:
            self.logger.error("Failed to create subscription for user %d", user_id)
            return

        plan = await self._get_plan(data.plan_id)
        if plan is None:
            self.logger.error("Plan %s not found", data.plan_id)
            return

        game_name = await self._get_game_name(plan.get("game_id"))
        if not game_name:
            self.logger.error("Game not found for plan %s", data.plan_id)
            return

        # Get the provisioner for this game
        provisioner = ProvisionerFactory.get_provisioner(game_name)
        if not provisioner:
            self.logger.error(f"No provisioner found for game: {game_name}")
            return

        # Get default configuration for this game
        cfg = await provisioner.get_default_config()

        baremetal = await self._find_available_baremetal(plan.get("ram_gb"))
        if baremetal is None:
            self.logger.warning("No baremetal with enough capacity")
            return

        await self._provision_server(
            subscription_id=subscription.get("id"),
            baremetal=baremetal,
            game_name=game_name,
            plan=plan,
            provisioner=provisioner,
            cfg=cfg,
        )

    async def _get_user_id(self, email: str) -> str | None:
        """Get the user ID for the given email."""
        record, err = await db.db_select_user_by_email(email)
        if not record:
            return None
        user_id = record.get("id")
        return user_id if user_id else None

    async def _create_subscription(
        self,
        user_id: str,
        plan_id: str,
    ) -> asyncpg.Record | None:
        """Create a subscription for the user."""
        now = datetime.datetime.now(datetime.UTC)
        expire_at = now + datetime.timedelta(hours=12)
        res, _ = await db.db_insert_subscription(
            user_id=user_id,
            plan_id=plan_id,
            status="provisioning",
            expires_at=expire_at,
            next_billing_date=now,
        )
        return res

    async def _get_plan(self, plan_id: str) -> asyncpg.Record | None:
        """Get the plan for the given plan ID."""
        res, _ = await db.db_select_plan_by_id(plan_id)
        return res

    async def _get_game_name(self, game_id: str | None) -> str | None:
        """Get the game name for the given game ID."""
        if game_id is None:
            return None
        record, _ = await db.db_select_game_by_id(game_id)
        return record.get("game_name") if record else None

    async def _find_available_baremetal(
        self,
        ram_needed: int | None,
    ) -> asyncpg.Record | None:
        """Find an available baremetal server with enough capacity."""
        if ram_needed is None:
            return None
        baremetals, _ = await db.db_select_all_baremetals()
        for bm in baremetals:
            total = bm.get("capacity_total") or 0
            used = bm.get("capacity_used") or 0
            if total - used >= ram_needed:
                return bm
        return None

    async def _provision_server(
        self,
        subscription_id: str,
        baremetal: asyncpg.Record,
        game_name: str,
        plan: asyncpg.Record,
        provisioner,
        cfg: str,
    ) -> None:
        """Provision a new game server.

        Args:
            subscription_id: The subscription ID for the user
            baremetal: The baremetal server to provision on
            game_name: The name of the game
            plan: The plan for the subscription
            provisioner: The game-specific provisioner
            cfg: The default configuration for the game

        """
        ip = baremetal.get("ip_address")
        if not ip:
            self.logger.error("Baremetal record missing IP")
            return

        # Get required ports from the game provisioner
        ports = provisioner.get_required_ports()

        server, _ = await db.db_insert_server(
            subscription_id=subscription_id,
            status="provisioning",
            ip_address=ip,
            ports=",".join(str(p) for p in ports),
            docker_container_id="-",
            cfg=cfg,
        )
        if not server:
            self.logger.error(
                "Failed to record server in DB for subscription %d",
                subscription_id,
            )
            return

        payload = self._build_payload(
            user_id=subscription_id,
            ports=ports,
            game_name=game_name,
            ram_gb=plan.get("ram_gb"),
            cpu_cores=plan.get("cpu_cores"),
        )
        queue = f"badger:pending:{ip}"
        await self.redisClient.lpush(queue, payload)
        self.logger.info("Server provisioning queued: %s", payload)

    def _build_payload(
        self,
        user_id: str,
        ports: list[int],
        game_name: str,
        ram_gb: int,
        cpu_cores: int,
    ) -> str:
        """Build the payload for the provisioning job."""
        port_args = " ".join(str(p) for p in ports)
        return (
            f"python3 setup_server.py -u {user_id} -p {port_args}"
            f" -g {game_name} -m {ram_gb}g -c {cpu_cores} start"
        )

    async def generate_config_view_schema(
        self, cfg: Dict[str, Any], subscription_id: str
    ) -> Optional[Dict[str, Any]]:
        record, err = await db.db_select_subscription_by_id(sub_id=subscription_id)
        if not record:
            self.logger.info(
                "Unable to get subscription_record id:%s err:%s", record, err
            )
            return None

        plan_id = record.get("plan_id")
        plan = await self._get_plan(str(plan_id))
        if plan is None:
            self.logger.error("Plan %s not found", plan_id)
            return

        game_name = await self._get_game_name(plan.get("game_id"))
        if not game_name:
            self.logger.error("Game not found for plan %s", plan_id)
            return
        provisioner = ProvisionerFactory.get_provisioner(game_name=game_name)
        if not provisioner:
            return None

        return await provisioner.generate_config_view_schema(cfg)
