"""
SlothOps Engine — Test Runner
Clones the target repository to a temporary directory, applies the LLM-generated fixes
and tests, installs dependencies, and runs ONLY the generated test files.
"""

import os
import subprocess
import tempfile
import logging
from models import LLMFixResponse

logger = logging.getLogger("slothops.test_runner")

_DIVIDER = "═" * 50


def validate_fix(fix: LLMFixResponse, repo, token: str) -> tuple[bool, str]:
    """
    Creates a temporary directory, clones the authenticated repo, applies the fix 
    and generated tests, runs ONLY the generated tests, and returns (success, output_string).
    """
    # 1. Prepare clone URL with installation token
    clone_url = repo.clone_url.replace("https://", f"https://x-access-token:{token}@")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        logger.info("%s", f"\n{_DIVIDER}\n🧪 SANDBOX: Cloning {repo.full_name}...\n{_DIVIDER}")
        
        # 2. Shallow clone the repo for speed
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", clone_url, tmpdir],
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            logger.error("🧪 SANDBOX FAILED: Could not clone repo: %s", e.stderr)
            return False, f"Failed to clone repository: {e.stderr}"

        # 3. Apply code changes
        logger.info("%s", f"\n{_DIVIDER}\n🧪 SANDBOX: Applying {len(fix.files_changed)} fix(es) + {len(fix.generated_tests)} test(s)...\n{_DIVIDER}")
        all_changes = fix.files_changed + fix.generated_tests
        for change in all_changes:
            target_path = os.path.join(tmpdir, change.path)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "w") as f:
                f.write(change.fixed_content)

        # Collect generated test file paths for targeted execution
        test_file_paths = [t.path for t in fix.generated_tests]

        # 4. Detect framework and run ONLY the generated tests
        output = ""
        success = False
        
        try:
            if os.path.exists(os.path.join(tmpdir, "package.json")):
                logger.info("%s", f"\n{_DIVIDER}\n🧪 SANDBOX: npm install (Node.js project detected)...\n{_DIVIDER}")
                subprocess.run(
                    ["npm", "install"], cwd=tmpdir, capture_output=True, text=True, check=True
                )
                
                # Run ONLY the generated test files, not the whole suite
                test_args = ["npx", "jest", "--no-coverage", "--passWithNoTests"] + test_file_paths
                logger.info("%s", f"\n{_DIVIDER}\n🧪 SANDBOX: Running targeted tests → {', '.join(test_file_paths)}\n{_DIVIDER}")
                
                test_proc = subprocess.run(
                    test_args, cwd=tmpdir, capture_output=True, text=True
                )
                output = test_proc.stdout + "\n" + test_proc.stderr
                success = (test_proc.returncode == 0)
                
            elif os.path.exists(os.path.join(tmpdir, "requirements.txt")):
                logger.info("%s", f"\n{_DIVIDER}\n🧪 SANDBOX: Setting up Python venv...\n{_DIVIDER}")
                subprocess.run(
                    ["python", "-m", "venv", ".venv"], cwd=tmpdir, capture_output=True, check=True
                )
                pip_path = os.path.join(tmpdir, ".venv", "bin", "pip")
                pytest_path = os.path.join(tmpdir, ".venv", "bin", "pytest")
                
                subprocess.run(
                    [pip_path, "install", "-r", "requirements.txt"], cwd=tmpdir, capture_output=True, check=True
                )
                
                # Run ONLY the generated test files
                test_args = [pytest_path, "-v"] + test_file_paths
                logger.info("%s", f"\n{_DIVIDER}\n🧪 SANDBOX: Running targeted tests → {', '.join(test_file_paths)}\n{_DIVIDER}")
                
                test_proc = subprocess.run(
                    test_args, cwd=tmpdir, capture_output=True, text=True
                )
                output = test_proc.stdout + "\n" + test_proc.stderr
                success = (test_proc.returncode == 0)
            else:
                logger.warning("🧪 SANDBOX: No package.json or requirements.txt found")
                return False, "Could not detect test framework (missing package.json or requirements.txt)"
                
        except subprocess.CalledProcessError as e:
            output = f"Command failed during setup: {e.cmd}\n{e.stderr}"
            success = False
        
        # Final verdict banner
        if success:
            logger.info("%s", f"\n{_DIVIDER}\n✅ SANDBOX: All generated tests PASSED!\n{_DIVIDER}")
        else:
            logger.warning("%s", f"\n{_DIVIDER}\n❌ SANDBOX: Generated tests FAILED\n{_DIVIDER}")

        # Truncate output to prevent massive context explosion in the LLM prompt
        if len(output) > 4000:
            output = output[:4000] + "\n...[OUTPUT TRUNCATED]..."
            
        return success, output
