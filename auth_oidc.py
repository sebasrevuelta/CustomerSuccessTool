"""
OIDC authentication routes and setup.
"""
from __future__ import annotations

import os

import flask
from authlib.integrations.flask_client import OAuth


def oidc_enabled():
    return os.environ.get("OIDC_ENABLED", "false").strip().lower() == "true"


def _get_required(name: str):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} environment variable is required when OIDC_ENABLED=true")
    return value


def _get_redirect_uri():
    return _get_required("OIDC_REDIRECT_URI")


def setup_oidc(app):
    if not oidc_enabled():
        return

    oauth = OAuth(app)
    oauth.register(
        name="oidc",
        client_id=_get_required("OIDC_CLIENT_ID"),
        client_secret=_get_required("OIDC_CLIENT_SECRET"),
        server_metadata_url=_get_required("OIDC_DISCOVERY_URL"),
        client_kwargs={
            "scope": os.environ.get("OIDC_SCOPE", "openid profile email"),
        },
    )
    app.extensions["oidc_oauth"] = oauth


def register_auth_routes(app):
    @app.get("/login", endpoint="login")
    def login():
        if not oidc_enabled():
            return flask.redirect(flask.url_for("index"))
        oauth = app.extensions.get("oidc_oauth")
        if oauth is None:
            flask.abort(503, description="OIDC provider is not configured")

        next_url = flask.request.args.get("next") or flask.url_for("index")
        flask.session["post_login_redirect"] = next_url
        return oauth.oidc.authorize_redirect(_get_redirect_uri())

    @app.get("/auth/callback", endpoint="auth_callback")
    def auth_callback():
        if not oidc_enabled():
            return flask.redirect(flask.url_for("index"))
        oauth = app.extensions.get("oidc_oauth")
        if oauth is None:
            flask.abort(503, description="OIDC provider is not configured")

        token = oauth.oidc.authorize_access_token()
        userinfo = token.get("userinfo") or oauth.oidc.userinfo()
        flask.session["user"] = {
            "sub": userinfo.get("sub"),
            "name": userinfo.get("name"),
            "email": userinfo.get("email"),
        }
        if "id_token" in token:
            flask.session["id_token"] = token["id_token"]
        redirect_url = flask.session.pop("post_login_redirect", flask.url_for("index"))
        return flask.redirect(redirect_url)

    @app.get("/logout", endpoint="logout")
    def logout():
        if not oidc_enabled():
            return flask.redirect(flask.url_for("index"))
        flask.session.pop("user", None)
        flask.session.pop("id_token", None)
        flask.session.pop("post_login_redirect", None)
        return flask.redirect(flask.url_for("login"))
