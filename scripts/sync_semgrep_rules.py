#!/usr/bin/env python3
"""Sync curated semgrep rules from upstream to local offline pack.

Usage:
    uv run python scripts/sync_semgrep_rules.py

Copies relevant YAML rules from the upstream semgrep-semgrep-rules repository
into .semgrep/rules/ for offline scanning without internet connectivity.

Handles both flat YAML files and subdirectories of rules.
"""
import shutil
from pathlib import Path

SOURCE = Path(".semgrep/semgrep-semgrep-rules/python/lang")
TARGET = Path(".semgrep/rules")

# Maps category -> list of rule paths relative to SOURCE
# Directories end with / and individual files are named *.yaml
RULE_GROUPS: dict[str, list[str]] = {
    "security": [
        "security/audit/",
        "security/dangerous-code-run-audit.yaml",
        "security/dangerous-globals-use.yaml",
        "security/dangerous-os-exec.yaml",
        "security/dangerous-spawn-process.yaml",
        "security/dangerous-subprocess-use.yaml",
        "security/dangerous-system-call.yaml",
        "security/insecure-hash-algorithms.yaml",
        "security/insecure-hash-function.yaml",
        "security/unverified-ssl-context.yaml",
        "security/use-defused-xml-parse.yaml",
        "security/use-defused-xml.yaml",
        "security/use-defused-xmlrpc.yaml",
        "security/use-defusedcsv.yaml",
    ],
    "best-practice": [
        "best-practice/hardcoded-tmp-path.yaml",
        "best-practice/logging-error-without-handling.yaml",
        "best-practice/manual-collections-create.yaml",
        "best-practice/missing-hash-with-eq.yaml",
        "best-practice/open-never-closed.yaml",
        "best-practice/pass-body.yaml",
        "best-practice/pdb.yaml",
        "best-practice/sleep.yaml",
        "best-practice/unspecified-open-encoding.yaml",
    ],
    "correctness": [
        "correctness/check-is-none-explicitly.yaml",
        "correctness/socket-shutdown-close.yaml",
        "correctness/suppressed-exception-handling-finally-break.yaml",
        "correctness/common-mistakes/",
        "correctness/exceptions/",
        "correctness/tempfile/",
        "correctness/baseclass-attribute-override.yaml",
        "correctness/cannot-cache-generators.yaml",
        "correctness/concurrent.yaml",
        "correctness/dict-modify-iterating.yaml",
        "correctness/exit.yaml",
        "correctness/file-object-redefined-before-close.yaml",
        "correctness/list-modify-iterating.yaml",
        "correctness/pytest-assert_match-after-path-patch.yaml",
        "correctness/return-in-init.yaml",
        "correctness/sync-sleep-in-async-code.yaml",
        "correctness/unchecked-returns.yaml",
        "correctness/useless-comparison.yaml",
        "correctness/useless-eqeq.yaml",
        "correctness/writing-to-file-in-read-mode.yaml",
    ],
    "maintainability": [
        "maintainability/improper-list-concat.yaml",
        "maintainability/is-function-without-parentheses.yaml",
        "maintainability/return.yaml",
        "maintainability/useless-assign.yaml",
        "maintainability/useless-ifelse.yaml",
        "maintainability/useless-innerfunction.yaml",
        "maintainability/useless-literal.yaml",
        "maintainability/useless-literal-set.yaml",
    ],
}


def sync() -> None:
    """Copy curated rules from upstream to local offline pack."""
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True, exist_ok=True)

    for category, rules in RULE_GROUPS.items():
        cat_target = TARGET / category
        cat_target.mkdir(parents=True, exist_ok=True)
        for rule in rules:
            src = SOURCE / rule.rstrip("/")
            is_dir_rule = rule.endswith("/")
            base_name = Path(rule.rstrip("/")).name
            dst = cat_target / base_name

            if is_dir_rule and src.is_dir():
                shutil.copytree(src, dst)
            elif src.is_file():
                shutil.copy2(src, dst)
                py_src = src.with_suffix(".py")
                if py_src.exists():
                    shutil.copy2(py_src, dst.with_suffix(".py"))
            else:
                print(f"  SKIP: {src} does not exist in upstream")

    print(f"\nSynced rules to {TARGET}")


if __name__ == "__main__":
    sync()
