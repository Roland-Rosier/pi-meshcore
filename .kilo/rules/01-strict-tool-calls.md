---
name: strict-tool-calls
globs: "**/*"
alwaysApply: true
---
# Strict Code Editing Rules

### CRITICAL PATH RULES
* Every file path **MUST** be a relative path from the workspace root (e.g., `"src/main.py"`).
* **NEVER** use absolute system paths (e.g., `"/home/user/..."`).

### CRITICAL DATA TYPE RULES
* Any boolean configurations, options, or flags **MUST** be a raw boolean literal (`true` or `false`).
* **NEVER** wrap it in quotation marks (e.g., do NOT use `"true"` or `"false"`). They must be a primitive data types.

### Example Formatting
```json
{
  "filepath": "utils/orders.py",
  "old_string": "def calculate_total(price, quantity):\n    return price * quantity",
  "new_string": "def calculate_total(price, quantity):\n    subtotal = price * quantity\n    tax = subtotal * 0.10\n    return subtotal + tax",
  "replace_all": false
}
```
