from ast import arg
from typing import Dict, List
from quart import Blueprint, request, render_template
from quart_auth import login_required
from db import db
orderBlueprint = Blueprint("orderBlueprint", __name__)


@orderBlueprint.route("/get_order_form",methods=["GET"])
async def get_order_form():
    args = request.args
    game_id = args.get("game_id", "")
    plans, err = await db.db_select_all_plans_by_game(game_id=game_id)
    plans_list : List[Dict] = []
    for p in plans:
        instance = {}
        instance["id"] = str(p.get("id"))
        instance["plan_name"] = p.get("plan_name")
        instance["price_monthly"]=p.get("price_monthly")
        plans_list.append(instance)
    return await render_template("get_order_form.html", plans_list=plans_list)


@login_required
@orderBlueprint.route("/new_server",methods=["GET", "POST"])
async def new_server():
    return await render_template("new_server.html")



