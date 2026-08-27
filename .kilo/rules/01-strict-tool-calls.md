---
name: strict-tool-calls
globs: "**/*"
alwaysApply: true
---
# Strict Tool Calls: Single Find and Replace

You have access to the `single_find_and_replace` tool. When using it, you must provide exactly four keys: `filepath`, `old_string`, `new_string`, and `replace_all`. 

### CRITICAL PATH RULES
* The `filepath` **MUST** be a relative path from the workspace root (e.g., `"src/main.py"`).
* **NEVER** use absolute system paths (e.g., `"/home/user/..."`).

### CRITICAL DATA TYPE RULES
* The `replace_all` key **MUST** be a raw JSON boolean literal (`true` or `false`).
* **NEVER** wrap it in quotation marks (e.g., do NOT use `"true"` or `"false"`). It must be a primitive data type.

### Example Formatting
```json
{
  "filepath": "utils/orders.py",
  "old_string": "def calculate_total(price, quantity):\n    return price * quantity",
  "new_string": "def calculate_total(price, quantity):\n    subtotal = price * quantity\n    tax = subtotal * 0.10\n    return subtotal + tax",
  "replace_all": false
}
```
