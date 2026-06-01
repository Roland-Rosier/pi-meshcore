---
description: Enforces the separation between the native reasoning phase and strict tool execution.
---

# Dual-Phase Execution Protocol

You must process every user prompt using a dual-phase execution logic. Never blend the architectural planning phase with the tool execution phase.

## PHASE 1: The Native Reasoning Engine (`<think>`)
* Open a native `<think>` block at the absolute beginning of your response.
* Inside this block, meticulously draft the architectural blueprint before writing code or invoking tools.
* Map out the following four components:
  1. **DESIGN & DATA TYPES**: Explicitly write out the global state models, type definitions, API endpoints, or database schemas required.
  2. **APPLICATION LAYOUT**: Map out a clear, visual text-based folder structure and file hierarchy for the greenfield project.
  3. **POTENTIAL PITFALLS**: Identify exactly 3 technical edge-cases (e.g., race conditions, async performance blocks, state sync problems) this implementation must circumvent.
  4. **DEPENDENCY LOOP CHECK**: Verify that no files or functions you plan to create will generate circular dependencies.
* Immediately close the reasoning engine with the literal tag: `</think>`

## PHASE 2: Strict Tool Execution & Code Modification Payloads
* Strictly forbidden from outputting any markdown code blocks, file-creation syntaxes, or functional JSON tool invocations inside the `<think>` block.
* All functional payloads must occur AFTER the closing `</think>` tag.
* CRITICAL: If you plan a tool call or bash command inside your `<think>` block, you MUST explicitly output the raw tool call schema outside and AFTER the closing `</think>` tag. 
* Do not summarize the action in text; emit the functional payload.
* Emit the literal text payload or structured JSON schema required to activate your local agent framework's tools (e.g., creating files, running terminal scripts).
* Do not summarize what you are about to do in conversational text. 
* Do not introduce the tool call. Let the tool payloads speak for themselves.
* Limit file creations or edits to a maximum of 2 files per conversational turn to protect memory stability.
* If more than 2 files need to be created or edited, plan the action in batches of no more than 2 files, telling the
user what you plan to do and allowing them to continue after each batch.
* All functional payloads must occur AFTER the closing `</think>` tag.
* CRITICAL EDIT PROTOCOL: When modifying an existing file, DO NOT rewrite the entire file from scratch.
* You must output ONLY the specific lines of code that need changing.
* Only output a complete, standalone code block if you are creating a brand-new file that does not exist.
* Limit file creations or edits to a maximum of 2 files per conversational turn to protect memory stability.

### Top-of-File Insertion Protocol via `single_find_and_replace`
* When inserting a copyright header, structural block, or other text at the top of a file, you must invoke the `single_find_and_replace` tool. 
* Emphasize precision: Anchor your change to the very first line of code in the file to control exactly what is injected at the beginning of the file.

* **Required `single_find_and_replace` Payload Structure:**
  ```json
  {
    "filepath": "src/main.py",
    "find": "import os",
    "replace": "# Copyright (c) 2026 Project Authors. All rights reserved.\n\nimport os"
  }
  ```

## Strict Sequential Structure Summary
Think completely inside the tags; execute flawlessly outside the tags.