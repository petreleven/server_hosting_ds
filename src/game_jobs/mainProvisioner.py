import datetime
import logging
from typing import Any, Dict, Optional, List
import json
import asyncpg
import helper_classes.custom_dataclass as cdata
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

    async def job_order_new_trial_server(self, data: cdata.RegisterUserData) -> None:
        """Orchestrates the provisioning of a new game server for a registered user.

        Args:
            data: The registration data for the user
        """
        user, _ = await db.db_select_user_by_email(data.email)
        if user is None:
            self.logger.warning("User not found for email %s", data.email)
            return
        user_id = str(user.get("id", ""))
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            hours=8, minutes=10
        )
        subscription, _ = await db.db_insert_subscription(
            user_id=user_id,
            plan_id=data.plan_id,
            internal_status=db.INTERNAL_SUBSCRIPTION_STATUS.PROVISIONING.value,
            status=db.SUBSCRIPTION_STATUS.ACTIVE.value,
            expires_at=expires_at,
            next_billing_date=expires_at,
            is_trial=True,
        )

        if subscription is None:
            self.logger.error("Failed to create subscription for user %d", user_id)
            return

        plan, _ = await db.db_select_plan_by_id(data.plan_id)
        if plan is None:
            self.logger.error("Plan %s not found", data.plan_id)
            return

        game, _ = await db.db_select_game_by_id(str(plan.get("parent_id")))
        if not game:
            self.logger.error("Game not found for plan %s", data.plan_id)
            return
        game_name = game.get("name", "")

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
            sub_id = str(subscription.get("id"))
            if not sub_id:
                return

            # Update subscription status to unavailable
            record, err = await db.db_update_subscription_internal_status(
                sub_id,
                db.INTERNAL_SUBSCRIPTION_STATUS.UNAVAILABLE.value,
            )
            if err:
                self.logger.warning(f"Unable to update subscription {sub_id}: {err}")

            # Add to queue for processing when resources become available
            ram_gb = plan.get("ram_gb")
            if ram_gb:
                await self._add_order_to_queue(
                    subscription_id=str(sub_id),
                    game_name=game_name,
                    ram_gb=int(ram_gb),
                    plan_id=data.plan_id,
                )
                await self.update_exhausted_free_status(user_id)
            return

        await db.db_update_subscription_is_trial(str(subscription.get("id")), True)
        await self._provision_server(
            subscription_id=str(subscription.get("id")),
            baremetal=baremetal,
            game_name=game_name,
            plan=plan,
            provisioner=provisioner,
            cfg=cfg,
        )
        await self.update_exhausted_free_status(user_id)

    async def _add_order_to_queue(
        self,
        subscription_id: str,
        game_name: str,
        ram_gb: int,
        plan_id: str,
    ) -> None:
        """Add a server order to the pending queue."""
        payload = {
            "subscription_id": subscription_id,
            "name": game_name,
            "ram_gb": ram_gb,
            "plan_id": plan_id,
            "order_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.logger.debug(f"Adding order to queue: {payload}")

        try:
            await self.redisClient.json().arrappend(
                "pending_servers", "$", json.dumps(payload)
            )
            self.logger.info(f"Added subscription {subscription_id} to pending queue")
        except Exception as e:
            self.logger.error(f"Failed to add order to queue: {e}")

    async def job_repeating_check_pending_servers(self) -> None:
        print("called")
        """Process pending server requests in FIFO order using Redis array operations."""
        try:
            # Get the length of the pending servers array
            queue_length = await self.redisClient.json().arrlen("pending_servers")
            if not queue_length or queue_length == 0:
                self.logger.debug("No pending servers in queue")
                return

            self.logger.debug(f"Processing {queue_length} pending servers")

            # Process orders from the front of the queue (FIFO)
            processed_count = 0
            for _ in range(queue_length):
                pending_job = {}
                try:
                    # Get the first item in the queue
                    pending_job_json = await self.redisClient.json().get(
                        "pending_servers", "$[0]"
                    )
                    if not pending_job_json or not pending_job_json[0]:
                        break

                    pending_job = json.loads(
                        pending_job_json[0]
                    )  # Extract from array wrapper

                    # Try to process the job
                    if await self._process_pending_job(pending_job):
                        # Remove the processed job from the front of the queue
                        await self.redisClient.json().arrpop("pending_servers", "$", 0)
                        processed_count += 1
                        self.logger.info(
                            f"Successfully processed and removed job for subscription {pending_job.get('subscription_id')}"
                        )
                    else:
                        # Can't process this job (no resources), stop processing queue
                        self.logger.debug(
                            "No available resources, stopping queue processing"
                        )
                        break

                except Exception as e:
                    subscription_id = str(
                        (pending_job.get("subscription_id", "unknown"))
                        if "pending_job" in locals()
                        else "unknown"
                    )
                    self.logger.error(
                        f"Failed to process subscription_id job {subscription_id}: {e}"
                    )
                    # Remove the problematic job to prevent queue blocking
                    try:
                        await self.redisClient.json().arrpop("pending_servers", "$", 0)
                        self.logger.warning("Removed problematic job from queue")
                    except Exception as cleanup_error:
                        self.logger.error(
                            f"Failed to remove problematic job: {cleanup_error}"
                        )
                        break

            if processed_count > 0:
                self.logger.info(f"Processed {processed_count} pending server orders")

        except Exception as e:
            self.logger.error(f"Error in job_repeating_check_pending_servers: {e}")

    async def _process_pending_job(self, pending_job: dict) -> bool:
        """
        Process a single pending job.

        Returns:
            bool: True if job was successfully processed, False if no resources available
        """
        subscription_id = str(pending_job.get("subscription_id"))
        ram_needed = pending_job.get("ram_gb")
        plan_id = str(pending_job.get("plan_id"))
        game_name = pending_job.get("name", "")

        # Validate required fields
        if not all([subscription_id, plan_id, game_name]):
            self.logger.warning(
                f"Missing required fields in pending job: {pending_job}"
            )
            return True  # Return True to remove invalid job from queue

        # Find available hardware
        baremetal = await self._find_available_baremetal(ram_needed=ram_needed)
        if not baremetal:
            self.logger.debug(
                f"No available baremetal for job {subscription_id} (RAM needed: {ram_needed}GB)"
            )
            return False  # Keep job in queue

        # Get plan details
        plan, _ = await db.db_select_plan_by_id(plan_id)
        if not plan:
            self.logger.warning(
                f"Unable to find plan with id {plan_id} for job {subscription_id}"
            )
            return True  # Remove invalid job from queue

        # Get provisioner and config
        try:
            provisioner = ProvisionerFactory.get_provisioner(game_name)
            if not provisioner:
                self.logger.error(f"Failed to get provisioner for game {game_name}")
                return False
            config = await provisioner.get_default_config()
        except Exception as e:
            self.logger.error(f"Failed to get provisioner for game '{game_name}': {e}")
            return True  # Remove invalid job from queue

        # Provision the server
        try:
            await self._provision_server(
                subscription_id=str(subscription_id),
                baremetal=baremetal,
                game_name=game_name,
                plan=plan,
                provisioner=provisioner,
                cfg=config,
            )
            self.logger.info(
                f"Successfully provisioned server for subscription {subscription_id}"
            )
            return True

        except Exception as e:
            self.logger.error(
                f"Failed to provision server for subscription {subscription_id}: {e}"
            )
            return False  # Keep job in queue for retry

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

        server, _ = await db.db_insert_server(
            subscription_id=subscription_id,
            status=db.SERVER_STATUS.PROVISIONING.value,
            ip_address=ip,
            ports="",
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
            game_name=game_name,
            ram_gb=plan.get("ram_gb", 2),
            cpu_cores=plan.get("cpu_cores", 2),
        )
        queue = f"badger:pending:{ip}"
        await self.redisClient.lpush(queue, payload)
        self.logger.info("Server provisioning queued: %s", payload)

    def _build_payload(
        self,
        user_id: str,
        game_name: str,
        ram_gb: int,
        cpu_cores: int,
    ) -> str:
        """Build the payload for the provisioning job."""
        return (
            f"python3 setup_server.py -u {user_id}"
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
        plan, _ = await db.db_select_plan_by_id(str(plan_id))
        if plan is None:
            self.logger.error("Plan %s not found", plan_id)
            return

        game, _ = await db.db_select_game_by_id(str(plan.get("parent_id")))
        if not game:
            self.logger.error("Game not found for plan %s", plan_id)
            return
        game_name = game.get("name", "")
        provisioner = ProvisionerFactory.get_provisioner(game_name=game_name)
        if not provisioner:
            return None

        data = await provisioner.generate_config_view_schema(cfg)
        data["subscription_id"] = subscription_id
        return data

    async def update_exhausted_free_status(self, user_id):
        pool = await db.get_pool()
        if not pool:
            return
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE  users SET exhausted_free=$1 WHERE id=$2", True, user_id
            )

    def parse_check_boxes(self, form_dict, game_name) -> Optional[Dict]:
        provisioner = ProvisionerFactory.get_provisioner(game_name=game_name)
        if not provisioner:
            return None
        newform_dict = provisioner.parse_check_boxes(form_dict=form_dict)
        return newform_dict
