# Verification

## Local results, 2026-11-04

- Core Python: 10 tests passed on Python 3.12.13 and Python 3.14.6.
- Real engine: 30 checks passed on Factorio 2.1.24, Windows, Space Age enabled,
  with an isolated copy of an existing world and its local mod collection.
- The engine suite drives the actual stdio MCP server and reads action outcomes
  independently through RCON. It does not assert only that an action method was called.
- Separate launcher checks loaded the packaged ZIP without its source directory,
  authenticated the exact registered Codex MCP command using its password file,
  enumerated 29 tools, saved/stopped the session, and resumed the latest native save
  with the same AI identity. The bootstrap session was then saved and stopped.
- Setup guide: the expanded suite has 18 tests. On Windows/Python 3.14.6,
  17 passed and the Unix-only process test was skipped. Preparation tests inspect
  the copied files and generated configuration, preserved source hashes,
  overwrite protection, latest-save selection, mod-snapshot reuse, occupied-port
  handling and macOS data-directory discovery.
- An additional real Windows engine smoke check consumed the Python launcher's
  generated configuration and packaged mod, authenticated RCON, completed and
  verified a native save, then resumed it with the same AI identity. Source save
  and mod-file hashes remained unchanged. The test server was stopped afterward.

The 30 engine checks cover:

1. MCP initialization and tool discovery.
2. Independent AI creation with empty inventory.
3. World and sandbox surface enumeration.
4. Generic observation with the Factorio 2.1 fluid interface.
5. Player blueprint library access.
6. Nested RAILS book enumeration.
7. Actual pathfinding movement with no connected human.
8. Refinery and assembler-2 placement with real item consumption.
9. Rejected placement preserving world state when an item is missing.
10. Real inventory transfer into a steel chest.
11. Assembler-2 recipe configuration.
12. Timed hand crafting and its actual product.
13. Native blueprint capture.
14. Recipe preservation in the captured blueprint.
15. Overlay preview creating zero construction ghosts.
16. Native plan application creating three ghosts.
17. Recipe preservation on the actual assembler ghost.
18. Reapplying a plan without duplicate construction.
19. Candidate site screening.
20. Train inspection.
21. Research and recipe inspection.
22. A repeated request spending exactly one item.
23. Timed resource mining adding actual ore.
24. Structure recovery returning the structure and contents.
25. Cancelled movement reaching a stable stopped position.
26. A selected train's schedule persisted in the engine.
27. Connected-rail topology inspection.
28. Native blueprint placement of actual rail ghosts.
29. AI identity and inventory surviving save/load.
30. Plan state surviving save/load.

Python tests exercise real socket framing, fragmented Unicode packets, authentication
rejection, malformed packets, response/request matching, retry identity after a lost
response, actionable game errors and MCP schema/transport contracts. They are not a
substitute for the engine suite.

## Reproduce

```powershell
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -p 'test_*.py'
uv run python scripts/verify_engine.py --factorio 'D:\path\Factorio.exe' --save 'D:\saves\world.zip' --mods 'D:\path\mods'
```

The engine runner copies both save and mods into a new ignored `.runtime/verify-*`
directory, binds the temporary server only to loopback, and stops its own subprocess
at the end. It creates a separate verification surface, supplies fixture items there,
and uses administrative Lua only to prepare fixtures and independently inspect results.
Those preparations are test setup, not ordinary gameplay tool behavior. The source
save is never used as the engine's write target. Reports and logs remain local.

## Boundaries

These results do not establish reliable autonomous combat, a complete factory
assignment, visual client-side multiplayer join behavior, or universal compatibility
with every mod and mechanic. The rail tools expose actual topology and native
blueprint placement; they do not by themselves certify throughput, signaling design
or deadlock freedom of an arbitrary proposed network.

The source-mod engine suite is distinct from launcher/ZIP checks. Hosted CI runs
Python checks and packaging on Windows, Linux and macOS; it does not run the
proprietary game binary. The Unix process test launches a small fixture executable
that consumes the generated configuration, not Factorio. Linux/macOS gameplay and
native game shutdown on those platforms have not been verified. A passed local
engine suite must not be reported as a hosted engine run.
