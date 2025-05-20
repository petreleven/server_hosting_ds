import logging
from abc import ABC, abstractmethod

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
        server_id: int,
        game_server_ip: str,
        game_name: str,
        subscription_id: int,
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
