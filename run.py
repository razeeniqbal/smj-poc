"""
CLI launcher for the Production Planning Dashboard.
Enables starting the dashboard server with customizable host and port.
"""

import argparse
from pathlib import Path
import sys

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dashboard import create_app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Production Planning Dashboard (6-Card Operations Cockpit)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to bind (default: 5000)",
    )
    parser.add_argument(
        "--no-debug",
        action="store_true",
        help="Disable Flask debug mode",
    )
    args = parser.parse_args()

    application = create_app(debug=not args.no_debug)

    env_mode = "Production" if args.no_debug else "Development (Debug)"

    print("=" * 65)
    print("  PRODUCTION PLANNING DASHBOARD (6-CARD OPERATIONS VIEW)")
    print("=" * 65)
    print(f"[*] Server running at: http://{args.host}:{args.port}")
    print(f"[*] Environment mode: {env_mode}")
    print("[*] Press Ctrl+C to stop the server.")
    print("=" * 65)

    application.run(host=args.host, port=args.port, debug=not args.no_debug)


if __name__ == "__main__":
    main()
