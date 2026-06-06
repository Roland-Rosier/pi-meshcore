---
name: Desktop Commander rule
---

# Shell tool use protocol

* You have access to the `desktop-commander` MCP Server.

# Constraints

* Avoid running any commands directly in the terminal and instead run any terminal commands via the `desktop-commander` MCP server.
* Only run terminal commands via the `desktop-commander` MCP server, using `start_process`, `interact_with_process` and `read_process_output` tools.
* When running the following terminal commands via the `desktop-commander` MCP Server, only send the `start_process` command and use its immediate output:
  - `git ls-files`
* When running the following terminal commands via the `desktop-commander` MCP Server, avoid using `interact_with_process` and `read_process_output`:
  - `git ls-files`
