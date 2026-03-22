import os
import json
import logging
import subprocess

logger = logging.getLogger("slothops.qa.static_analysis")

async def run_static_analysis(repo_dir: str, changed_files: list[str], stack_config: dict = None) -> dict:
    """
    Run static analysis on the cloned repo using the detected stack config.
    Falls back to basic heuristic if no config is provided.
    """
    if not stack_config:
        stack_config = {"language": "unknown", "lint_commands": [], "type_check_command": None}
    
    language = stack_config.get("language", "unknown")
    lint_commands = stack_config.get("lint_commands", [])
    type_check_cmd = stack_config.get("type_check_command")
    
    logger.info("Static analysis for stack: language=%s", language)
    
    status = "passed"
    issues = []
    summary_lines = []
    
    # 1. Run type checker if available
    if type_check_cmd:
        try:
            logger.debug("Running type checker: %s", type_check_cmd)
            res = subprocess.run(
                type_check_cmd.split(),
                cwd=repo_dir, capture_output=True, text=True, timeout=60
            )
            if res.returncode != 0:
                status = "warning"
                summary_lines.append(f"Type checker reported errors.")
                out_text = res.stdout.strip() or res.stderr.strip()
                issues.append({"tool": type_check_cmd.split()[0], "output": out_text[:2000] + ("..." if len(out_text) > 2000 else "")})
            else:
                summary_lines.append("Type checking passed.")
        except subprocess.TimeoutExpired:
            logger.warning("Type checker timed out.")
            status = "warning"
            summary_lines.append("Type checking timed out (>60s).")
        except Exception as e:
            logger.error("Failed to run type checker: %s", e)
    
    # 2. Run linters
    for lint_cmd in lint_commands:
        try:
            logger.debug("Running linter: %s", lint_cmd)
            res = subprocess.run(
                lint_cmd.split(),
                cwd=repo_dir, capture_output=True, text=True, timeout=60
            )
            if res.returncode != 0:
                status = "warning"
                tool_name = lint_cmd.split()[0]
                summary_lines.append(f"{tool_name} reported warnings or errors.")
                out_text = res.stdout.strip() or res.stderr.strip()
                issues.append({"tool": tool_name, "output": out_text[:2000] + ("..." if len(out_text) > 2000 else "")})
            else:
                tool_name = lint_cmd.split()[0]
                summary_lines.append(f"{tool_name} passed.")
        except subprocess.TimeoutExpired:
            logger.warning("Linter timed out: %s", lint_cmd)
            status = "warning"
            summary_lines.append(f"Linter timed out (>60s).")
        except Exception as e:
            logger.error("Failed to run linter: %s", e)
            
    if not summary_lines:
        summary_lines.append(f"No static analysis tools configured for detected stack ({language}).")
        
    return {
        "status": status,
        "issues": issues,
        "summary": " ".join(summary_lines)
    }
