"""
Synchronize Google Sheet data into Customer_Success table.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from sqlalchemy import MetaData, Table, create_engine, text

load_dotenv()

def _env_str(name, default=""):
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip()
    return normalized if normalized else default


def _env_int(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip()
    if not normalized:
        return default
    try:
        return int(normalized)
    except ValueError:
        return default


GOOGLE_CREDENTIALS_PATH = _env_str("GOOGLE_CREDENTIALS_PATH", "credentials.json")
GOOGLE_SHEET_ID = _env_str("GOOGLE_SHEET_ID", "")
GOOGLE_SHEET_TAB = _env_str("GOOGLE_SHEET_TAB", "Dashboard")
GOOGLE_SHEET_HEADER_ROW = _env_int("GOOGLE_SHEET_HEADER_ROW", 4)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

INT_FIELDS = {
    "open_critical_feature_request",
    "days_since_last_contact",
    "total_contributors",
    "contributors_last_30_days",
}
DECIMAL_FIELDS = {"active_contributors_count", "annual_recurring_revenue"}
DATE_FIELDS = {"last_engagement_date", "latest_contract_end_date", "license_expiration_date"}
BOOL_FIELDS = {"sast", "ssc", "secrets"}
HEALTH_COLORS = {"green", "yellow", "red"}

UPSERT_SQL = text(
    """
    INSERT INTO "Customer_Success" (
        deployment_id,
        account_name,
        customer_stage,
        account_owner,
        annual_recurring_revenue,
        technical_account_manager,
        last_engagement_date,
        sast,
        ssc,
        secrets,
        active_contributors_count,
        health_color,
        latest_contract_end_date,
        open_critical_feature_request,
        days_since_last_contact,
        license_expiration_date,
        total_contributors,
        contributors_last_30_days,
        insert_time
    )
    VALUES (
        :deployment_id,
        :account_name,
        :customer_stage,
        :account_owner,
        :annual_recurring_revenue,
        :technical_account_manager,
        :last_engagement_date,
        :sast,
        :ssc,
        :secrets,
        :active_contributors_count,
        :health_color,
        :latest_contract_end_date,
        :open_critical_feature_request,
        :days_since_last_contact,
        :license_expiration_date,
        :total_contributors,
        :contributors_last_30_days,
        :insert_time
    )
    ON CONFLICT (deployment_id) DO UPDATE SET
        account_name = EXCLUDED.account_name,
        customer_stage = EXCLUDED.customer_stage,
        account_owner = EXCLUDED.account_owner,
        annual_recurring_revenue = EXCLUDED.annual_recurring_revenue,
        technical_account_manager = EXCLUDED.technical_account_manager,
        last_engagement_date = EXCLUDED.last_engagement_date,
        sast = EXCLUDED.sast,
        ssc = EXCLUDED.ssc,
        secrets = EXCLUDED.secrets,
        active_contributors_count = EXCLUDED.active_contributors_count,
        health_color = EXCLUDED.health_color,
        latest_contract_end_date = EXCLUDED.latest_contract_end_date,
        open_critical_feature_request = EXCLUDED.open_critical_feature_request,
        days_since_last_contact = EXCLUDED.days_since_last_contact,
        license_expiration_date = EXCLUDED.license_expiration_date,
        total_contributors = EXCLUDED.total_contributors,
        contributors_last_30_days = EXCLUDED.contributors_last_30_days,
        insert_time = EXCLUDED.insert_time
    """
)


def normalize_header(header: str) -> str:
    return header.strip().lower().replace(" ", "_")


def parse_int(value):
    if value in (None, ""):
        return None
    return int(str(value).strip())


def parse_decimal(value):
    if value in (None, ""):
        return None
    cleaned = (
        str(value)
        .replace("$", "")
        .replace("USD", "")
        .replace("usd", "")
        .replace(",", "")
        .replace("%", "")
        .strip()
    )
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1].strip()}"
    return Decimal(cleaned)


def parse_date(value):
    if value in (None, ""):
        return None
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {raw}")


def parse_bool(value):
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"Unsupported boolean value: {value}")


def parse_health_color(value):
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    if normalized in HEALTH_COLORS:
        return normalized.capitalize()
    raise ValueError(f"Unsupported health_color value: {value}")


def convert_value(field_name, value):
    if field_name in INT_FIELDS:
        return parse_int(value)
    if field_name in DECIMAL_FIELDS:
        return parse_decimal(value)
    if field_name in DATE_FIELDS:
        return parse_date(value)
    if field_name in BOOL_FIELDS:
        return parse_bool(value)
    if field_name == "health_color":
        return parse_health_color(value)
    if value in (None, ""):
        return None
    return str(value).strip()


def get_table_columns(database_url):
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        table = Table("Customer_Success", MetaData(), autoload_with=connection)
        return {column.name for column in table.columns}


def get_sheet_rows(expected_columns):
    if not GOOGLE_SHEET_ID:
        raise ValueError("GOOGLE_SHEET_ID is not set")
    if not os.path.isfile(GOOGLE_CREDENTIALS_PATH):
        raise FileNotFoundError(
            f"Credentials file not found: {GOOGLE_CREDENTIALS_PATH}"
        )

    credentials = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_PATH, scopes=SCOPES
    )
    client = gspread.authorize(credentials)
    worksheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(GOOGLE_SHEET_TAB)
    values = worksheet.get_all_values()
    if not values:
        return []

    header_index = GOOGLE_SHEET_HEADER_ROW - 1
    if header_index < 0:
        raise ValueError("Customer_Success header row must be >= 1")
    if len(values) <= header_index:
        raise ValueError(
            f"Sheet does not contain header row {GOOGLE_SHEET_HEADER_ROW} in tab {GOOGLE_SHEET_TAB}."
        )

    headers = values[header_index]
    selected_columns = []
    seen_columns = set()
    for index, header in enumerate(headers):
        normalized = normalize_header(header)
        if not normalized:
            continue
        if normalized not in expected_columns or normalized in seen_columns:
            continue
        seen_columns.add(normalized)
        selected_columns.append((index, normalized))

    if not selected_columns:
        raise ValueError(
            "No Google Sheet headers matched Customer_Success database columns."
        )

    records = []
    for row_values in values[header_index + 1 :]:
        record = {}
        for index, column_name in selected_columns:
            record[column_name] = row_values[index] if index < len(row_values) else ""
        records.append(record)
    return records


def sync_customer_success(database_url):
    db_columns = get_table_columns(database_url)
    records = get_sheet_rows(expected_columns=db_columns)
    transformed_rows = []
    for record in records:
        try:
            row = {k: convert_value(k, v) for k, v in record.items()}
        except (ValueError, ArithmeticError):
            continue
        deployment_id = (row.get("deployment_id") or "").strip()
        account_name = (row.get("account_name") or "").strip()
        if deployment_id and account_name:
            row["deployment_id"] = deployment_id
            row["account_name"] = account_name
            transformed_rows.append(row)

    if not transformed_rows:
        return 0

    batch_insert_time = datetime.now(timezone.utc).replace(tzinfo=None)
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.begin() as connection:
        for row in transformed_rows:
            row["insert_time"] = batch_insert_time
            connection.execute(UPSERT_SQL, row)
    return len(transformed_rows)
