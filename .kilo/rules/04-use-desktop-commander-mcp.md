---
name: Desktop Commander Rule
globs: "**/*"
alwaysApply: true
---
# Shell Tool Use Protocol
* You have access to the `desktop-commander` MCP Server.

# Constraints
* Only execute terminal commands via the `desktop-commander` MCP server by calling the `start_process`, `interact_with_process`, and `read_process_output` tools.

### High-Speed Execution (Immediate Output Only)
When running the following terminal commands via the `desktop-commander` MCP Server, send **ONLY** the `start_process` tool call and capture its immediate response. Do **NOT** wait or loop:
* `git ls-files`

### Interaction Restrictions
When running the following terminal commands via the `desktop-commander` MCP Server, you **MUST NOT** invoke `interact_with_process` or `read_process_output`:
* `git ls-files`
