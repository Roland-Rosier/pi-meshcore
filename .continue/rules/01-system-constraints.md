---
description: System Constraints
---
# Constraints
- **Arch**: Qwen3-14B native reasoning. Optimized for deep planning and multi-turn tool precision.
- **Remote**: Shell capture unsupported. Forbidden to use shell commands for file editing; use internal tools. Developer must manually execute terminal tools.
- **Headers**: Prepend metadata/licenses with `single_find_and_replace` using the absolute first line of the file as an anchor. Do not rewrite.