import logging
import os
from pathlib import Path
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

BACKENDLOGGER = logging.getLogger("backendlogger")
STATIC_FOLDER = os.path.join(str(Path(__file__).parent) + "/static")
# globals
app = Quart(__name__)
app._static_folder = STATIC_FOLDER
app.secret_key = "38b1c9fa-9c2b-467b-ae42-960d3e1593c1"
#extensions
QuartAuth(app)
QuartSchema(app)
# registering blueprint
app.register_blueprint(apiblueprint)
app.register_blueprint(userblueprint)




@app.before_serving
async def connect():

    try:
        redisClient = db.get_redis_client()
        await db.db_createalldbs()
        await redisClient.ping()
    except Exception as e:
        BACKENDLOGGER.warning("error in startup:", e)
        raise


app.run(debug=False, host="127.0.0.1", port=8000)
