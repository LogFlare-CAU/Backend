import importlib
import json
import sys
from pathlib import Path
from fastapi import FastAPI

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
APP_DIR = ROOT_DIR / "app"
if APP_DIR.is_dir() and str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def load_app(app_path: str) -> FastAPI:
    try:
        module_path, app_attr = app_path.split(":")
    except ValueError:
        print("APP_MODULE must be like 'package.module:app'", file=sys.stderr)
        sys.exit(1)
    module = importlib.import_module(module_path)
    app = getattr(module, app_attr, None)
    if app is None or not isinstance(app, FastAPI):
        print("Could not load FastAPI app from APP_MODULE.", file=sys.stderr)
        sys.exit(1)
    return app

def main():
    if len(sys.argv) < 2:
        print("Usage: export_openapi.py <package.module:app>", file=sys.stderr)
        sys.exit(1)
    app = load_app(sys.argv[1])
    schema = app.openapi()
    with open("openapi.json", "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    print("openapi.json exported.")

if __name__ == "__main__":
    main()
