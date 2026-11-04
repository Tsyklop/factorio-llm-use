# Factorio LLM Use

Let an MCP assistant work in your Factorio world through its own AI engineer.
The companion mod provides world inspection, normal character actions, native
blueprint operations and train tools without desktop mouse or keyboard control.

**This mod requires the external Factorio LLM Use MCP server and an MCP client.**
The Python server connects to a locally hosted Factorio server through RCON.

The MCP server repository is currently private; access is required to use the
linked setup guide.

- [Installation and usage for Windows, Linux and macOS](https://github.com/Tsyklop/factorio-llm-use/blob/main/docs/getting-started.md)
- [Source code and MCP server](https://github.com/Tsyklop/factorio-llm-use)

## What the assistant can do

- Inspect surfaces, entities, inventories, fluids, recipes, research and rail networks.
- Walk, mine and craft over game ticks; build using its real inventory and transfer items.
- Configure production machines and stations, and inspect or update train schedules.
- Read available blueprint libraries and nested books, including existing rail books.
- Capture layouts built on sandbox surfaces, compare building sites and compose plans.
- Draw a temporary preview or explicitly place native construction ghosts.
- Use an advanced Lua tool for other game capabilities and mod remote interfaces.

There are no entity-name placement whitelists or inventory-role whitelists. Tools
discover installed prototypes and use native game mechanics. Reach, collision,
materials and recipe availability still apply to ordinary actions.

## Using an existing world

The supplied launchers start a server from a copy of your save and mods. Your
original save stays unchanged; server progress is saved separately and can be
resumed. A human player can join the local server and play alongside the assistant.
The assistant also works without a human connected.

The mod creates an empty AI character near the player force's spawn. It does not
provide starter items or unlock research. Installing it does not assign a factory
project: give the assistant an explicit task, such as inspection, construction,
repair, production changes or transport.

For blueprint work, ask for a preview before placement when you want to review the
plan. Construction ghosts are real ghosts and may be built by supplied robots.

## Requirements and coverage

- Factorio 2.1, with matching game versions, expansion settings and enabled mods
  on the server and any joining human clients.
- Python 3.12+, uv and an MCP client for the external server.
- A local Factorio server with RCON; the setup guide supplies the commands.

Developed and tested with Factorio 2.1.24 on Windows. Linux/macOS launcher and
configuration checks are distinct from real game verification; see the
[verification report](https://github.com/Tsyklop/factorio-llm-use/blob/main/docs/verification.md).
Space Age is optional. Compatibility with every third-party mod and mechanic has
not been established, and reliable autonomous combat has not been verified.

## License

MIT. The companion mod and MCP server are an independent implementation.
