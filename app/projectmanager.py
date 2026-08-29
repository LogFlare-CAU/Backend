import asyncio
import sys
from typing import Sequence

from sqlalchemy import select

from common.sqlsession import async_session
from routes.projects import model, schema, service


async def _list_projects(session) -> Sequence[model.Project]:
    projects = await service.list_projects(session, load=True)
    if not projects:
        print("No projects found.")
        return []
    for project in projects:
        print(
            f"[{project.id}] {project.name} "
            f"(token={project.token}) logfiles={len(project.logfiles)}"
        )
    return projects


async def _select_project(session) -> model.Project | None:
    await _list_projects(session)
    raw = input("Enter project ID: ").strip()
    if not raw.isdigit():
        print("Invalid project ID.")
        return None
    project_id = int(raw)
    try:
        return await service.get_project(session, project_id, load=True)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to load project: {exc}")
        return None


async def _create_project(session) -> None:
    name = input("Project name: ").strip()
    if not name:
        print("Project name is required.")
        return
    project = await service.create_project(
        session, schema.ProjectCreateParams(name=name)
    )
    print(f"Created project [{project.id}] {project.name} token={project.token}")


async def _delete_project(session) -> None:
    project = await _select_project(session)
    if not project:
        return
    confirm = input(f"Delete project '{project.name}'? (y/N): ").strip().lower()
    if confirm != "y":
        print("Canceled.")
        return
    await service.delete_project(session, project.id)
    print("Project deleted.")


async def _rename_project(session) -> None:
    project = await _select_project(session)
    if not project:
        return
    new_name = input("New project name: ").strip()
    if not new_name:
        print("Project name is required.")
        return
    updated = await service.update_project(
        session, project.id, schema.ProjectCreateParams(name=new_name)
    )
    print(f"Renamed project to '{updated.name}'.")


async def _list_logfiles(session) -> None:
    project = await _select_project(session)
    if not project:
        return
    if not project.logfiles:
        print("No logfiles for this project.")
        return
    for logfile in project.logfiles:
        print(f"[{logfile.id}] {logfile.file_name} -> {logfile.file_path}")


async def _add_logfile(session) -> None:
    project = await _select_project(session)
    if not project:
        return
    name = input("Logfile name: ").strip()
    path = input("Logfile path: ").strip()
    if not name or not path:
        print("Logfile name and path are required.")
        return
    logfile = await service.add_logfile(
        session, project.id, schema.LogFileCreateParams(name=name, path=path)
    )
    print(f"Added logfile [{logfile.id}] {logfile.file_name} -> {logfile.file_path}")


async def _delete_logfile(session) -> None:
    project = await _select_project(session)
    if not project:
        return
    raw = input("Logfile ID to delete: ").strip()
    if not raw.isdigit():
        print("Invalid logfile ID.")
        return
    logfile_id = int(raw)
    await service.delete_logfile(session, project.id, logfile_id)
    print("Logfile deleted.")


async def _update_logfile(session) -> None:
    project = await _select_project(session)
    if not project:
        return
    raw = input("Logfile ID to update: ").strip()
    if not raw.isdigit():
        print("Invalid logfile ID.")
        return
    logfile_id = int(raw)
    stmt = select(model.LogFile).where(
        model.LogFile.id == logfile_id,
        model.LogFile.project_id == project.id,
    )
    result = await session.execute(stmt)
    logfile = result.scalars().first()
    if not logfile:
        print("Logfile not found.")
        return
    new_name = input(f"New logfile name (blank to keep '{logfile.file_name}'): ").strip()
    new_path = input(f"New logfile path (blank to keep '{logfile.file_path}'): ").strip()
    if new_name:
        logfile.file_name = new_name
    if new_path:
        logfile.file_path = new_path
    await session.commit()
    await session.refresh(logfile)
    print(f"Updated logfile [{logfile.id}] {logfile.file_name} -> {logfile.file_path}")


def _print_menu() -> None:
    print("\nLogFlare Project Manager")
    print("1) List projects")
    print("2) Create project")
    print("3) Delete project")
    print("4) Rename project")
    print("5) List logfiles in project")
    print("6) Add logfile to project")
    print("7) Delete logfile from project")
    print("8) Update logfile in project")
    print("0) Exit")


async def _run_cli() -> None:
    async with async_session() as session:
        while True:
            _print_menu()
            choice = input("Select: ").strip()
            if choice == "1":
                await _list_projects(session)
            elif choice == "2":
                await _create_project(session)
            elif choice == "3":
                await _delete_project(session)
            elif choice == "4":
                await _rename_project(session)
            elif choice == "5":
                await _list_logfiles(session)
            elif choice == "6":
                await _add_logfile(session)
            elif choice == "7":
                await _delete_logfile(session)
            elif choice == "8":
                await _update_logfile(session)
            elif choice == "0":
                print("Bye.")
                sys.exit(0)
            else:
                print("Unknown option.")


def main() -> None:
    asyncio.run(_run_cli())


if __name__ == "__main__":
    main()
