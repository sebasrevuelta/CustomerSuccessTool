"""
Helpers to fetch runtime secrets from AWS Secrets Manager.
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)

GOOGLE_SHEET_ID_SECRET_NAME = "prod/customer_health_score_tool/google_sheet_id"
OIDC_SECRET_NAME = "prod/customer_health_score_tool/oidc"
INTERNAL_DATABASE_SECRET_NAME = (
    "prod/customer_success_health_score_tool/internal_database"
)
GOOGLE_CREDENTIALS_SECRET_NAME = "prod/customer_health_score_tool/google_credentials"


def _env_str(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip()
    return normalized if normalized else default


@lru_cache(maxsize=16)
def get_secret_string(secret_name: str, region_name: str) -> str:
    access_key_id = _env_str(
        "AWS_SECRETS_MANAGER_ACCESS_KEY_ID", _env_str("AWS_ACCESS_KEY_ID", "")
    )
    secret_access_key = _env_str(
        "AWS_SECRETS_MANAGER_SECRET_ACCESS_KEY",
        _env_str("AWS_SECRET_ACCESS_KEY", ""),
    )
    session_token = _env_str(
        "AWS_SECRETS_MANAGER_SESSION_TOKEN", _env_str("AWS_SESSION_TOKEN", "")
    )
    profile_name = _env_str(
        "AWS_SECRETS_MANAGER_PROFILE", _env_str("AWS_PROFILE", "")
    )

    if (access_key_id and not secret_access_key) or (
        secret_access_key and not access_key_id
    ):
        logger.error(
            "Incomplete AWS credentials in environment for Secrets Manager access."
        )
        raise RuntimeError(
            "Incomplete AWS credentials in environment. Set both "
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (or the "
            "AWS_SECRETS_MANAGER_* equivalents)."
        )

    session_kwargs = {}
    if access_key_id and secret_access_key:
        session_kwargs["aws_access_key_id"] = access_key_id
        session_kwargs["aws_secret_access_key"] = secret_access_key
        if session_token:
            session_kwargs["aws_session_token"] = session_token
    elif profile_name:
        session_kwargs["profile_name"] = profile_name

    logger.info("Initializing AWS Secrets Manager client.")
    session = boto3.session.Session(**session_kwargs)
    endpoint_url = _env_str("AWS_SECRETS_MANAGER_ENDPOINT_URL", "")
    client_kwargs = {"service_name": "secretsmanager", "region_name": region_name}
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url
        logger.info("Using custom AWS Secrets Manager endpoint URL.")
    client = session.client(**client_kwargs)
    try:
        logger.info("Requesting secret value from AWS Secrets Manager.")
        response = client.get_secret_value(SecretId=secret_name)
    except (NoCredentialsError, PartialCredentialsError) as exc:
        logger.error("Unable to locate valid AWS credentials for Secrets Manager.")
        raise RuntimeError(
            "AWS credentials were not found. Set AWS_ACCESS_KEY_ID and "
            "AWS_SECRET_ACCESS_KEY (plus AWS_SESSION_TOKEN if needed), use "
            "AWS_PROFILE, or attach an IAM role to the runtime."
        ) from exc
    except ClientError as exc:
        logger.error("AWS Secrets Manager client error retrieving secret value.")
        raise RuntimeError(
            f"Failed to retrieve secret '{secret_name}' from AWS Secrets Manager"
        ) from exc

    secret_value = response.get("SecretString")
    if secret_value:
        logger.info("Successfully retrieved secret value as SecretString.")
        return secret_value

    secret_binary = response.get("SecretBinary")
    if secret_binary:
        logger.info("Successfully retrieved secret value as SecretBinary.")
        return secret_binary.decode("utf-8")

    raise RuntimeError(f"Secret '{secret_name}' has no SecretString/SecretBinary value")


def get_google_sheet_id() -> str:
    region_name = _env_str("AWS_REGION", "us-west-2")
    logger.info(
        "Resolving GOOGLE_SHEET_ID via AWS Secrets Manager."
    )
    secret_payload = get_secret_string(GOOGLE_SHEET_ID_SECRET_NAME, region_name).strip()
    if not secret_payload:
        logger.warning("Secrets Manager lookup resolved to an empty value.")
        return ""

    # Support both plain string secrets and JSON payloads.
    if secret_payload.startswith("{"):
        try:
            parsed = json.loads(secret_payload)
        except json.JSONDecodeError:
            return secret_payload
        for key in ("GOOGLE_SHEET_ID", "google_sheet_id", "sheet_id"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                logger.info(
                    "Resolved GOOGLE_SHEET_ID from JSON payload key '%s'.",
                    key,
                )
                return value.strip()
        logger.warning(
            "Secrets Manager JSON payload does not contain a recognized GOOGLE_SHEET_ID key."
        )
        return ""

    logger.info("Resolved GOOGLE_SHEET_ID from plain string secret payload.")
    return secret_payload


def get_oidc_client_secret() -> str:
    region_name = _env_str("AWS_REGION", "us-west-2")
    logger.info("Resolving OIDC client secret via AWS Secrets Manager.")
    secret_payload = get_secret_string(OIDC_SECRET_NAME, region_name).strip()
    if not secret_payload:
        raise RuntimeError("OIDC secret payload is empty in AWS Secrets Manager.")

    if secret_payload.startswith("{"):
        try:
            parsed = json.loads(secret_payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OIDC secret payload is invalid JSON.") from exc
        for key in ("OIDC_CLIENT_SECRET", "oidc_client_secret", "client_secret"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                logger.info("Resolved OIDC client secret from JSON payload.")
                return value.strip()
        raise RuntimeError(
            "OIDC secret JSON payload does not contain OIDC_CLIENT_SECRET."
        )

    logger.info("Resolved OIDC client secret from plain string secret payload.")
    return secret_payload


def get_oidc_client_id() -> str:
    region_name = _env_str("AWS_REGION", "us-west-2")
    logger.info("Resolving OIDC client ID via AWS Secrets Manager.")
    secret_payload = get_secret_string(OIDC_SECRET_NAME, region_name).strip()
    if not secret_payload:
        raise RuntimeError("OIDC secret payload is empty in AWS Secrets Manager.")

    if secret_payload.startswith("{"):
        try:
            parsed = json.loads(secret_payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OIDC secret payload is invalid JSON.") from exc
        for key in ("OIDC_CLIENT_ID", "oidc_client_id", "client_id"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                logger.info("Resolved OIDC client ID from JSON payload.")
                return value.strip()
        raise RuntimeError("OIDC secret JSON payload does not contain OIDC_CLIENT_ID.")

    logger.info("Resolved OIDC client ID from plain string secret payload.")
    return secret_payload


def get_internal_database_credentials() -> tuple[str, str]:
    region_name = _env_str("AWS_REGION", "us-west-2")
    logger.info("Resolving internal database credentials via AWS Secrets Manager.")
    secret_payload = get_secret_string(INTERNAL_DATABASE_SECRET_NAME, region_name).strip()
    if not secret_payload:
        raise RuntimeError(
            "Internal database secret payload is empty in AWS Secrets Manager."
        )

    if not secret_payload.startswith("{"):
        raise RuntimeError(
            "Internal database secret payload must be JSON with username/password."
        )
    try:
        parsed = json.loads(secret_payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Internal database secret payload is invalid JSON.") from exc

    username = ""
    password = ""
    for key in (
        "INTERNAL_DATABASE_USERNAME",
        "internal_database_username",
        "username",
        "user",
    ):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            username = value.strip()
            break
    for key in (
        "INTERNAL_DATABASE_PASSWORD",
        "internal_database_password",
        "password",
        "pass",
    ):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            password = value.strip()
            break

    if not username or not password:
        raise RuntimeError(
            "Internal database secret JSON must include username and password fields."
        )
    logger.info("Resolved internal database credentials from JSON payload.")
    return username, password


def get_google_credentials_info() -> dict:
    region_name = _env_str("AWS_REGION", "us-west-2")
    logger.info("Resolving Google service-account credentials via AWS Secrets Manager.")
    secret_payload = get_secret_string(GOOGLE_CREDENTIALS_SECRET_NAME, region_name).strip()
    if not secret_payload:
        raise RuntimeError(
            "Google credentials secret payload is empty in AWS Secrets Manager."
        )

    try:
        parsed = json.loads(secret_payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Google credentials secret payload is invalid JSON.") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("Google credentials secret payload must be a JSON object.")

    if parsed.get("type") != "service_account":
        raise RuntimeError(
            "Google credentials secret payload is not a valid service-account key."
        )
    logger.info("Resolved Google service-account credentials from JSON payload.")
    return parsed
