import asyncio
import logging
import os
from pathlib import Path
from pprint import pp
import sys

from dotenv import load_dotenv
from quart import Quart
from quart_auth import QuartAuth
from quart_schema import QuartSchema
from db import db
from game_jobs import mainProvisioner

from api_internal.api import apiblueprint
from api_user.userroutes import userblueprint
from api_user.create_order import orderBlueprint
from api_user.server_actions import serverActionsBlueprint

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

BACKENDLOGGER = logging.getLogger("backendlogger")
STATIC_FOLDER = os.path.join(str(Path(__file__).parent) + "/static")
# globals
app = Quart(__name__)
app._static_folder = STATIC_FOLDER
app.secret_key = "38b1c9fa-9c2b-467b-ae42-960d3e1593c1"
# extensions
QuartAuth(app)
QuartSchema(app)
# registering blueprint
app.register_blueprint(apiblueprint)
app.register_blueprint(userblueprint)
app.register_blueprint(orderBlueprint)
app.register_blueprint(serverActionsBlueprint)


@app.before_serving
async def connect()->None:
    try:
        redis_Client = db.get_redis_client()
        if await redis_Client.json().get("pending_servers", "$") is None:
            await redis_Client.json().set("pending_servers", "$", [])
        # await db.db_createalldbs()
        await redis_Client.ping()
        # app.add_background_task(check_pending_servers)
    except Exception as e:
        BACKENDLOGGER.warning("error in startup:", e)
        raise


async def check_pending_servers():
    pv = mainProvisioner.MainProvisioner()
    await pv.job_repeating_check_pending_servers()
    while True:
        await pv.job_repeating_check_pending_servers()
        await asyncio.sleep(30)


app.run(
    debug=False,
    host="127.0.0.1",
    port=8000,
)
