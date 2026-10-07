"""
Production Planning Dashboard Package.

Can be run standalone:
    from dashboard import create_app
    app = create_app()
    app.run()

Or easily integrated into a colleague's Flask application as a Blueprint:
    from dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)
"""

from pathlib import Path
from flask import Flask

from dashboard.routes import dashboard_bp

PACKAGE_DIR = Path(__file__).resolve().parent


def create_app(debug: bool = True) -> Flask:
    """Create a standalone Flask application instance serving the dashboard."""
    application = Flask(
        __name__,
        template_folder=str(PACKAGE_DIR / "templates"),
        static_folder=str(PACKAGE_DIR / "static"),
    )
    application.config["DEBUG"] = debug
    application.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB max upload

    # Mount the dashboard Blueprint at root
    application.register_blueprint(dashboard_bp)

    return application


# Default application instance for quick imports and WSGI servers
app = create_app()

__all__ = ["dashboard_bp", "create_app", "app"]
