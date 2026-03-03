"""
Feature request page routes and data logic.
"""
from __future__ import annotations

import flask
from sqlalchemy import MetaData, Table, func, select
from sqlalchemy.exc import SQLAlchemyError

from app_common import get_database_url, get_engine, get_or_create_csrf_token, validate_csrf
from nurture_feature_request import sync_feature_request


def get_feature_request_data(
    account_name=None,
    technical_account_manager=None,
    priority=None,
):
    try:
        with get_engine().connect() as connection:
            table = Table("feature_request", MetaData(), autoload_with=connection)
            latest_insert_time = connection.execute(
                select(func.max(table.c.insert_time))
            ).scalar_one_or_none()

            query = select(table)
            if latest_insert_time is not None:
                query = query.where(table.c.insert_time == latest_insert_time)
            if account_name:
                query = query.where(table.c.account_name == account_name)
            if technical_account_manager:
                query = query.where(
                    table.c.technical_account_manager == technical_account_manager
                )
            if priority:
                query = query.where(table.c.priority == priority)
            query = query.order_by(table.c.case_number)

            result = connection.execute(query)
            headers = list(result.keys())
            rows = [dict(row._mapping) for row in result]

            account_name_query = select(table.c.account_name).distinct()
            if latest_insert_time is not None:
                account_name_query = account_name_query.where(
                    table.c.insert_time == latest_insert_time
                )
            account_name_query = (
                account_name_query.where(table.c.account_name.is_not(None))
                .where(table.c.account_name != "")
                .order_by(table.c.account_name)
            )
            account_name_options = [row[0] for row in connection.execute(account_name_query)]
            tam_query = select(table.c.technical_account_manager).distinct()
            if latest_insert_time is not None:
                tam_query = tam_query.where(table.c.insert_time == latest_insert_time)
            tam_query = (
                tam_query.where(table.c.technical_account_manager.is_not(None))
                .where(table.c.technical_account_manager != "")
                .order_by(table.c.technical_account_manager)
            )
            technical_account_manager_options = [
                row[0] for row in connection.execute(tam_query)
            ]

            priority_query = select(table.c.priority).distinct()
            if latest_insert_time is not None:
                priority_query = priority_query.where(table.c.insert_time == latest_insert_time)
            priority_query = (
                priority_query.where(table.c.priority.is_not(None))
                .order_by(table.c.priority)
            )
            priority_options = [str(row[0]) for row in connection.execute(priority_query)]

            return (
                headers,
                rows,
                account_name_options,
                technical_account_manager_options,
                priority_options,
            )
    except (SQLAlchemyError, RuntimeError) as exc:
        flask.current_app.logger.exception("Failed to read feature_request data: %s", exc)
        return [], [], [], [], []


def register_feature_request_routes(app):
    @app.get("/feature-requests", endpoint="feature_requests")
    def feature_requests():
        selected_account_name = flask.request.args.get("account_name", "").strip()
        selected_technical_account_manager = flask.request.args.get(
            "technical_account_manager", ""
        ).strip()
        selected_priority = flask.request.args.get("priority", "").strip()
        (
            headers,
            rows,
            account_name_options,
            technical_account_manager_options,
            priority_options,
        ) = get_feature_request_data(
            account_name=selected_account_name or None,
            technical_account_manager=selected_technical_account_manager or None,
            priority=selected_priority or None,
        )
        return flask.render_template(
            "feature_requests.html",
            active_page="feature_requests",
            headers=headers,
            rows=rows,
            account_name_options=account_name_options,
            technical_account_manager_options=technical_account_manager_options,
            priority_options=priority_options,
            selected_account_name=selected_account_name,
            selected_technical_account_manager=selected_technical_account_manager,
            selected_priority=selected_priority,
            refresh_message=flask.request.args.get("refresh_message", ""),
            refresh_status=flask.request.args.get("refresh_status", ""),
            csrf_token=get_or_create_csrf_token(),
        )

    @app.post("/refresh-feature-requests", endpoint="refresh_feature_requests")
    def refresh_feature_requests():
        validate_csrf()
        selected_account_name = flask.request.form.get("account_name", "").strip()
        selected_technical_account_manager = flask.request.form.get(
            "technical_account_manager", ""
        ).strip()
        selected_priority = flask.request.form.get("priority", "").strip()
        try:
            synced_rows = sync_feature_request(get_database_url())
            refresh_message = (
                "Load completed. "
                f"Synchronized {synced_rows} Feature Request rows."
            )
            refresh_status = "success"
        except Exception as exc:  # noqa: BLE001
            app.logger.exception("Feature request refresh failed: %s", exc)
            refresh_message = "Load failed. Check Google credentials, sheet sharing, and logs."
            refresh_status = "error"

        return flask.redirect(
            flask.url_for(
                "feature_requests",
                account_name=selected_account_name,
                technical_account_manager=selected_technical_account_manager,
                priority=selected_priority,
                refresh_message=refresh_message,
                refresh_status=refresh_status,
            )
        )
