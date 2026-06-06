---
name: Enforce Native File Editing Tools
---

# Enforce Native File Editing Tools

When a file is being modified, edited, or updated, invoke your `edit_existing_file` tool capability to apply those changes.

### Hard Requirements
* You **must* invoke your native `edit_existing_file` tool capability to apply the changes directly to the codebase.
* If a requested file does not exist, use the `create_new_file` tool first.
* Do not use any MCP Server to perform any file creation or modification.