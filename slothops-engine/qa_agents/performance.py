import os
import time
import socket
import logging
import subprocess

logger = logging.getLogger("slothops.qa.performance")

def _wait_for_port(port: int, host: str = "127.0.0.1", timeout: int = 15) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(1)
    return False

async def run_performance_check(repo_dir: str, stack_config: dict = None) -> dict:
    """
    Spin up the app using detected start_command, hit endpoint, measure response time.
    """
    if not stack_config:
        stack_config = {"start_command": None, "port": None, "language": "unknown"}
    
    logger.info("Starting Performance Baseline Check...")
    
    status = "passed"
    summary_lines = []
    
    start_command = stack_config.get("start_command")
    port = stack_config.get("port")
    language = stack_config.get("language", "unknown")
    
    if not start_command:
        return {
            "status": "passed",
            "summary": f"Skipping performance baseline: no start_command for {language} stack."
        }
    
    if not port:
        port = 3000
        
    process = None
    try:
        env = os.environ.copy()
        env["PORT"] = str(port)
        
        process = subprocess.Popen(
            start_command.split(), 
            cwd=repo_dir, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            env=env
        )
        
        # Wait for port
        ports_to_try = [port, 3000, 8000, 8080, 5000]
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
            logger.warning("Could not detect any listening port for performance check.")
            return {"status": "warning", "summary": "App did not expose a known port for performance baseline."}
            
        logger.info("App listening on port %d. Gathering basic performance metrics...", found_port)
        
        # Simple curl baseline
        url = f"http://127.0.0.1:{found_port}"
        
        samples = []
        for _ in range(5):
            start = time.time()
            try:
                res = subprocess.run(
                    ["curl", "-s", "-o", "/dev/null", "-w", "%{time_total}", url], 
                    capture_output=True, text=True, timeout=5
                )
                if res.returncode == 0:
                    samples.append(float(res.stdout))
            except subprocess.TimeoutExpired:
                pass
            time.sleep(0.1)
                
        if samples:
            avg_time = sum(samples) / len(samples)
            if avg_time > 0.5:
                status = "warning"
                summary_lines.append(f"Root endpoint is slow: {avg_time*1000:.1f}ms (warning threshold 500ms).")
            else:
                summary_lines.append(f"Root endpoint baseline: {avg_time*1000:.1f}ms.")
        else:
            status = "warning"
            summary_lines.append("Failed to hit root endpoint for performance baseline.")
            
    except Exception as e:
        logger.error("Failed to start server for performance test: %s", e)
        summary_lines.append(f"Failed to boot app for baseline: {e}")
    finally:
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
