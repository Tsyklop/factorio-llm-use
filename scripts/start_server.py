"""Prepare an isolated session and run Factorio in the foreground on Linux/macOS."""

import argparse
import json
import os
import secrets
import shutil
import socket
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOD_NAME = "factorio_llm_use"
MOD_FILE = MOD_NAME + "_0.1.1.zip"


def parser(project_root: Path) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--factorio", required=True, type=Path, help="Path to the game executable")
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--save", type=Path, help="Source ZIP to copy for a new session")
    mode.add_argument("--resume", action="store_true", help="Load the latest session save")
    result.add_argument(
        "--mods", type=Path, help="Source mods directory; required for a new session"
    )
    result.add_argument("--read-data", type=Path, help="Override the installed game data directory")
    result.add_argument("--game-port", type=int, default=34199)
    result.add_argument("--rcon-port", type=int, default=27075)
    result.add_argument("--runtime-directory", type=Path, default=project_root / ".runtime")
    result.add_argument(
        "--prepare-only", action="store_true", help="Write files without starting a game"
    )
    return result


def game_data(executable: Path, override: Path | None) -> Path:
    candidates = (
        [override.expanduser().resolve()]
        if override
        else [executable.parents[2] / "data", executable.parent.parent / "data"]
    )
    for candidate in candidates:
        if (candidate / "base/info.json").is_file():
            return candidate
    raise ValueError("Cannot locate game data (base/info.json). Provide --read-data explicitly.")


def check_ports(game_port: int, rcon_port: int) -> None:
    for port, kind in [(game_port, socket.SOCK_DGRAM), (rcon_port, socket.SOCK_STREAM)]:
        if not 1 <= port <= 65535:
            raise ValueError("Ports must be between 1 and 65535.")
        with socket.socket(socket.AF_INET, kind) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as error:
                raise ValueError(
                    f"Local port {port} is unavailable. Stop the existing server."
                ) from error


def prepare(args: argparse.Namespace, project_root: Path = PROJECT_ROOT) -> list[str]:
    executable = args.factorio.expanduser().resolve(strict=True)
    if not executable.is_file():
        raise ValueError("--factorio must name an executable file.")
    read_data = game_data(executable, args.read_data)
    runtime = args.runtime_directory.expanduser().resolve()
    data = runtime / "data"
    mods = runtime / "mods"
    session = runtime / "session.zip"
    check_ports(args.game_port, args.rcon_port)

    if args.resume:
        saves = list((data / "saves").glob("*.zip"))
        if saves:
            session = max(saves, key=lambda path: path.stat().st_mtime_ns)
        if not session.is_file() or not (mods / "mod-list.json").is_file():
            raise ValueError("No complete session exists to resume in this runtime directory.")
    else:
        if session.exists() or any((data / "saves").glob("*.zip")):
            raise ValueError("A session already exists. Use --resume; it will not be overwritten.")
        if args.mods is None:
            raise ValueError("Provide --mods for a new session.")
        source_mods = args.mods.expanduser().resolve(strict=True)
        if not source_mods.is_dir():
            raise ValueError("--mods must name a directory.")
        if runtime.is_relative_to(source_mods) or source_mods.is_relative_to(runtime):
            raise ValueError("Source mods and the runtime directory must not overlap.")
        source_save = args.save.expanduser().resolve(strict=True)
        if not source_save.is_file():
            raise ValueError("--save must name a save ZIP.")
        archive = project_root / "dist" / MOD_FILE
        if not archive.is_file():
            raise ValueError("Build the mod first: uv run python scripts/package_mod.py")
        if mods.exists() and any(mods.iterdir()):
            raise ValueError(
                "A mod snapshot already exists. Preserve it or use another runtime directory."
            )
        # Copy first; never enable the companion mod in the user's source directory.
        shutil.copytree(source_mods, mods, dirs_exist_ok=True)
        shutil.copy2(archive, mods / MOD_FILE)
        mod_list_path = mods / "mod-list.json"
        mod_list = (
            json.loads(mod_list_path.read_text(encoding="utf-8-sig"))
            if mod_list_path.exists()
            else {"mods": [{"name": "base", "enabled": True}]}
        )
        mod_list["mods"] = [entry for entry in mod_list["mods"] if entry["name"] != MOD_NAME]
        mod_list["mods"].append({"name": MOD_NAME, "enabled": True})
        mod_list_path.write_text(json.dumps(mod_list, indent=2), encoding="utf-8")
        shutil.copy2(source_save, session)

    (data / "saves").mkdir(parents=True, exist_ok=True)
    password_file = runtime / "rcon-password.txt"
    if not password_file.exists():
        password_file.write_text(secrets.token_hex(16), encoding="utf-8")
    if os.name != "nt":
        password_file.chmod(0o600)
    password = password_file.read_text(encoding="utf-8-sig").strip()
    if not password:
        raise ValueError("The RCON password file is empty.")
    config = runtime / "config.ini"
    config.write_text(
        f"[path]\nread-data={read_data.as_posix()}\nwrite-data={data.as_posix()}\n",
        encoding="utf-8",
    )
    settings = runtime / "server-settings.json"
    settings.write_text(
        json.dumps(
            {
                "name": "Factorio LLM Use",
                "description": "Local AI engineer session",
                "visibility": {"public": False, "lan": False},
                "require_user_verification": False,
                "auto_pause": False,
                "autosave_interval": 5,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return [
        str(executable),
        "--config",
        str(config),
        "--mod-directory",
        str(mods),
        "--start-server",
        str(session),
        "--server-settings",
        str(settings),
        "--bind",
        "127.0.0.1",
        "--port",
        str(args.game_port),
        "--rcon-bind",
        f"127.0.0.1:{args.rcon_port}",
        "--rcon-password",
        password,
    ]


def main(project_root: Path = PROJECT_ROOT) -> None:
    cli = parser(project_root)
    args = cli.parse_args()
    if os.name == "nt" and not args.prepare_only:
        cli.error(
            "Use scripts/start-server.ps1 on Windows, or --prepare-only to inspect preparation."
        )
    try:
        command = prepare(args, project_root)
        runtime = args.runtime_directory.expanduser().resolve()
        print(f"Session data and autosaves: {runtime / 'data'}", flush=True)
        print(f"Game: 127.0.0.1:{args.game_port}; RCON: 127.0.0.1:{args.rcon_port}", flush=True)
        if args.prepare_only:
            print("Prepared only; no game process started.")
            return
        print(
            "Keep this terminal open. Save from another terminal before pressing Ctrl+C.",
            flush=True,
        )
        os.chdir(runtime)
        os.execv(command[0], command)
    except (OSError, ValueError) as error:
        cli.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
