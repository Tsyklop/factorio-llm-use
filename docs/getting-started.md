# Getting started

This guide sets up a local server from a **copy of your existing world**, connects
an MCP assistant, and explains how to save and resume. The assistant has its own
character; it does not take over your mouse, keyboard or human player.

Use PowerShell on Windows, or a POSIX shell such as bash/zsh on Linux/macOS.
Run project commands from the repository root. Replace example installation paths
with your own. These instructions use game port **34199** and RCON port **27075**.

## 1. Install prerequisites and build

Install Git, Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).
For example, install uv on Windows with:

```powershell
winget install --id astral-sh.uv -e
```

On Linux/macOS, the official uv installer is:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Reopen your terminal after installation. You need Factorio 2.1; the implementation
was verified against 2.1.24. Use matching game versions, expansion settings and mods
for your server and any human clients. Steam can show the installation directory
through **Properties > Installed Files > Browse**.

Clone the repository if you do not have it yet (GitHub access is required):

```sh
git clone https://github.com/Tsyklop/factorio-llm-use.git
cd factorio-llm-use
```

The following commands work in both PowerShell and Unix shells:

```sh
uv sync --frozen
uv run python scripts/package_mod.py
```

The mod ZIP is `dist/factorio_llm_use_0.1.0.zip`. Leave it zipped.

## 2. Prepare your world and human client

In Factorio, save the world you want to use as **FOR_AI**, then return to the main
menu. This is the starting snapshot; subsequent server progress is stored separately.

Install the mod in your client if you want to join the server. The launchers install
it into the server's copied mod directory automatically.

### Windows

```powershell
Copy-Item -LiteralPath ".\dist\factorio_llm_use_0.1.0.zip" `
  -Destination "$env:APPDATA\Factorio\mods\"
```

### Linux

```sh
FACTORIO_USER="$HOME/.factorio"
mkdir -p "$FACTORIO_USER/mods"
cp dist/factorio_llm_use_0.1.0.zip "$FACTORIO_USER/mods/"
```

### macOS

```sh
FACTORIO_USER="$HOME/Library/Application Support/factorio"
mkdir -p "$FACTORIO_USER/mods"
cp dist/factorio_llm_use_0.1.0.zip "$FACTORIO_USER/mods/"
```

These are the [standard user-data locations](https://wiki.factorio.com/Application_directory).
Portable installs, custom configuration and Steam Flatpak can use other directories;
set the path to the directory containing your actual `saves` and `mods` folders.

In the Factorio client, enable **Factorio LLM Use** under **Mods**, apply the changes
and return to the main menu. Do not host the same session through the client as well.
The companion mod creates an empty AI character at the player force's spawn; it
does not supply free items or research.

## 3. Start the copied world

### Windows: hidden server

Set the executable path once in this PowerShell terminal:

```powershell
$FactorioExe = "D:\Programs\Steam\steamapps\common\Factorio\bin\x64\Factorio.exe"
.\scripts\start-server.ps1 `
  -FactorioExe $FactorioExe `
  -Save "$env:APPDATA\Factorio\saves\FOR_AI.zip"
```

If your mods are stored elsewhere, add `-SourceMods "D:\path\to\mods"`. If
PowerShell blocks local scripts, run `Set-ExecutionPolicy -Scope Process Bypass`
in this terminal and retry; this affects only the current PowerShell process.

The server runs in the background. Startup output reports its PID and ports;
inspect `.runtime/server.log` if startup fails. The script returning does not mean
that the world has finished loading.

### Linux/macOS: foreground server

Choose the executable and user-data directory for your installation. For example:

```sh
# Linux standalone installation (adjust the installation path).
FACTORIO_BIN="$HOME/games/factorio/bin/x64/factorio"
FACTORIO_USER="$HOME/.factorio"
```

Or, for a macOS Steam installation:

```sh
FACTORIO_BIN="$HOME/Library/Application Support/Steam/steamapps/common/Factorio/factorio.app/Contents/MacOS/factorio"
FACTORIO_USER="$HOME/Library/Application Support/factorio"
```

Then start the server:

```sh
uv run python scripts/start_server.py \
  --factorio "$FACTORIO_BIN" \
  --save "$FACTORIO_USER/saves/FOR_AI.zip" \
  --mods "$FACTORIO_USER/mods"
```

Leave this terminal open. Use a **second terminal in the repository root** for the
remaining commands. Logs are shown in the server terminal and written to
`.runtime/data/factorio-current.log`. For an unusual installation layout, add
`--read-data "/path/to/factorio/data"` (the directory containing `base/info.json`).

Both launchers bind the server and RCON to `127.0.0.1`, create a random password in
`.runtime/rcon-password.txt`, and refuse to replace an existing session with `FOR_AI`.
Wait for the server to finish loading before checking MCP. `.runtime/` is ignored
by Git; it contains your world data, logs and credentials.

## 4. Connect your assistant

### Codex desktop app or CLI

Install the Codex CLI so that `codex --version` works, then register the project
environment (same command on all platforms):

```sh
uv run python scripts/register_mcp.py
codex mcp list
```

This registers the **factorio-llm-use** stdio server. It reads the RCON password
from the local file rather than putting the password in the MCP configuration.
Register once. If you move the checkout and the old entry points to a different
Python executable, remove that entry before registering the new location:

```sh
codex mcp remove factorio-llm-use
uv run python scripts/register_mcp.py
```

Refresh the MCP connection or start a new Codex session if the tools are not visible.
Codex's desktop app and CLI share [MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
The MCP client starts the Python bridge automatically. Registering it does not
start Factorio or assign gameplay work.

### Other MCP clients

Use your client's stdio MCP configuration format. A typical Windows example:

```json
{
  "mcpServers": {
    "factorio-llm-use": {
      "command": "D:\\path\\factorio-llm-use\\.venv\\Scripts\\python.exe",
      "args": ["-m", "factorio_llm_use.server"],
      "env": {
        "FACTORIO_RCON_PASSWORD_FILE": "D:\\path\\factorio-llm-use\\.runtime\\rcon-password.txt",
        "FACTORIO_RCON_PORT": "27075"
      }
    }
  }
}
```

On Linux/macOS, use absolute paths such as
`/home/you/factorio-llm-use/.venv/bin/python` for `command` and
`/home/you/factorio-llm-use/.runtime/rcon-password.txt` for the password file.
On macOS a checkout may instead be under `/Users/you/`. Do not use `~` in JSON paths.
There is no need to run another Python bridge manually.

## 5. Verify the connection and optionally join

Give the assistant a read-only first task:

> Check the Factorio MCP connection with factorio_ping, get_agent_status and
> get_world. List available blueprint libraries and look for the RAILS book.
> Report the AI character, surfaces and book availability. Do not modify the world.

A successful ping confirms an authenticated connection to the mod. The AI status
should identify an independent character. A missing book is a blueprint access
issue, not proof that the connection failed. See troubleshooting below.

To play alongside the assistant, open Factorio and use **Multiplayer > Connect to
address**, entering **127.0.0.1:34199**. You and the assistant control separate
characters. Joining is optional; the assistant can work without a human connected.

After verification, assign a task explicitly. For example:

> Inspect the oil-processing build on my sandbox surface and the RAILS book.
> Find a suitable location in the main world and propose the factory and train
> connections. Show a preview before placing any ghosts or structures.

A preview only draws temporary overlays. Native construction ghosts can be built
by your construction robots as soon as they have materials. Ask specifically for
a preview, ghosts, or actual work according to what you want.

## 6. Save and stop

Closing the human client does **not** stop the server. The factory continues
simulating while humans are disconnected. The assistant acts during an active task;
installing MCP does not create an indefinite autonomous worker. Movement stops
after ten seconds without controller requests.

### Windows

```powershell
.\scripts\stop-server.ps1
```

The script requests a native save, verifies its ZIP, then stops the recorded project
server. If saving fails it leaves the server running.

### Linux/macOS

In the **second terminal**, from the repository root:

```sh
uv run python scripts/save_session.py
```

Wait for it to print the completed save path. Then press **Ctrl+C in the original
server terminal**. If saving fails, leave the server running and resolve the error
before stopping it. `save_session.py` saves only; it does not terminate the server.

## 7. Resume your progress

Use resume after the first start. Importing `FOR_AI.zip` again would use the old
snapshot rather than the server's progress, so the launchers refuse to overwrite it.

Windows (set `$FactorioExe` again if using a new terminal):

```powershell
.\scripts\start-server.ps1 -FactorioExe $FactorioExe -Resume
```

Linux/macOS (set `FACTORIO_BIN` again in a new terminal):

```sh
uv run python scripts/start_server.py --factorio "$FACTORIO_BIN" --resume
```

Resume selects the most recently modified ZIP under `.runtime/data/saves/`, or
`.runtime/session.zip` if no later saves exist. Keep the same game and mod versions.
The Unix launcher reuses the copied mod snapshot when resuming. The Windows launcher
copies files from `-SourceMods` again; use the same source directory on later starts.

To continue in single-player, stop the server, copy the completed `session-*.zip`
printed by the save command into your normal Factorio `saves` directory, and load
that copy with the matching mods enabled. The original `FOR_AI.zip` stays unchanged.
Back up the entire `.runtime/` directory when preserving or moving a session.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| No Factorio tools in the assistant | Run `codex mcp list`, verify the checkout/virtual-environment paths, then refresh the MCP connection or open a new session. |
| Connection refused | Check that Factorio finished loading and is listening on RCON port 27075; inspect the server log. Registration alone does not launch the game. |
| Authentication failed | The MCP password-file path must point to this checkout's `.runtime/rcon-password.txt`. Restart the MCP connection after changing credentials. |
| Mod/version mismatch or join failure | Match the client and server game versions and enabled mods, including Factorio LLM Use. Inspect the server and client logs for the actual error. |
| RAILS or another library book is missing | Some books are in a human player's personal library. Join once with that player and recheck the available libraries. Alternatively export a blueprint string or capture a built layout on a sandbox surface. |
| Source save not found | Save as `FOR_AI` in Factorio and check the actual user-data location; portable and Flatpak installations may differ from the defaults. |
| Existing session / occupied port | Resume the existing session, or save and stop it first. To start a different world, preserve and move the old `.runtime/` directory while the server and MCP connection are stopped, then register/start a fresh session. |

For custom ports, use `-GamePort`/`-RconPort` on Windows, or
`--game-port`/`--rcon-port` on Unix. Register MCP with
`uv run python scripts/register_mcp.py --port 27076` if using RCON port 27076.
Also pass `-RconPort 27076` to the Windows stop script, or run
`FACTORIO_RCON_PORT=27076 uv run python scripts/save_session.py` on Unix. Use your
chosen game port when joining. Advanced custom runtime directories require matching
password-file configuration and save handling; the commands above use `.runtime/`.

See [verification](verification.md) for the exact tested platforms and boundaries,
and [architecture](architecture.md) for the MCP/mod interface.
