"""
Shared Flask helpers for parsing, database access, and CSRF.
"""
from __future__ import annotations

import os
import secrets
from decimal import Decimal, InvalidOperation
from hmac import compare_digest

import flask
from sqlalchemy import create_engine


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def get_read_database_url():
    if _env_bool("READ_FROM_INTERNAL_DATABASE", True):
        return get_database_url()

    metabase_database_url = os.environ.get("METABASE_DATABASE_URL")
    if not metabase_database_url:
        raise RuntimeError(
            "METABASE_DATABASE_URL environment variable is required when "
            "READ_FROM_INTERNAL_DATABASE=false"
        )
    return metabase_database_url


def get_engine():
    return create_engine(get_read_database_url(), pool_pre_ping=True)


def get_database_url():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")
    return database_url


def parse_arr_filter(raw_value):
    if not raw_value:
        return Decimal("0")
    try:
        value = Decimal(raw_value)
    except (InvalidOperation, ValueError):
        return Decimal("0")
    if value < 0:
        return Decimal("0")
    return value


def parse_non_negative_decimal_filter(raw_value):
    if not raw_value:
        return Decimal("0")
    try:
        value = Decimal(raw_value)
    except (InvalidOperation, ValueError):
        return Decimal("0")
    return value if value >= 0 else Decimal("0")


def parse_non_negative_int_filter(raw_value):
    if raw_value in (None, ""):
        return 0
    try:
        parsed = int(raw_value)
    except ValueError:
        return 0
    return parsed if parsed >= 0 else 0


def parse_enabled_flag(raw_value, default=True):
    if raw_value is None:
        return default
    normalized = str(raw_value).strip().lower()
    if normalized in {"true", "1", "yes", "on", "enabled"}:
        return True
    if normalized in {"false", "0", "no", "off", "disabled"}:
        return False
    return default


def get_or_create_csrf_token():
    token = flask.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        flask.session["csrf_token"] = token
    return token


def validate_csrf():
    request_token = flask.request.form.get("csrf_token", "")
    session_token = flask.session.get("csrf_token", "")
    if not session_token or not compare_digest(request_token, session_token):
        flask.abort(400, description="Invalid CSRF token")
