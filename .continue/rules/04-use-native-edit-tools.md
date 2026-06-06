---
name: Enforce Native File Editing Tools
---

# Enforce Native File Editing Tools

You are running inside a Continue.dev workspace environment with native tools enabled. You MUST NOT use `<tool_code>`, `<tool_call>`, or pythonic block calls like `read_file(filepath="...")`.

### Core Directive
When modifying, editing, or updating any file, you MUST invoke the native `edit_existing_file` tool call via the API. Do not write out the code changes as text blocks.

### Tool Selection Rules
* **To read a file**: Use the native `read_file` tool.
* **To view active editor**: Use the native `read_currently_open_file` tool.
* **To modify code**: Use the native `edit_existing_file` tool.
* **To create a file**: Use the native `create_new_file` tool if the file does not exist.

### Execution Constraints
* Never use MCP servers for direct file system operations.
* Never use custom tags like `<tool_code>` or manual JSON markdown wrappers.
* Rely exclusively on the standard OpenAI tool-calling API payload structure provided in your system context.
* You **must* invoke your native `edit_existing_file` tool capability to apply the changes directly to the codebase.
* If a requested file does not exist, use the `create_new_file` tool first.
