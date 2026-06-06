---
description: Native Dual-Phase Protocol
---
# Execution Protocol

## PHASE 1: Reasoning Strategy
- Leverage native reasoning capabilities to plan the blueprint.
- Meticulously analyze 4 elements before producing output payload:
  1. **DESIGN & DATA TYPES**: Global state models, types, schemas, API routes.
  2. **APPLICATION LAYOUT**: Visual text directory structure.
  3. **PITFALLS**: Exactly 3 technical edge cases (race conditions, sync, async blocks).
  4. **DEPENDENCY LOOP CHECK**: Confirm 0 circular file links.

## PHASE 2: Payloads & Code Execution
- Output raw tool call schemas/JSON directly outside of reasoning space. Do not introduce or summarize payload actions.
- Max 2 file additions/edits per conversational turn to ensure memory stability.
- Batch changes exceeding 2 files, asking user permission to proceed.
- Do not rewrite entire files. Output target code modifications only.

### Top-of-File Header Insertion Payload Pattern:
```json
{"filepath": "src/main.py", "find": "import os", "replace": "# Copyright (c) 2026 Project Authors. All rights reserved.\n\nimport os"}
```