"""
Settings page route.
"""
from __future__ import annotations

import flask


def register_settings_routes(app):
    @app.get("/settings", endpoint="settings")
    def settings():
        return flask.render_template("settings.html", active_page="settings")
