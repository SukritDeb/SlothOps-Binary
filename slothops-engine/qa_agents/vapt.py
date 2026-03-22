import os
import json
import logging
import subprocess

logger = logging.getLogger("slothops.qa.vapt")

async def run_vapt_scan(repo_dir: str, stack_config: dict = None) -> dict:
    """
    Run Vulnerability Assessment and Penetration Testing.
    Uses the stack config to determine which auditing tool to use.
    """
    if not stack_config:
        stack_config = {"audit_command": None, "language": "unknown"}
    
    logger.info("Starting VAPT scan...")
    status = "passed"
    summary_lines = []
    issues = []
    
    audit_cmd = stack_config.get("audit_command")
    language = stack_config.get("language", "unknown")
    
    if audit_cmd:
        try:
            logger.debug("Running audit: %s", audit_cmd)
            res = subprocess.run(
                audit_cmd.split(),
                cwd=repo_dir, capture_output=True, text=True, timeout=30
            )
            
            # Parse JSON output for npm audit specifically
            if "npm audit" in audit_cmd:
                try:
                    audit_data = json.loads(res.stdout)
                    vulns = audit_data.get("metadata", {}).get("vulnerabilities", {})
                    total_vulns = sum(vulns.values())
                    
                    if total_vulns > 0:
                        critical = vulns.get("critical", 0)
                        high = vulns.get("high", 0)
                        if critical > 0 or high > 0:
                            status = "failed"
                        else:
                            status = "warning"
                        summary_lines.append(f"npm audit found {total_vulns} vulnerabilities (Critical: {critical}, High: {high}).")
                        issues.append({"tool": "npm audit", "vulns": vulns})
                    else:
                        summary_lines.append("npm audit passed with 0 vulnerabilities.")
                except json.JSONDecodeError:
                    logger.warning("Failed to parse npm audit JSON output.")
                    summary_lines.append("npm audit output was not valid JSON.")
            elif "pip-audit" in audit_cmd:
                if res.returncode != 0:
                    status = "warning"
                    summary_lines.append("pip-audit found vulnerabilities.")
                    issues.append({"tool": "pip-audit", "output": res.stdout[:500]})
                else:
                    summary_lines.append("pip-audit passed.")
            elif "cargo audit" in audit_cmd:
                if res.returncode != 0:
                    status = "warning"
                    summary_lines.append("cargo audit found vulnerabilities.")
                    issues.append({"tool": "cargo audit", "output": res.stdout[:500]})
                else:
                    summary_lines.append("cargo audit passed.")
            elif "govulncheck" in audit_cmd:
                if res.returncode != 0:
                    status = "warning"
                    summary_lines.append("govulncheck found vulnerabilities.")
                    issues.append({"tool": "govulncheck", "output": res.stdout[:500]})
                else:
                    summary_lines.append("govulncheck passed.")
            else:
                # Generic: just check exit code
                if res.returncode != 0:
                    status = "warning"
                    summary_lines.append(f"Audit tool reported issues.")
                    issues.append({"tool": audit_cmd.split()[0], "output": res.stdout[:500]})
                else:
                    summary_lines.append(f"Audit passed.")
                    
        except subprocess.TimeoutExpired:
            logger.warning("Audit tool timed out.")
            status = "warning"
            summary_lines.append("Audit tool timed out (>30s).")
        except Exception as e:
            logger.error("Failed to run audit: %s", e)
            summary_lines.append(f"Audit tool execution failed: {e}")
    else:
        summary_lines.append(f"No audit tool configured for {language} stack.")
    
    if not summary_lines:
        summary_lines.append("No supported VAPT tools ran.")
        
    return {
        "status": status,
        "summary": " ".join(summary_lines),
        "issues": issues
    }
