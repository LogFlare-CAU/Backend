# app/initdb.py
import os
import sys
import shutil
from pathlib import Path


def run(cmd: str) -> int:
    print(f"[RUN] {cmd}")
    return os.system(cmd)


def main():
    print("WARNING: This will DELETE existing database and migrations!")
    input("Press Enter to continue or Ctrl-C to abort...")

    project_root = Path(__file__).resolve().parents[0]
    dbfile = project_root / "db" / "mydb.sqlite"
    env_py = project_root / "alembic" / "migrations" / "env.py"
    env_py_copy = project_root / "alembic" / "env.py.copy"
    migraions_dir = project_root / "alembic" / "migrations"

    if dbfile.exists():
        print("Deleting existing database")
        dbfile.unlink()

    if migraions_dir.exists():
        print("Deleting existing migrations")
        shutil.rmtree(migraions_dir)

    os.chdir(project_root)
    os.chdir("./alembic")
    run("alembic init migrations")
    env_py.unlink()
    shutil.copyfile(env_py_copy, env_py)
    run("alembic revision --autogenerate")
    run("alembic upgrade head")
    print("Database initialized.")

    if not dbfile.exists():
        print("ERROR: Database file was not created!")
        sys.exit(1)


if __name__ == "__main__":
    main()
