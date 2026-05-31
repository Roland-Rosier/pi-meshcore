# Security Policy & Posture Notice

This project is open-source software provided on an "as-is" basis under the Apache 2.0 License. 

## 1. Scope of Maintainer Support
* **Development Focus:** This is a personal project. It does not undergo commercial penetration testing, fuzzing, or automated application security testing (SAST/DAST).
* **No Security SLA:** The maintainer does not actively monitor this repository for newly discovered common vulnerabilities and exposures (CVEs) within upstream Python packages.
* **No Active Patching:** There is no guaranteed timeline or obligation to patch, remediate, or issue security alerts for identified software flaws.

## 2. User Security Responsibilities
By cloning, importing, or deploying this codebase, you explicitly assume all downstream cybersecurity responsibilities. You are solely responsible for:
* **Vulnerability Scanning:** Running Software Composition Analysis (SCA) and code scanning tools (such as Bandit, Snyk, or CodeQL) before deployment.
* **Dependency Auditing:** Inspecting and updating the `requirements.txt` or `pyproject.toml` packages to resolve vulnerabilities in upstream dependencies.
* **Incident Response:** Managing, isolating, and mitigating any data breaches, network intrusions, or system errors resulting from the use of this software.

## 3. Reporting a Vulnerability
If you discover a critical exploit or security risk within the codebase, we welcome responsible disclosure so we can evaluate it:
* Please use the **"Report a Vulnerability"** button under the **Security** tab.
* Do not publish the exploit details in a public Issue or Pull Request until a fix has been discussed.