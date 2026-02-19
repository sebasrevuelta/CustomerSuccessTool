"""
Orchestrate Google Sheet sync into Customer_Success and feature_request tables.
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError

from nurture_customer_success import sync_customer_success
from nurture_feature_request import sync_feature_request

load_dotenv()
logger = logging.getLogger(__name__)


def sync_google_sheet_to_postgres():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    customer_success_rows = sync_customer_success(database_url)
    feature_request_rows = sync_feature_request(database_url)
    return {
        "customer_success_rows": customer_success_rows,
        "feature_request_rows": feature_request_rows,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")
    try:
        result = sync_google_sheet_to_postgres()
        logger.info(
            "Synchronized %s Customer_Success rows and %s feature_request rows.",
            result["customer_success_rows"],
            result["feature_request_rows"],
        )
    except (SQLAlchemyError, OSError, ValueError) as exc:
        logger.error("Sync failed: %s", exc)
        raise SystemExit(1) from exc
