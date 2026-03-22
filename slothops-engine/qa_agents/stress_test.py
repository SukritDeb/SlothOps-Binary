import os
import time
import socket
import logging
import subprocess

logger = logging.getLogger("slothops.qa.stress")

def _wait_for_port(port: int, host: str = "127.0.0.1", timeout: int = 15) -> bool:
    """Wait until a local port is listening."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(1)
    return False

async def run_stress_test(repo_dir: str, stack_config: dict = None) -> dict:
    """
    Spin up the application locally using the detected start_command and run autocannon.
    """
    if not stack_config:
        stack_config = {"start_command": None, "port": None, "language": "unknown"}
    
    logger.info("Starting Stress Testing...")
    
    status = "passed"
    summary_lines = []
    
    start_command = stack_config.get("start_command")
    port = stack_config.get("port")
    language = stack_config.get("language", "unknown")
    
    if not start_command:
        return {
            "status": "passed",
            "summary": f"Skipping stress test: no start_command configured for {language} stack."
        }
    
    if not port:
        port = 3000  # default fallback
        
    # Spin up the app server
    logger.debug("Spinning up local server via '%s' on port %d...", start_command, port)
    process = None
    try:
        # Set PORT env var for the child process
        env = os.environ.copy()
        env["PORT"] = str(port)
        
        process = subprocess.Popen(
            start_command.split(), 
            cwd=repo_dir, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            env=env
        )
        
        # Wait for the port to become reachable
        ports_to_try = [port, 3000, 8000, 8080, 5000]
        # Deduplicate while preserving order
        seen = set()
        unique_ports = []
        for p in ports_to_try:
            if p not in seen:
                seen.add(p)
                unique_ports.append(p)
        
        found_port = None
        for p in unique_ports:
            if _wait_for_port(p, timeout=5):
                found_port = p
                break
                
        if not found_port:
            logger.warning("Could not detect any listening port for stress testing.")
            summary_lines.append("Application did not expose a known port for stress testing.")
            return {"status": "warning", "summary": summary_lines[0]}
            
        logger.info("Application detected listening on port %d. Running autocannon...", found_port)
        
        # Run autocannon - 10 concurrent connections for 5 seconds
        url = f"http://127.0.0.1:{found_port}"
        try:
            res = subprocess.run(
                ["npx", "--yes", "autocannon", "-c", "10", "-d", "5", "--json", url],
                cwd=repo_dir, capture_output=True, text=True, timeout=30
            )
            if res.returncode != 0:
                logger.error("autocannon failed: %s", res.stderr)
                status = "warning"
                summary_lines.append("Load generator (autocannon) failed to execute properly.")
            else:
                import json
                try:
                    stats = json.loads(res.stdout)
                    latency_avg = stats.get('latency', {}).get('average', 0)
                    requests_sec = stats.get('requests', {}).get('average', 0)
                    errors = stats.get('errors', 0)
                    timeouts = stats.get('timeouts', 0)
                    
                    if errors > 0 or timeouts > 0:
                        status = "failed"
                        summary_lines.append(f"Stress test FAILED: {errors} errors, {timeouts} timeouts.")
                    elif latency_avg > 1000:
                        status = "warning"
                        summary_lines.append(f"Stress test WARN: High average latency ({latency_avg}ms).")
                    else:
                        summary_lines.append(f"Stress test PASSED: {requests_sec} req/sec, avg latency {latency_avg}ms.")
                except Exception:
                    summary_lines.append("Failed to parse autocannon JSON output.")
                    
        except subprocess.TimeoutExpired:
            logger.warning("autocannon timed out.")
            status = "warning"
            summary_lines.append("autocannon timed out (>30s).")
        except Exception as e:
            logger.error("Failed to run npx autocannon: %s", e)
            summary_lines.append(f"Error running autocannon: {e}")
            
    except Exception as e:
        logger.error("Failed to start server for stress testing: %s", e)
        summary_lines.append(f"Failed to boot local application: {e}")
    finally:
        # Crucial: cleanup the spawned server
        if process:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                
    return {
        "status": status,
        "summary": " ".join(summary_lines)
    }
