"""Complete a new native server save before a session is stopped."""

import os
import time
import zipfile
from datetime import datetime
from pathlib import Path

from factorio_llm_use.bridge import Bridge


def main():
    root = Path(__file__).resolve().parents[1] / ".runtime"
    password = (root / "rcon-password.txt").read_text(encoding="utf-8-sig").strip()
    port = int(os.environ.get("FACTORIO_RCON_PORT", "27075"))
    bridge = Bridge(password, port=port)
    name = "session-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    target = root / "data/saves" / (name + ".zip")
    bridge.command("/server-save " + name)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with zipfile.ZipFile(target) as archive:
                if archive.testzip() is None:
                    print(target)
                    return
        except (OSError, zipfile.BadZipFile):
            pass
        time.sleep(0.1)
    raise TimeoutError("Native save did not complete; the server has not been stopped")


if __name__ == "__main__":
    main()
