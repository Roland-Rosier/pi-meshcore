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