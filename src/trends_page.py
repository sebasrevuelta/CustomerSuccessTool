"""
Trends page route and query logic.
"""
from __future__ import annotations

from decimal import Decimal

import flask
from sqlalchemy import MetaData, Table, func, select
from sqlalchemy.exc import SQLAlchemyError

from app_common import get_engine


def get_health_trends_data(account_name=None):
    try:
        with get_engine().connect() as connection:
            table = Table(
                "Customer_success_health_score",
                MetaData(),
                autoload_with=connection,
            )
            if (
                "insert_time" not in table.c
                or "health_score" not in table.c
                or "account_name" not in table.c
            ):
                return None, [], []

            account_name_query = (
                select(table.c.account_name)
                .distinct()
                .where(table.c.account_name.is_not(None), table.c.account_name != "")
                .order_by(table.c.account_name)
            )
            account_name_options = [row[0] for row in connection.execute(account_name_query)]

            query = select(table.c.insert_time, table.c.health_score).where(
                table.c.insert_time.is_not(None), table.c.health_score.is_not(None)
            )
            if account_name:
                query = query.where(table.c.account_name == account_name)
            query = query.order_by(table.c.insert_time)
            result = connection.execute(query)

            trend_accumulator = {}
            for row in result:
                mapped_row = dict(row._mapping)
                insert_time = mapped_row.get("insert_time")
                if insert_time is None:
                    continue

                health_score = mapped_row.get("health_score")
                if health_score is None:
                    continue

                bucket = trend_accumulator.setdefault(
                    insert_time, {"sum": Decimal("0"), "count": 0}
                )
                bucket["sum"] += Decimal(health_score)
                bucket["count"] += 1

            trend_series = []
            for insert_time in sorted(trend_accumulator):
                bucket = trend_accumulator[insert_time]
                if bucket["count"] <= 0:
                    continue
                average_score = bucket["sum"] / Decimal(bucket["count"])
                trend_series.append(
                    {
                        "insert_time": insert_time,
                        "label": insert_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "value": float(average_score),
                    }
                )

            latest_average = trend_series[-1]["value"] if trend_series else None

            customer_success_table = Table(
                "Customer_Success",
                MetaData(),
                autoload_with=connection,
            )
            customer_latest_insert_time = connection.execute(
                select(func.max(customer_success_table.c.insert_time))
            ).scalar_one_or_none()

            number_of_accounts = 0
            total_arr = Decimal("0")
            if customer_latest_insert_time is not None:
                number_accounts_query = select(
                    func.count(func.distinct(customer_success_table.c.account_name))
                ).where(
                    customer_success_table.c.insert_time == customer_latest_insert_time,
                    customer_success_table.c.account_name.is_not(None),
                    customer_success_table.c.account_name != "",
                )
                total_arr_query = select(
                    func.sum(customer_success_table.c.annual_recurring_revenue)
                ).where(customer_success_table.c.insert_time == customer_latest_insert_time)
                if account_name:
                    number_accounts_query = number_accounts_query.where(
                        customer_success_table.c.account_name == account_name
                    )
                    total_arr_query = total_arr_query.where(
                        customer_success_table.c.account_name == account_name
                    )

                number_of_accounts = (
                    connection.execute(number_accounts_query).scalar_one_or_none() or 0
                )
                total_arr = (
                    connection.execute(total_arr_query).scalar_one_or_none()
                    or Decimal("0")
                )

            return (
                latest_average,
                trend_series,
                account_name_options,
                int(number_of_accounts),
                total_arr,
            )
    except (SQLAlchemyError, RuntimeError) as exc:
        flask.current_app.logger.exception("Failed to read health trends data: %s", exc)
        return None, [], [], 0, Decimal("0")


def register_trends_routes(app):
    @app.get("/trends", endpoint="trends")
    def trends():
        selected_account_name = flask.request.args.get("account_name", "").strip()
        (
            average_health_score,
            trend_series,
            account_name_options,
            number_of_accounts,
            total_arr,
        ) = get_health_trends_data(account_name=selected_account_name or None)
        return flask.render_template(
            "trends.html",
            active_page="trends",
            average_health_score=average_health_score,
            number_of_accounts=number_of_accounts,
            total_arr=total_arr,
            account_name_options=account_name_options,
            selected_account_name=selected_account_name,
            trend_labels=[point["label"] for point in trend_series],
            trend_values=[point["value"] for point in trend_series],
        )
