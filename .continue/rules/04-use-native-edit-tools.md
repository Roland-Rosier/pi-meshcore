---
name: Enforce Native File Editing Tools
---

# Enforce Native File Editing Tools

You are running inside a Continue.dev workspace environment with native tools enabled. You MUST NOT use `<tool_code>`, `<tool_call>`, or pythonic block calls like `read_file(filepath="...")`.

### Core Directive
When modifying, editing, or updating any file, you MUST invoke the native `single_find_and_replace` tool call via the API. Do not write out the code changes as text blocks.

### Tool Selection Rules
* **To read a file**: Use the native `read_file` tool.
* **To view active editor**: Use the native `read_currently_open_file` tool.
* **To modify a file**: Use the native `single_find_and_replace` tool.
* **To create a file**: Use the native `create_new_file` tool if the file does not exist.

### Correct use of tools
* **When using the `create_new_file` tool**: You must always provide the key "contents" in your JSON object.

### Execution Constraints
* Never use MCP servers for direct file system operations.
* Never use custom tags like `<tool_code>` or manual JSON markdown wrappers.
* Rely exclusively on the standard OpenAI tool-calling API payload structure provided in your system context.
* You **must* invoke your native `single_find_and_replace` tool capability to apply the changes directly.
* If a requested file does not exist, use the `create_new_file` tool first.
