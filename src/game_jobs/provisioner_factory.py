import logging

from game_jobs.abstract_provisioner import AbstractProvisioner


class ProvisionerFactory:
    """Factory class for creating game-specific provisioners.
    Allows for dynamic registration of new game provisioners.
    """

    _provisioners: dict[str, type[AbstractProvisioner]] = {}
    _logger = logging.getLogger("backendlogger")

    @classmethod
    def register_provisioner(
        cls,
        game_name: str,
        provisioner_class: type[AbstractProvisioner],
    ) -> None:
        """Register a provisioner class for a specific game.

        Args:
            game_name: The name of the game
            provisioner_class: The provisioner class to register

        """
        cls._provisioners[game_name.lower()] = provisioner_class
        cls._logger.info(f"Registered provisioner for game: {game_name}")

    @classmethod
    def get_provisioner(cls, game_name: str) -> AbstractProvisioner | None:
        """Get an instance of the provisioner for the specified game.

        Args:
            game_name: The name of the game

        Returns:
            An instance of the provisioner or None if not found

        """
        game_name = game_name.lower()
        provisioner_class = cls._provisioners.get(game_name)

        if not provisioner_class:
            cls._logger.warning(f"No provisioner found for game: {game_name}")
            return None

        return provisioner_class()

    @classmethod
    def load_provisioners(cls) -> None:
        """Load all available provisioners from the game_jobs module.
        This can be expanded to load from a configuration file or database.
        """
        # Import available provisioners
        try:
            from game_jobs.valheimprovisioner import ValheimProvisioner

            cls.register_provisioner("valheim", ValheimProvisioner)

        except ImportError as e:
            cls._logger.error(f"Error loading provisioners: {e}")
