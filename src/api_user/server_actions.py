import logging
from quart import Blueprint, request, jsonify
from quart_auth import login_required
from db import db
from game_jobs.mainProvisioner import MainProvisioner
import json

serverActionsBlueprint = Blueprint("serverActionsBlueprint", __name__)


def create_error_response(message, status_code=400):
    """Helper function to create standardized error responses."""
    return jsonify({"error": message}), status_code


@serverActionsBlueprint.route("/restart_server", methods=["POST"])
@login_required
async def restart_server():
    redis_Client = await db.get_redis_client()
    logger = logging.getLogger("backendlogger")
    subscription_id = request.args.get("subscription_id", "")
    if not subscription_id:
        return create_error_response("Missing subscription_id", 400)

    try:
        server, err = await db.db_select_server_by_subscription_id(subscription_id)
        if not server:
            logger.error(
                f"Server not found for subscription_id {subscription_id}: {err}"
            )
            return create_error_response("Server not found", 404)

        subscription, err = await db.db_select_subscription_by_id(subscription_id)
        if not subscription:
            logger.error(
                f"Subscription not found for subscription_id {subscription_id}: {err}"
            )
            return create_error_response("Subscription not found", 404)

        plan, err = await db.db_select_plan_by_id(str(subscription.get("plan_id", "")))
        if not plan:
            logger.error(f"Plan not found for subscription_id {subscription_id}: {err}")
            return create_error_response("Plan not found", 404)

        game, err = await db.db_select_game_by_id(str(plan.get("parent_id", "")))
        if not game:
            logger.error(f"Game not found for subscription_id {subscription_id}: {err}")
            return create_error_response("Game not found", 404)

        game_name = game.get("name", "")
        await db.db_update_server_status(
            status=db.SERVER_STATUS.RESTARTING.value,
            docker_container_id=server.get("docker_container_id", ""),
            subscription_id=subscription_id,
            ports=server.get("ports", ""),
        )
        ip = server.get("ip_address", "")
        queueName = f"badger:pending:{ip}"
        payload = f"python3 setup_server.py -u {subscription_id} -g {game_name} restart"
        await redis_Client.lpush(queueName, payload)
        return "restarting", 200
    except Exception as e:
        logger.exception(
            f"Unexpected error when restarting server for subscription_id {subscription_id}: {e}"
        )
        return create_error_response("Internal server error", 500)


@serverActionsBlueprint.route("/stop_server", methods=["POST"])
@login_required
async def stop_server():
    redis_Client = await db.get_redis_client()
    subscription_id = request.args.get("subscription_id", "")
    if not subscription_id:
        return create_error_response("Missing subscription_id", 400)

    try:
        server, err = await db.db_select_server_by_subscription_id(subscription_id)
        if not server:
            return create_error_response("Server not found", 404)

        subscription, err = await db.db_select_subscription_by_id(subscription_id)
        if not subscription:
            return create_error_response("Subscription not found", 404)

        plan, err = await db.db_select_plan_by_id(str(subscription.get("plan_id", "")))
        if not plan:
            return create_error_response("Plan not found", 404)

        game, err = await db.db_select_game_by_id(str(plan.get("parent_id", "")))
        if not game:
            return create_error_response("Game not found", 404)

        game_name = game.get("name", "")
        await db.db_update_server_status(
            status=db.SERVER_STATUS.STOPPING.value,
            docker_container_id=server.get("docker_container_id", ""),
            subscription_id=subscription_id,
            ports=server.get("ports", ""),
        )
        ip = server.get("ip_address", "")
        queueName = f"badger:pending:{ip}"
        payload = f"python3 setup_server.py -u {subscription_id} -g {game_name} stop"
        await redis_Client.lpush(queueName, payload)
        return "stopping", 200
    except Exception as e:
        logging.exception(
            f"Unexpected error when stopping server for subscription_id {subscription_id}: {e}"
        )
        return create_error_response("Internal server error", 500)


@serverActionsBlueprint.route("/backup_server", methods=["POST"])
@login_required
async def backup_server():
    redis_Client = await db.get_redis_client()
    subscription_id = request.args.get("subscription_id", "")
    if not subscription_id:
        return create_error_response("Missing subscription_id", 400)

    try:
        server, err = await db.db_select_server_by_subscription_id(subscription_id)
        if not server:
            return create_error_response("Server not found", 404)

        subscription, err = await db.db_select_subscription_by_id(subscription_id)
        if not subscription:
            return create_error_response("Subscription not found", 404)

        plan, err = await db.db_select_plan_by_id(str(subscription.get("plan_id", "")))
        if not plan:
            return create_error_response("Plan not found", 404)

        game, err = await db.db_select_game_by_id(str(plan.get("parent_id", "")))
        if not game:
            return create_error_response("Game not found", 404)

        game_name = game.get("name", "")
        await db.db_update_server_status(
            status=db.SERVER_STATUS.RUNNING.value,
            docker_container_id=server.get("docker_container_id", ""),
            subscription_id=subscription_id,
            ports=server.get("ports", ""),
        )
        ip = server.get("ip_address", "")
        queueName = f"badger:pending:{ip}"
        payload = f"python3 setup_server.py -u {subscription_id} -g {game_name} backup"
        await redis_Client.lpush(queueName, payload)
        return "backing up", 200
    except Exception as e:
        logging.exception(
            f"Unexpected error when backing up server for subscription_id {subscription_id}: {e}"
        )
        return create_error_response("Internal server error", 500)


@serverActionsBlueprint.route("/save-config", methods=["POST"])
@login_required
async def save_config():
    logger = logging.getLogger("backendlogger")
    provisioner = MainProvisioner()
    subscription_id = request.args.get("subscription_id", "")
    error_html = "<p>Error updating the configuration</p>"
    success_html = "<p>Success</p>"

    server, err = await db.db_select_server_by_subscription_id(
        subscription_id=subscription_id
    )

    def log_error(err):
        logger.error(
            f"Error when updating configuration server:{server} of subscription_id:{subscription_id} err:{err} "
        )

    if not server or not subscription_id:
        log_error(err)
        return error_html

    subscription, err = await db.db_select_subscription_by_id(
        subscription_id=subscription_id
    )
    if not subscription:
        log_error(err)
        return error_html

    plan, err = await db.db_select_plan_by_id(str(subscription.get("plan_id", "")))
    if not plan:
        log_error(err)
        return error_html

    game, err = await db.db_select_game_by_id(str(plan.get("parent_id", "")))
    if not game or not game.get("name", None):
        log_error(err)
        return error_html

    ip = server.get("ip_address", "")
    game_name = game.get("name", "")

    # take care of nestings of 1 level and ints
    raw_config_values = await request.form

    config_values = {}
    for key, value in raw_config_values.items():
        v = value
        try:
            v = int(v)
        except ValueError:
            pass
        # on the frontend inputs for same object have like
        # toplavelname[example1], toplevelname[example2]
        # which needs to map to {'toplavelname' : {'example1' : .., 'example2': ...}}

        if "[" in key and "]" in key:
            top_level_name = key.split("[")[0]
            second_level_name = (key.split("[")[1]).split("]")[0]
            if not config_values.get(top_level_name, None):
                config_values[top_level_name] = {}
            config_values[top_level_name][second_level_name] = v
            continue
        config_values[key] = v

    parsed_config_form = provisioner.parse_check_boxes(
        form_dict=config_values, game_name=game_name
    )
    if parsed_config_form is not None:
        config_values = parsed_config_form

    result, _ = await db.db_update_server_config(
        config=json.dumps(config_values), server_id=str(server.get("id", ""))
    )
    await provisioner.job_update_config(
        game_server_ip=ip,
        game_name=game_name,
        subscription_id=subscription_id,
        config_values=config_values,
    )

    return success_html
