"""Run a test probe on isolated engine copies using files instead of RCON."""

import argparse
import hashlib
import json
import shutil
import socket
import subprocess
import time
import zipfile
from pathlib import Path
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factorio", type=Path, required=True)
    parser.add_argument("--save", type=Path, required=True)
    parser.add_argument("--old-mod", type=Path, required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    root = project / ".runtime" / ("offline-respawn-" + uuid4().hex[:8])
    mods = root / "mods"
    mods.mkdir(parents=True)
    (root / "data/saves").mkdir(parents=True)
    original_hash = hashlib.sha256(args.save.read_bytes()).hexdigest()
    copied = root / "source-copy.zip"
    shutil.copy2(args.save, copied)
    with zipfile.ZipFile(args.old_mod) as archive:
        archive.extractall(mods)
    listing = {
        "mods": [
            {"name": n, "enabled": True}
            for n in (
                "base",
                "quality",
                "elevated-rails",
                "space-age",
                "factorio_llm_use",
                "respawn_probe",
            )
        ]
    }
    (mods / "mod-list.json").write_text(json.dumps(listing), encoding="utf-8")
    probe = mods / "respawn_probe_1.0.0"
    probe.mkdir()
    (probe / "info.json").write_text(
        json.dumps(
            {
                "name": "respawn_probe",
                "version": "1.0.0",
                "title": "Isolated respawn observer",
                "author": "test",
                "factorio_version": "2.1",
                "dependencies": ["factorio_llm_use >= 0.1.1"],
            }
        ),
        encoding="utf-8",
    )
    shutil.copy2(project / "tests/respawn_probe.lua", probe / "control.lua")
    config = root / "config.ini"
    config.write_text(
        f"[path]\nread-data={(args.factorio.parents[2] / 'data').as_posix()}\n"
        f"write-data={(root / 'data').as_posix()}\n",
        encoding="utf-8",
    )
    reports = []
    settings = root / "server-settings.json"
    settings.write_text(
        json.dumps(
            {
                "name": "Isolated respawn test",
                "description": "Disposable test copy",
                "visibility": {"public": False, "lan": False},
                "require_user_verification": False,
                "auto_pause": False,
                "autosave_interval": 0,
            }
        ),
        encoding="utf-8",
    )
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as temporary_socket:
        temporary_socket.bind(("127.0.0.1", 0))
        game_port = temporary_socket.getsockname()[1]

    def run(mode, save):
        (probe / "test_mode.lua").write_text('return "' + mode + '"', encoding="utf-8")
        marker = root / "data/script-output/respawn-complete.txt"
        if marker.exists():
            marker.unlink()
        log_path = root / (mode + ".log")
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [
                    str(args.factorio),
                    "--config",
                    str(config),
                    "--mod-directory",
                    str(mods),
                    "--start-server",
                    str(save),
                    "--server-settings",
                    str(settings),
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(game_port),
                ],
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                deadline = time.monotonic() + 35
                while not marker.exists():
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(f"Engine test failed: {mode}; see {log_path}")
                    time.sleep(0.1)
                # Only this disposable child process is stopped. Windows builds
                # do not consistently accept headless commands through stdin.
                process.terminate()
                process.wait(timeout=10)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
        print(log_path.read_text(encoding="utf-8")[-7000:], flush=True)
        report = json.loads((root / "data/script-output/respawn-report.json").read_text())
        if report["mode"] != mode:
            raise AssertionError("Test runner did not execute expected mode")
        reports.append(report)

    run("legacy", copied)
    old_sources = [path for path in mods.glob("factorio_llm_use_*") if path.is_dir()]
    new_sources = [path for path in (project / "mod").glob("factorio_llm_use_*") if path.is_dir()]
    if len(old_sources) != 1 or len(new_sources) != 1:
        raise ValueError("Expected exactly one original and one updated companion mod directory")
    shutil.move(str(old_sources[0]), str(root / "original-mod"))
    shutil.copytree(new_sources[0], mods / new_sources[0].name)
    run("upgrade", root / "data/saves/legacy-dead.zip")
    run("reload", root / "data/saves/pending-respawn.zip")
    assert hashlib.sha256(args.save.read_bytes()).hexdigest() == original_hash
    (root / "report.json").write_text(
        json.dumps(
            {"reports": reports, "source_unchanged": True, "source_sha256": original_hash}, indent=2
        ),
        encoding="utf-8",
    )
    print("PASS source save unchanged\nReport: " + str(root / "report.json"), flush=True)


if __name__ == "__main__":
    main()
