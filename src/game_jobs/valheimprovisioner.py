import base64
import json
import os
import secrets
import sys
from typing import Dict, Any
from db import db

import jsonschema

from game_jobs.abstract_provisioner import AbstractProvisioner

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


class ValheimProvisioner(AbstractProvisioner):
    def __init__(self):
        super().__init__()
        """
         "ports": {
                    "type": "object",
                    "properties": {
                        "main_port": {"type": "integer", "default": 3300},
                        "misc_1": {"type": "integer", "default": 3311},
                    },
                },
        """
        self.schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "https://example.com/schemas/valheim.json",
            "title": "Valheim Server Config",
            "description": "Configuration schema for spinning up a Valheim dedicated server. See support guide: https://www.valheimgame.com/support/a-guide-to-dedicated-servers/",
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "The display name for your server (-name)",
                    "default": "My server",
                },
                "world": {
                    "type": "string",
                    "minLength": 1,
                    "default": "Dedicated",
                    "description": "Name of the world to load or create (-world)",
                },
                "password": {
                    "type": "string",
                    "minLength": 0,
                    "description": "Optional password (leave blank for none) (-password)",
                    "default": "",
                },
                "savedir": {
                    "type": "string",
                    "default": "./valheim_saves",
                    "description": "Path where worlds and permission files are stored (-savedir)",
                },
                "public": {
                    "type": "integer",
                    "enum": [0, 1],
                    "default": 1,
                    "description": "0 = private, 1 = publicly listed on Steam (-public)",
                },
                "logFile": {
                    "type": "string",
                    "default": "./valheim.log",
                    "description": "File path to save server logs (-logFile)",
                },
                "saveinterval": {
                    "type": "integer",
                    "minimum": 60,
                    "default": 1800,
                    "description": "Interval between world saves in seconds (-saveinterval)",
                },
                "backups": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 4,
                    "description": "How many automatic backups to keep (-backups)",
                },
                "backupshort": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 7200,
                    "description": "Interval (in seconds) until the first automatic backup (-backupshort)",
                },
                "backuplong": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 43200,
                    "description": "Interval (in seconds) for subsequent automatic backups (-backuplong)",
                },
                "crossplay": {
                    "type": "boolean",
                    "default": False,
                    "description": "Enable crossplay backend (-crossplay)",
                },
                "instanceid": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 1,
                    "description": "Unique identifier when hosting multiple servers on the same IP/port (-instanceid)",
                },
                "preset": {
                    "type": "string",
                    "enum": [
                        "Normal",
                        "Casual",
                        "Easy",
                        "Hard",
                        "Hardcore",
                        "Immersive",
                        "Hammer",
                    ],
                    "default": "Normal",
                    "description": "Sets world modifier preset. Setting a preset will overwrite any other previous modifiers. Valid values are: Normal, Casual, Easy, Hard, Hardcore, Immersive, Hammer. (-preset)",
                },
                "modifiers": {
                    "type": "object",
                    "properties": {
                        "Combat": {
                            "type": "string",
                            "enum": ["veryeasy", "easy", "hard", "veryhard"],
                            "default": "easy",
                        },
                        "DeathPenalty": {
                            "type": "string",
                            "enum": ["casual", "veryeasy", "easy", "hard", "hardcore"],
                            "default": "easy",
                        },
                        "Resources": {
                            "type": "string",
                            "enum": ["muchless", "less", "more", "muchmore", "most"],
                            "default": "less",
                        },
                        "Raids": {
                            "type": "string",
                            "enum": ["none", "muchless", "less", "more", "muchmore"],
                            "default": "less",
                        },
                        "Portals": {
                            "type": "string",
                            "enum": ["casual", "hard", "veryhard"],
                            "default": "casual",
                        },
                    },
                },
                # Individual setkey boolean fields
                "nomap": {
                    "type": "boolean",
                    "default": False,
                    "description": "Disable map exploration overlays (setkey nomap)",
                },
                "playerevents": {
                    "type": "boolean",
                    "default": False,
                    "description": "Enable player events (setkey playerevents)",
                },
                "passivemobs": {
                    "type": "boolean",
                    "default": False,
                    "description": "Enable passive mobs (setkey passivemobs)",
                },
                "nobuildcost": {
                    "type": "boolean",
                    "default": False,
                    "description": "Disable build costs (setkey nobuildcost)",
                },
            },
            "required": ["name", "world"],
        }

    def parse_check_boxes(self, form_dict) -> Dict:
        check_box_keys = [
            "nobuildcost",
            "passivemobs",
            "playerevents",
            "nomap",
            "crossplay",
        ]
        for key in check_box_keys:
            if key not in form_dict.keys():
                form_dict[key] = "off"
            form_dict[key] = True if form_dict[key] == "on" else False

        return form_dict

    async def job_update_config(
        self,
        game_server_ip: str,
        game_name: str,
        subscription_id: str,
        config_values: dict,
    ) -> None:
        """Implementation of configuration update for Valheim servers."""

        if not await self.validate_config(config_values):
            return

        queue = f"badger:pending:{game_server_ip}"

        raw = json.dumps(config_values, separators=(",", ":"))
        encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        payload = (
            f"python setup_server.py "
            f"-u {subscription_id} "
            f"-g {game_name} "
            f"--cfg-json {encoded} "
            f"updateConfig"
        )
        self.redisClient = await db.get_redis_client()
        await self.redisClient.lpush(queue, payload)

    async def get_default_config(self) -> str:
        """Get the default configuration for Valheim servers."""
        properties: dict = {}
        for key, value in self.schema["properties"].items():
            if value["type"] != "object":
                properties[key] = value["default"]
            else:
                for k, v in value["properties"].items():
                    properties[f"{key}_{k}"] = v["default"]
        properties["password"] = secrets.token_urlsafe(nbytes=4)

        # Validate the default config
        await self.validate_config(properties)

        return json.dumps(properties)

    def get_required_ports(self) -> list[int]:
        """Get the required ports for Valheim servers."""
        # Valheim requires two consecutive UDP ports
        # The server binds to the first port, and the second port is port+1
        return [2456, 2457]

    async def validate_config(self, config_values: dict) -> bool:
        """Validate the provided configuration against the Valheim schema."""
        try:
            jsonschema.validate(config_values, self.schema)
            return True
        except jsonschema.ValidationError as e:
            self.logger.error("Json Validation for valheim config failed:", str(e))
            return False

    async def generate_config_view_schema(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        schema_copy = self.schema.copy()
        for key, value in cfg.items():
            if key in schema_copy["properties"].keys():
                if schema_copy["properties"][key]["type"] != "object":
                    schema_copy["properties"][key]["value"] = value
            else:
                for k in schema_copy["properties"].keys():
                    if schema_copy["properties"][k]["type"] == "object":
                        r = key.lower().split("_")
                        if len(r) > 1 and r[0] == k:
                            schema_copy["properties"][k][r[1]] = value

        return schema_copy
