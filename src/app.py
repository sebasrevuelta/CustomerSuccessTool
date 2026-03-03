"""
Application entrypoint and route registration.
"""
import os

import flask
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

from auth_oidc import oidc_enabled, register_auth_routes, setup_oidc
from dashboard_page import register_dashboard_routes
from feature_requests_page import register_feature_request_routes
from settings_page import register_settings_routes
from trends_page import register_trends_routes

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


app = flask.Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = _env_bool("SESSION_COOKIE_SECURE", False)
app.config["SESSION_COOKIE_SAMESITE"] = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
app.config["SESSION_COOKIE_NAME"] = os.environ.get(
    "SESSION_COOKIE_NAME", "customer_success_session"
)

if _env_bool("TRUST_PROXY_HEADERS", False):
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=int(os.environ.get("PROXY_FIX_X_FOR", "1")),
        x_proto=int(os.environ.get("PROXY_FIX_X_PROTO", "1")),
        x_host=int(os.environ.get("PROXY_FIX_X_HOST", "1")),
        x_port=int(os.environ.get("PROXY_FIX_X_PORT", "1")),
    )

setup_oidc(app)
register_auth_routes(app)
register_dashboard_routes(app)
register_feature_request_routes(app)
register_settings_routes(app)
register_trends_routes(app)


@app.before_request
def require_login():
    if not oidc_enabled():
        return None
    if flask.request.endpoint is None:
        return None
    exempt_endpoints = {"login", "auth_callback", "logout", "static"}
    if flask.request.endpoint in exempt_endpoints:
        return None
    if flask.session.get("user"):
        return None
    return flask.redirect(flask.url_for("login", next=flask.request.url))


@app.context_processor
def inject_auth_context():
    return {
        "oidc_enabled": oidc_enabled(),
        "current_user": flask.session.get("user"),
    }


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
