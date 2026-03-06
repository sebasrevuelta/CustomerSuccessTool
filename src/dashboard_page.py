"""
Dashboard page routes and data logic.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

import flask
from sqlalchemy import MetaData, Table, create_engine, func, insert, select
from sqlalchemy.exc import SQLAlchemyError

from app_common import (
    get_database_url,
    get_engine,
    get_or_create_csrf_token,
    parse_arr_filter,
    parse_enabled_flag,
    parse_non_negative_decimal_filter,
    parse_non_negative_int_filter,
    validate_csrf,
)
from nurture_customer_success import sync_customer_success


def _sortable_value(value):
    if value is None:
        return (3, "")
    if isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, (int, float, Decimal)):
        return (0, Decimal(str(value)))
    if isinstance(value, datetime):
        return (1, value.timestamp())
    if isinstance(value, date):
        return (1, value.toordinal())
    return (2, str(value).strip().lower())


def _sort_customer_rows(rows, sort_by, sort_dir):
    valid_direction = "desc" if sort_dir == "desc" else "asc"
    reverse = valid_direction == "desc"

    rows_with_values = [row for row in rows if row.get(sort_by) is not None]
    rows_without_values = [row for row in rows if row.get(sort_by) is None]
    rows_with_values.sort(key=lambda row: _sortable_value(row.get(sort_by)), reverse=reverse)
    return rows_with_values + rows_without_values


def _build_scores_for_row(mapped_row):
    active_contributors = mapped_row.get("active_contributors_count")
    if active_contributors is None:
        mapped_row["contributors_score"] = None
    else:
        mapped_row["contributors_score"] = (
            Decimal("100")
            if Decimal(active_contributors) > Decimal("100")
            else Decimal(active_contributors)
        )

    days_since_last_contact = mapped_row.get("days_since_last_contact")
    if days_since_last_contact is None:
        mapped_row["days_since_last_contact_score"] = None
    else:
        mapped_row["days_since_last_contact_score"] = (
            Decimal("100") - Decimal(days_since_last_contact)
        )

    sms_usage = mapped_row.get("sms_usage")
    if sms_usage is None:
        mapped_row["sms_score"] = None
    else:
        mapped_row["sms_score"] = Decimal(sms_usage)

    open_critical_feature_request = mapped_row.get("open_critical_feature_request")
    if open_critical_feature_request is None:
        mapped_row["critical_fr_score"] = None
    else:
        critical_fr_count = int(open_critical_feature_request)
        if critical_fr_count <= 0:
            mapped_row["critical_fr_score"] = Decimal("100")
        elif critical_fr_count == 1:
            mapped_row["critical_fr_score"] = Decimal("75")
        elif critical_fr_count == 2:
            mapped_row["critical_fr_score"] = Decimal("50")
        elif critical_fr_count == 3:
            mapped_row["critical_fr_score"] = Decimal("25")
        else:
            mapped_row["critical_fr_score"] = Decimal("0")

    health_color = mapped_row.get("health_color")
    if health_color is None:
        mapped_row["health_ae_score"] = None
    else:
        normalized_health_color = str(health_color).strip().lower()
        if normalized_health_color == "green":
            mapped_row["health_ae_score"] = Decimal("100")
        elif normalized_health_color == "yellow":
            mapped_row["health_ae_score"] = Decimal("50")
        elif normalized_health_color in {"red/yellow", "red-yellow"}:
            mapped_row["health_ae_score"] = Decimal("25")
        elif normalized_health_color == "red":
            mapped_row["health_ae_score"] = Decimal("0")
        else:
            mapped_row["health_ae_score"] = None

    return mapped_row


def _compute_dynamic_health_score(
    mapped_row,
    *,
    use_last_activity_factor,
    use_contributors_factor,
    use_health_ae_factor,
    use_feature_request_factor,
    use_sms_factor,
):
    score_components = []
    if use_health_ae_factor and mapped_row.get("health_ae_score") is not None:
        score_components.append(Decimal(mapped_row["health_ae_score"]))
    if use_feature_request_factor and mapped_row.get("critical_fr_score") is not None:
        score_components.append(Decimal(mapped_row["critical_fr_score"]))
    if use_contributors_factor and mapped_row.get("contributors_score") is not None:
        score_components.append(Decimal(mapped_row["contributors_score"]))
    if (
        use_last_activity_factor
        and mapped_row.get("days_since_last_contact_score") is not None
    ):
        score_components.append(Decimal(mapped_row["days_since_last_contact_score"]))
    if use_sms_factor and mapped_row.get("sms_score") is not None:
        score_components.append(Decimal(mapped_row["sms_score"]))

    if not score_components:
        return None
    average_score = sum(score_components) / Decimal(len(score_components))
    return int(average_score.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def get_customer_success_data(
    technical_account_manager=None,
    customer_stage=None,
    account_owner=None,
    annual_recurring_revenue_min=None,
    open_critical_feature_request_min=None,
    active_contributors_count_min=None,
    use_last_activity_factor=True,
    use_contributors_factor=True,
    use_health_ae_factor=True,
    use_feature_request_factor=True,
    use_sms_factor=True,
    sort_by="account_name",
    sort_dir="asc",
):
    try:
        with get_engine().connect() as connection:
            table = Table("Customer_Success", MetaData(), autoload_with=connection)
            base_conditions = []
            if "insert_time" in table.c:
                latest_insert_time = connection.execute(
                    select(func.max(table.c.insert_time))
                ).scalar_one_or_none()
                if latest_insert_time is not None:
                    base_conditions.append(table.c.insert_time == latest_insert_time)
            else:
                latest_insert_time = None

            query = select(table)
            for condition in base_conditions:
                query = query.where(condition)
            if technical_account_manager:
                query = query.where(
                    table.c.technical_account_manager == technical_account_manager
                )
            if customer_stage:
                query = query.where(table.c.customer_stage == customer_stage)
            if account_owner:
                query = query.where(table.c.account_owner == account_owner)
            if annual_recurring_revenue_min is not None:
                query = query.where(
                    table.c.annual_recurring_revenue >= annual_recurring_revenue_min
                )
            if open_critical_feature_request_min is not None:
                query = query.where(
                    table.c.open_critical_feature_request
                    >= open_critical_feature_request_min
                )
            if active_contributors_count_min is not None:
                query = query.where(
                    table.c.active_contributors_count >= active_contributors_count_min
                )

            result = connection.execute(query)
            headers = list(result.keys())
            rows = []
            for row in result:
                mapped_row = dict(row._mapping)
                mapped_row = _build_scores_for_row(mapped_row)
                mapped_row["health_score"] = _compute_dynamic_health_score(
                    mapped_row,
                    use_last_activity_factor=use_last_activity_factor,
                    use_contributors_factor=use_contributors_factor,
                    use_health_ae_factor=use_health_ae_factor,
                    use_feature_request_factor=use_feature_request_factor,
                    use_sms_factor=use_sms_factor,
                )
                rows.append(mapped_row)

            if "contributors_score" not in headers:
                headers.append("contributors_score")
            if "days_since_last_contact_score" not in headers:
                headers.append("days_since_last_contact_score")
            if "critical_fr_score" not in headers:
                headers.append("critical_fr_score")
            if "health_ae_score" not in headers:
                headers.append("health_ae_score")
            if "sms_score" not in headers:
                headers.append("sms_score")
            if "health_score" not in headers:
                insert_idx = 2 if len(headers) >= 2 else len(headers)
                headers.insert(insert_idx, "health_score")

            effective_sort_by = sort_by if sort_by in set(headers) else "account_name"
            rows = _sort_customer_rows(rows, effective_sort_by, sort_dir)

            tam_query = (
                select(table.c.technical_account_manager)
                .distinct()
                .where(*base_conditions)
                .where(table.c.technical_account_manager.is_not(None))
                .where(table.c.technical_account_manager != "")
                .order_by(table.c.technical_account_manager)
            )
            stage_query = (
                select(table.c.customer_stage)
                .distinct()
                .where(*base_conditions)
                .where(table.c.customer_stage.is_not(None))
                .where(table.c.customer_stage != "")
                .order_by(table.c.customer_stage)
            )
            owner_query = (
                select(table.c.account_owner)
                .distinct()
                .where(*base_conditions)
                .where(table.c.account_owner.is_not(None))
                .where(table.c.account_owner != "")
                .order_by(table.c.account_owner)
            )
            arr_max_query = (
                select(func.max(table.c.annual_recurring_revenue)).where(*base_conditions)
            )
            critical_max_query = (
                select(func.max(table.c.open_critical_feature_request)).where(
                    *base_conditions
                )
            )
            contributors_max_query = (
                select(func.max(table.c.active_contributors_count)).where(*base_conditions)
            )
            tam_options = [row[0] for row in connection.execute(tam_query)]
            stage_options = [row[0] for row in connection.execute(stage_query)]
            owner_options = [row[0] for row in connection.execute(owner_query)]
            arr_max = connection.execute(arr_max_query).scalar_one_or_none() or Decimal(
                "0"
            )
            critical_max = connection.execute(critical_max_query).scalar_one_or_none() or 0
            contributors_max = (
                connection.execute(contributors_max_query).scalar_one_or_none()
                or Decimal("0")
            )

            return (
                headers,
                rows,
                tam_options,
                stage_options,
                owner_options,
                arr_max,
                int(critical_max),
                contributors_max,
                latest_insert_time,
            )
    except (SQLAlchemyError, RuntimeError) as exc:
        flask.current_app.logger.exception("Failed to read from PostgreSQL: %s", exc)
        return [], [], [], [], [], Decimal("0"), 0, Decimal("0"), None


def persist_customer_success_health_score_snapshot(
    *,
    database_url,
    use_last_activity_factor,
    use_contributors_factor,
    use_health_ae_factor,
    use_feature_request_factor,
    use_sms_factor,
):
    with create_engine(database_url, pool_pre_ping=True).begin() as connection:
        customer_table = Table("Customer_Success", MetaData(), autoload_with=connection)
        health_table = Table(
            "Customer_success_health_score",
            MetaData(),
            autoload_with=connection,
        )

        latest_insert_time = connection.execute(
            select(func.max(customer_table.c.insert_time))
        ).scalar_one_or_none()
        if latest_insert_time is None:
            return 0

        query = (
            select(
                customer_table.c.account_name,
                customer_table.c.active_contributors_count,
                customer_table.c.days_since_last_contact,
                customer_table.c.open_critical_feature_request,
                customer_table.c.health_color,
            )
            .where(customer_table.c.insert_time == latest_insert_time)
            .order_by(customer_table.c.account_name)
        )
        rows = connection.execute(query)

        snapshot_insert_time = datetime.now(timezone.utc).replace(tzinfo=None)
        inserted_rows = 0
        for row in rows:
            mapped_row = dict(row._mapping)
            account_name = (mapped_row.get("account_name") or "").strip()
            if not account_name:
                continue

            _build_scores_for_row(mapped_row)
            mapped_row["health_score"] = _compute_dynamic_health_score(
                mapped_row,
                use_last_activity_factor=use_last_activity_factor,
                use_contributors_factor=use_contributors_factor,
                use_health_ae_factor=use_health_ae_factor,
                use_feature_request_factor=use_feature_request_factor,
                use_sms_factor=use_sms_factor,
            )
            if mapped_row["health_score"] is None:
                continue

            connection.execute(
                insert(health_table).values(
                    account_name=account_name,
                    health_score=mapped_row["health_score"],
                    insert_time=snapshot_insert_time,
                )
            )
            inserted_rows += 1

        return inserted_rows


def register_dashboard_routes(app):
    @app.route("/", endpoint="index")
    def index():
        technical_account_manager = flask.request.args.get(
            "technical_account_manager", ""
        ).strip()
        customer_stage = flask.request.args.get("customer_stage", "").strip()
        account_owner = flask.request.args.get("account_owner", "").strip()
        arr_min = parse_arr_filter(
            flask.request.args.get("annual_recurring_revenue_min")
        )
        critical_min = parse_non_negative_int_filter(
            flask.request.args.get("open_critical_feature_request_min")
        )
        contributors_min = parse_non_negative_decimal_filter(
            flask.request.args.get("active_contributors_count_min")
        )
        requested_sort_by = flask.request.args.get("sort_by", "account_name").strip()
        requested_sort_dir = flask.request.args.get("sort_dir", "asc").strip().lower()
        if requested_sort_dir not in {"asc", "desc"}:
            requested_sort_dir = "asc"
        use_last_activity_factor = parse_enabled_flag(
            flask.request.args.get(
                "last_activity_factor", flask.request.cookies.get("last_activity_factor")
            ),
            default=True,
        )
        use_contributors_factor = parse_enabled_flag(
            flask.request.args.get(
                "contributors_factor", flask.request.cookies.get("contributors_factor")
            ),
            default=True,
        )
        use_health_ae_factor = parse_enabled_flag(
            flask.request.args.get(
                "health_ae_factor", flask.request.cookies.get("health_ae_factor")
            ),
            default=True,
        )
        use_feature_request_factor = parse_enabled_flag(
            flask.request.args.get(
                "feature_request_factor",
                flask.request.cookies.get("feature_request_factor"),
            ),
            default=True,
        )
        use_sms_factor = parse_enabled_flag(
            flask.request.args.get("sms_factor", flask.request.cookies.get("sms_factor")),
            default=True,
        )

        (
            headers,
            rows,
            tam_options,
            stage_options,
            owner_options,
            arr_max,
            critical_max,
            contributors_max,
            latest_insert_time,
        ) = get_customer_success_data(
            technical_account_manager=technical_account_manager or None,
            customer_stage=customer_stage or None,
            account_owner=account_owner or None,
            annual_recurring_revenue_min=arr_min,
            open_critical_feature_request_min=critical_min,
            active_contributors_count_min=contributors_min,
            use_last_activity_factor=use_last_activity_factor,
            use_contributors_factor=use_contributors_factor,
            use_health_ae_factor=use_health_ae_factor,
            use_feature_request_factor=use_feature_request_factor,
            use_sms_factor=use_sms_factor,
            sort_by=requested_sort_by,
            sort_dir=requested_sort_dir,
        )
        arr_max_value = float(arr_max)
        arr_min_value = float(arr_min if arr_min <= arr_max else arr_max)
        critical_min_value = (
            critical_min if critical_min <= critical_max else critical_max
        )
        contributors_max_value = float(contributors_max)
        contributors_min_value = float(
            contributors_min if contributors_min <= contributors_max else contributors_max
        )
        if latest_insert_time is not None:
            last_refresh_display = latest_insert_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            last_refresh_display = "N/A"

        return flask.render_template(
            "index.html",
            active_page="dashboard",
            headers=headers,
            rows=rows,
            tam_options=tam_options,
            stage_options=stage_options,
            owner_options=owner_options,
            selected_tam=technical_account_manager,
            selected_stage=customer_stage,
            selected_owner=account_owner,
            arr_min_value=arr_min_value,
            arr_max_value=arr_max_value,
            critical_min_value=critical_min_value,
            critical_max_value=critical_max,
            contributors_min_value=contributors_min_value,
            contributors_max_value=contributors_max_value,
            last_refresh_display=last_refresh_display,
            selected_sort_by=requested_sort_by,
            selected_sort_dir=requested_sort_dir,
            refresh_message=flask.request.args.get("refresh_message", ""),
            refresh_status=flask.request.args.get("refresh_status", ""),
            csrf_token=get_or_create_csrf_token(),
        )

    @app.post("/refresh", endpoint="refresh")
    def refresh():
        validate_csrf()

        technical_account_manager = flask.request.form.get(
            "technical_account_manager", ""
        ).strip()
        customer_stage = flask.request.form.get("customer_stage", "").strip()
        account_owner = flask.request.form.get("account_owner", "").strip()
        arr_min = flask.request.form.get("annual_recurring_revenue_min", "0").strip()
        critical_min = flask.request.form.get(
            "open_critical_feature_request_min", "0"
        ).strip()
        contributors_min = flask.request.form.get(
            "active_contributors_count_min", "0"
        ).strip()
        sort_by = flask.request.form.get("sort_by", "account_name").strip()
        sort_dir = flask.request.form.get("sort_dir", "asc").strip().lower()
        if sort_dir not in {"asc", "desc"}:
            sort_dir = "asc"
        use_last_activity_factor = parse_enabled_flag(
            flask.request.cookies.get("last_activity_factor"), default=True
        )
        use_contributors_factor = parse_enabled_flag(
            flask.request.cookies.get("contributors_factor"), default=True
        )
        use_health_ae_factor = parse_enabled_flag(
            flask.request.cookies.get("health_ae_factor"), default=True
        )
        use_feature_request_factor = parse_enabled_flag(
            flask.request.cookies.get("feature_request_factor"), default=True
        )
        use_sms_factor = parse_enabled_flag(
            flask.request.cookies.get("sms_factor"), default=True
        )

        try:
            database_url = get_database_url()
            synced_rows = sync_customer_success(database_url)
            score_rows = persist_customer_success_health_score_snapshot(
                database_url=database_url,
                use_last_activity_factor=use_last_activity_factor,
                use_contributors_factor=use_contributors_factor,
                use_health_ae_factor=use_health_ae_factor,
                use_feature_request_factor=use_feature_request_factor,
                use_sms_factor=use_sms_factor,
            )
            refresh_message = (
                "Load completed. "
                f"Synchronized {synced_rows} Dashboard rows and saved {score_rows} health score snapshots."
            )
            refresh_status = "success"
        except Exception as exc:  # noqa: BLE001
            app.logger.exception("Refresh failed: %s", exc)
            refresh_message = (
                "Load failed. Check Google credentials, sheet sharing, and logs."
            )
            refresh_status = "error"

        return flask.redirect(
            flask.url_for(
                "index",
                technical_account_manager=technical_account_manager,
                customer_stage=customer_stage,
                account_owner=account_owner,
                annual_recurring_revenue_min=arr_min,
                open_critical_feature_request_min=critical_min,
                active_contributors_count_min=contributors_min,
                sort_by=sort_by,
                sort_dir=sort_dir,
                refresh_message=refresh_message,
                refresh_status=refresh_status,
            )
        )
