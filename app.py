"""
Application entrypoint and route registration.
"""
import os
import secrets

import flask
from dotenv import load_dotenv

from auth_oidc import oidc_enabled, register_auth_routes, setup_oidc
from dashboard_page import register_dashboard_routes
from feature_requests_page import register_feature_request_routes
from settings_page import register_settings_routes
from trends_page import register_trends_routes

load_dotenv()

app = flask.Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

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
