import logging
import os
import secrets
import sys

from dotenv import load_dotenv
from quart import Quart
from quart_auth import QuartAuth
from quart_schema import QuartSchema

from api import apiblueprint
from db import db
from game_jobs import valheimprovisioner
from userroutes import userblueprint

# envs
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(os.getcwd(), "web.log")),
        logging.StreamHandler(sys.stdout),
    ],
)

backendlogger = logging.getLogger("backendlogger")
redisClient = db.get_redis_client()
# globals
app = Quart(__name__)
app._static_folder = os.path.join(os.path.dirname(__file__), "static")
auth = QuartAuth(
    app,
)
app.secret_key = secrets.token_urlsafe(16)
QuartSchema(app)
# registering blueprint
app.register_blueprint(apiblueprint)
app.register_blueprint(userblueprint)


def get_app():
    return app


@app.before_serving
async def connect():
    x = {
        "name": "awesomeserver",
        "port": 2456,
        "world": "westworld",
        "password": "7777",
        "public": 1,
        "saveinterval": 1800,
        "backups": 4,
        "backupshort": 7200,
        "backuplong": 43200,
        "crossplay": True,
    }
    try:
        # await db.db_createalldbs()
        await redisClient.ping()
        vp = valheimprovisioner.ValheimProvisioner()
        await vp.job_update_config(2, "0.0.0.0", "valheim", 34, x)
    except Exception as e:
        backendlogger.warning(f"Unable to connect to Redis @{db.REDIS_PORT}:", e)
        sys.exit(0)


app.run(debug=False, host="127.0.0.1", port=8000)
