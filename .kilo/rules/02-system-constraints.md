---
name: System Constraints
globs: "**/*"
alwaysApply: true
---
# Constraints

### Architecture Capabilities
* **Arch**: Qwen3 native reasoning. Optimized for deep planning and multi-turn tool precision.

### File Header Protocol
* **Headers**: When prepending metadata or licenses to a file, modify only the top of the file. 
* **Anchor Strategy**: Use the absolute first line of the target file as your anchor string. 
* **Constraint**: Do **NOT** rewrite the entire file to insert headers.

### Python execution protocul
* **Virtual Environment**: Use the project's Python virtual environment to execute any python commands.
