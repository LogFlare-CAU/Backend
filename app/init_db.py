# app/init_db.py
"""Create/reset the SQLite database file and apply committed Alembic migrations.

Does NOT delete migration scripts — schema history lives under app/alembic/migrations.
"""
import os
import sys
from pathlib import Path


def run(cmd: str) -> int:
    print(f"[RUN] {cmd}")
    return os.system(cmd)


def main():
    print("WARNING: This will DELETE the existing SQLite database file!")
    print("Alembic migration scripts under app/alembic/migrations will be kept.")
    input("Press Enter to continue or Ctrl-C to abort...")

    project_root = Path(__file__).resolve().parents[0]
    dbfile = project_root / "db" / "mydb.sqlite"
    alembic_dir = project_root / "alembic"
    versions = alembic_dir / "migrations" / "versions"

    if not versions.exists() or not any(versions.glob("*.py")):
        print("ERROR: No Alembic revisions found under alembic/migrations/versions/")
        print("Commit migration scripts before running init_db.")
        sys.exit(1)

    if dbfile.exists():
        print("Deleting existing database")
        dbfile.unlink()

    dbfile.parent.mkdir(parents=True, exist_ok=True)

    os.chdir(alembic_dir)
    code = run("alembic upgrade head")
    if code != 0:
        print("ERROR: alembic upgrade failed")
        sys.exit(code or 1)

    # SQLite file path is relative to alembic CWD in some configs; also check app/db
    candidates = [
        dbfile,
        alembic_dir / "db" / "mydb.sqlite",
        project_root / "db" / "mydb.sqlite",
    ]
    if not any(p.exists() for p in candidates):
        print("WARNING: Database file not found at expected paths; check alembic URL.")
    else:
        print("Database initialized.")


if __name__ == "__main__":
    main()
