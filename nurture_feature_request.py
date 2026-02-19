"""
Synchronize Google Sheet data into feature_request table.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from sqlalchemy import MetaData, Table, create_engine, text

load_dotenv()

GOOGLE_CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_FEATURE_REQUEST_TAB = os.environ.get("GOOGLE_FEATURE_REQUEST_TAB", "SF_FR_Data")
GOOGLE_FEATURE_REQUEST_HEADER_ROW = int(
    os.environ.get("GOOGLE_FEATURE_REQUEST_HEADER_ROW", "1")
)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

FEATURE_REQUEST_BOOL_FIELDS = {"open", "closed"}
FEATURE_REQUEST_DATE_FIELDS = {"date_time_opened"}
FEATURE_REQUEST_PRIORITY_VALUES = {
    "P0",
    "P1",
    "P2",
    "P3",
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
    "UNKNOWN",
}

FEATURE_REQUEST_UPSERT_SQL = text(
    """
    INSERT INTO feature_request (
        case_number,
        case_owner,
        account_name,
        subject,
        status,
        opportunity,
        feature_request,
        linear_url_fr,
        date_time_opened,
        priority,
        open,
        closed,
        technical_account_manager,
        feature_request_status,
        insert_time
    )
    VALUES (
        :case_number,
        :case_owner,
        :account_name,
        :subject,
        :status,
        :opportunity,
        :feature_request,
        :linear_url_fr,
        :date_time_opened,
        :priority,
        :open,
        :closed,
        :technical_account_manager,
        :feature_request_status,
        :insert_time
    )
    ON CONFLICT (case_number) DO UPDATE SET
        case_owner = EXCLUDED.case_owner,
        account_name = EXCLUDED.account_name,
        subject = EXCLUDED.subject,
        status = EXCLUDED.status,
        opportunity = EXCLUDED.opportunity,
        feature_request = EXCLUDED.feature_request,
        linear_url_fr = EXCLUDED.linear_url_fr,
        date_time_opened = EXCLUDED.date_time_opened,
        priority = EXCLUDED.priority,
        open = EXCLUDED.open,
        closed = EXCLUDED.closed,
        technical_account_manager = EXCLUDED.technical_account_manager,
        feature_request_status = EXCLUDED.feature_request_status,
        insert_time = EXCLUDED.insert_time
    """
)


def normalize_header(header: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", header.strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def parse_date(value):
    if value in (None, ""):
        return None
    raw = str(value).strip()
    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%m/%d/%Y %I:%M %p",
        "%d/%m/%Y %I:%M %p",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):
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


def parse_priority(value):
    if value in (None, ""):
        return None
    normalized = str(value).strip().upper()
    short_code = normalized.split("-", 1)[0].strip()
    if short_code in FEATURE_REQUEST_PRIORITY_VALUES:
        return short_code
    return normalized if normalized in FEATURE_REQUEST_PRIORITY_VALUES else "UNKNOWN"


def convert_value(field_name, value):
    if field_name in FEATURE_REQUEST_DATE_FIELDS:
        return parse_date(value)
    if field_name in FEATURE_REQUEST_BOOL_FIELDS:
        return parse_bool(value)
    if field_name == "priority":
        return parse_priority(value)
    if value in (None, ""):
        return None
    return str(value).strip()


def get_table_columns(database_url):
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        table = Table("feature_request", MetaData(), autoload_with=connection)
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
    worksheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(GOOGLE_FEATURE_REQUEST_TAB)
    values = worksheet.get_all_values()
    if not values:
        return []

    header_index = GOOGLE_FEATURE_REQUEST_HEADER_ROW - 1
    if header_index < 0:
        raise ValueError("feature_request header row must be >= 1")
    if len(values) <= header_index:
        raise ValueError(
            f"Sheet does not contain header row {GOOGLE_FEATURE_REQUEST_HEADER_ROW} in tab {GOOGLE_FEATURE_REQUEST_TAB}."
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
        raise ValueError("No Google Sheet headers matched feature_request columns.")

    records = []
    for row_values in values[header_index + 1 :]:
        record = {}
        for index, column_name in selected_columns:
            record[column_name] = row_values[index] if index < len(row_values) else ""
        records.append(record)
    return records


def sync_feature_request(database_url):
    db_columns = get_table_columns(database_url)
    records = get_sheet_rows(expected_columns=db_columns)
    transformed_rows = []
    for record in records:
        try:
            row = {k: convert_value(k, v) for k, v in record.items()}
        except (ValueError, ArithmeticError):
            continue
        case_number = (row.get("case_number") or "").strip()
        if case_number:
            row["case_number"] = case_number
            transformed_rows.append(row)
    if not transformed_rows:
        return 0

    batch_insert_time = datetime.now(timezone.utc).replace(tzinfo=None)
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.begin() as connection:
        for row in transformed_rows:
            row["insert_time"] = batch_insert_time
            connection.execute(FEATURE_REQUEST_UPSERT_SQL, row)
    return len(transformed_rows)
