import logging
from abc import ABC, abstractmethod
from typing import Dict, Any

from db import db


class AbstractProvisioner(ABC):
    """Abstract base class for all game provisioners.
    Defines the interface that all game provisioners must implement.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger("backendlogger")
        self.redisClient = db.get_redis_client()

    @abstractmethod
    async def job_update_config(
        self,
        game_server_ip: str,
        game_name: str,
        subscription_id: str,
        config_values: dict,
    ) -> None:
        """Update the configuration for a running game server.

        Args:
            game_server_ip: The IP address of the game server
            game_name: The name of the game
            subscription_id: The subscription ID associated with the server
            config_values: The configuration values to update

        """

    @abstractmethod
    async def get_default_config(self) -> str:
        """Get the default configuration for the game.

        Returns:
            A string representation of the default configuration

        """

    @abstractmethod
    def get_required_ports(self) -> list[int]:
        """Get the list of ports required for this game.

        Returns:
            A list of port numbers

        """

    @abstractmethod
    async def validate_config(self, config_values: dict) -> bool:
        """Validate the provided configuration against the game's schema.

        Args:
            config_values: The configuration values to validate

        Returns:
            True if the configuration is valid, False otherwise

        """

    @abstractmethod
    async def generate_config_view_schema(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """
        This generates the schema to be handed over to js based on saved configs from database
        Args:
            cfg : json loaded config values from db
        Returns:
            Dict[str, Any] a dictionary of the schema
        """
