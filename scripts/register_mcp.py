"""Register the installed project in Codex without embedding a password in its config."""

import argparse
import copy
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=27075)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    password_file = root / ".runtime/rcon-password.txt"
    password_file.parent.mkdir(exist_ok=True)
    if not password_file.exists():
        password_file.write_text(uuid4().hex, encoding="utf-8")
    config_file = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "config.toml"
    before = (
        tomllib.loads(config_file.read_text(encoding="utf-8-sig")) if config_file.exists() else {}
    )
    previous = before.get("mcp_servers", {}).get("factorio-llm-use")
    if previous and previous.get("command") != sys.executable:
        raise RuntimeError("An unrelated factorio-llm-use MCP entry already exists")
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("Codex CLI is not on PATH")
    command = [
        codex,
        "mcp",
        "add",
        "factorio-llm-use",
        "--env",
        f"FACTORIO_RCON_PASSWORD_FILE={password_file}",
        "--env",
        f"FACTORIO_RCON_PORT={args.port}",
        "--",
        sys.executable,
        "-m",
        "factorio_llm_use.server",
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    after = tomllib.loads(config_file.read_text(encoding="utf-8-sig"))
    configured = copy.deepcopy(after["mcp_servers"].pop("factorio-llm-use"))
    if "mcp_servers" in before:
        before["mcp_servers"].pop("factorio-llm-use", None)
    elif not after["mcp_servers"]:
        after.pop("mcp_servers")
    if before != after:
        changed = [key for key in set(before) | set(after) if before.get(key) != after.get(key)]
        raise RuntimeError("Other Codex configuration sections changed: " + ", ".join(changed))
    if configured.get("command") != sys.executable:
        raise RuntimeError("Registered MCP command did not match this virtual environment")
    print("Registered factorio-llm-use. Other Codex configuration was preserved.")
    print(
        "The game must be hosted with the mod and matching RCON settings before game calls succeed."
    )


if __name__ == "__main__":
    main()
