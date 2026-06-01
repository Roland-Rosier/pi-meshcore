---
description: System architecture, remote constraints, and critical context requirements.
---

# System Architecture & Constraints

## 1. Underlying Architecture
* You run on the Qwen3-14B native reasoning architecture.
* Optimized for deep architectural planning.
* Optimized for greenfield code generation.
* Optimized for multi-turn tool execution precision.

## 2. Remote System Constraints
* CRITICAL: Shell capture is not supported due to running on a remote system.
* Execution relies entirely on the developer copying and pasting the output.
* Do not use shell commands unless there is absolutely no other way to achieve the result.
* Never use shell commands to edit files. Always edit them directly using appropriate internal tools.

## 3. Required Context Reading
* CRITICAL: Re-read the `AGENTS.md` file before acting on any prompt.

## 4. Specific Tool Selection & Header Protocols
* **File Header Insertion**: When tasked with inserting copyright notices, licenses, metadata headers, or other text at the absolute beginning of an existing file, you must explicitly use the `single_find_and_replace` tool. Do not rewrite the entire file.
* **Execution Strategy**: Identify the exact, literal string currently sitting at the absolute start of the target file (e.g., the first `import` statement, class definition, or top comment). Use that exact string as your search anchor within the `single_find_and_replace` parameters to prepend your header cleanly above it.