# Project instructions

- Build a general Factorio tool. Do not start a gameplay assignment merely because the tool is installed.
- Keep source, documentation and tool descriptions in English. Preserve user blueprint labels and world data.
- Do not introduce entity-name placement whitelists or per-entity inventory-role whitelists.
- Use installed prototypes, native mechanics and normal materials for ordinary gameplay operations.
- Keep game-tick event handlers in mod source so they survive save/load and multiplayer joins.
- Use independent reads of the real engine state to verify action outcomes. Python boundary doubles are not gameplay proof.
- Run engine tests only on isolated copies under `.runtime/`. Never commit saves, user blueprint data, passwords or logs.
- Separate Python checks, actual engine checks, hosted CI and actual user-world evidence in reports.
- Keep combat primitives distinct from unverified claims of reliable autonomous combat.
