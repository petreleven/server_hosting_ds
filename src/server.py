import asyncio
import logging
import os
from pathlib import Path
from pprint import pp
import sys

from dotenv import load_dotenv
from quart import Quart, abort, render_template, request
from quart_auth import QuartAuth
from quart_schema import QuartSchema

from api import apiblueprint
from db import db
from game_jobs import mainProvisioner
from userroutes import userblueprint
from create_order import orderBlueprint

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


@app.before_serving
async def connect():
    try:
        redis_Client = db.get_redis_client()
        if await redis_Client.json().get("pending_servers", "$") is None:
            await redis_Client.json().set("pending_servers", "$", [])
        await db.db_createalldbs()
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

@app.route("/test")
async def test():
    return await render_template("test.html")

import pprint
from typing import Optional
from paddle_billing.Notifications import Verifier, Secret
from paddle_billing.Notifications.Requests import Request
from paddle_billing.Notifications.Requests.Headers import Headers


class QuartRequestAdapter:
    """Adapter to make Quart request compatible with Paddle Request protocol"""

    def __init__(self, quart_request, raw_body: bytes):
        self.body: Optional[bytes] = raw_body
        self.content: Optional[bytes] = raw_body  # Same as body
        self.data: Optional[bytes] = raw_body     # Same as body
        self.headers: Headers = quart_request.headers

@app.route("/p_hook", methods=["POST"])
async def p_hook():
    # 1. Grab the raw body
    raw_body = await request.get_data()  # Get raw bytes from Quart

    # 2. Create adapter that satisfies the Request protocol
    paddle_request = QuartRequestAdapter(request, raw_body)

    try:
        # 3. Verify signature using the adapter
        integrity_check = Verifier().verify(
            paddle_request,
            Secret('apikey_01jy129070xndw3whgzcbgw1pe')
        )
    except Exception as e:
        print(f"Signature verification failed: {e}")
        abort(403)

    # 4. Now it's safe to parse JSON
    data = await request.get_json()
    pprint.pprint(data)

    # 5. Process your webhook data here
    # e.g. fulfill an order, update your DB, etc.

    return "OK", 200


app.run(
    debug=False,
    host="127.0.0.1",
    port=8000,
)
