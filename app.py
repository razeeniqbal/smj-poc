"""
Production Planning Dashboard - Top-Level Application Entry Point / WSGI Module.

Forwards to the application factory in the dashboard package.
Enables running via:
    python app.py
    flask run
    gunicorn app:app
"""

from dashboard import app, create_app

if __name__ == "__main__":
    print("[*] Starting Production Planning Dashboard Backend Service...")
    print("    URL: http://127.0.0.1:5000")
    print("    Package layout: dashboard/ (Application Factory & Blueprints)")
    app.run(host="127.0.0.1", port=5000, debug=True)
