from  game_jobs.valheimprovisioner import ValheimProvisioner

a = ValheimProvisioner()
X = a.generate_config_view_schema( \
    cfg={
  "backuplong": 43200,
  "backups": 4,
  "backupshort": 7200,
  "crossplay": False,
  "instanceid": 1,
  "logFile": "./valheim.log",
  "modifiers_Combat": "easy",
  "modifiers_DeathPenalty": "easy",
  "modifiers_Portals": "casual",
  "modifiers_Raids": "less",
  "modifiers_Resources": "less",
  "name": "My server",
  "nobuildcost": False,
  "nomap": False,
  "passivemobs": False,
  "password": "WpF5tA",
  "playerevents": False,
  "port": 2456,
  "preset": "Normal",
  "public": 1,
  "savedir": "./valheim_saves",
  "saveinterval": 1800,
  "world": "Dedicated"
}
    )
print(X)
