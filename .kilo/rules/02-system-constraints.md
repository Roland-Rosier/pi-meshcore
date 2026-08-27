---
name: System Constraints
globs: "**/*"
alwaysApply: true
---
# Constraints

### Architecture Capabilities
* **Arch**: Qwen3 native reasoning. Optimized for deep planning and multi-turn tool precision.

### File Header Protocol
* **Headers**: Prepend metadata/licenses with the native `single_find_and_replace` tool.
* **Anchor Strategy**: Use the absolute first line of the target file as your anchor string. 
* **Constraint**: Do **NOT** rewrite the entire file to insert headers.

### Python execution protocul
* **Virtual Environment**: Use the project's Python virtual environment to execute any python commands.
