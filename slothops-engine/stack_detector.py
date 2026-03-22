"""
SlothOps Tech Stack Detector

Auto-detects the language, framework, and relevant commands for a repository.
Supports an optional `.slothops.yml` override at the repo root.

Priority order:
  1. `.slothops.yml` (user-defined, highest priority)
  2. Heuristic detection from repo marker files (package.json, requirements.txt, go.mod, etc.)
"""

import json
import logging
import os

logger = logging.getLogger("slothops.stack_detector")

# ── Default configs per detected stack ────────────────────────────────

STACK_CONFIGS = {
    "node": {
        "language": "javascript",
        "framework": "node",
        "start_command": "npm start",
        "test_command": "npm test",
        "lint_commands": ["npx --yes eslint . --max-warnings=0"],
        "type_check_command": None,  # set if TS detected
        "audit_command": "npm audit --json",
        "install_command": "npm install --include=dev",
        "port": 3000,
    },
    "node-ts": {
        "language": "typescript",
        "framework": "node",
        "start_command": "npm start",
        "test_command": "npm test",
        "lint_commands": ["npx --yes eslint . --max-warnings=0"],
        "type_check_command": "npx --yes tsc --noEmit",
        "audit_command": "npm audit --json",
        "install_command": "npm install --include=dev",
        "port": 3000,
    },
    "python": {
        "language": "python",
        "framework": "python",
        "start_command": None,  # will try to detect from Procfile, manage.py, etc.
        "test_command": "python -m pytest",
        "lint_commands": ["python -m flake8 ."],
        "type_check_command": None,
        "audit_command": "pip-audit --format=json",
        "install_command": "pip install -r requirements.txt",
        "port": 8000,
    },
    "python-django": {
        "language": "python",
        "framework": "django",
        "start_command": "python manage.py runserver 0.0.0.0:{port}",
        "test_command": "python manage.py test",
        "lint_commands": ["python -m flake8 ."],
        "type_check_command": None,
        "audit_command": "pip-audit --format=json",
        "install_command": "pip install -r requirements.txt",
        "port": 8000,
    },
    "python-flask": {
        "language": "python",
        "framework": "flask",
        "start_command": "python app.py",
        "test_command": "python -m pytest",
        "lint_commands": ["python -m flake8 ."],
        "type_check_command": None,
        "audit_command": "pip-audit --format=json",
        "install_command": "pip install -r requirements.txt",
        "port": 5000,
    },
    "go": {
        "language": "go",
        "framework": "go",
        "start_command": "go run .",
        "test_command": "go test ./...",
        "lint_commands": ["golangci-lint run"],
        "type_check_command": "go vet ./...",
        "audit_command": "govulncheck ./...",
        "install_command": "go mod download",
        "port": 8080,
    },
    "java-maven": {
        "language": "java",
        "framework": "maven",
        "start_command": "mvn spring-boot:run",
        "test_command": "mvn test",
        "lint_commands": ["mvn checkstyle:check"],
        "type_check_command": "mvn compile",
        "audit_command": None,
        "install_command": "mvn install -DskipTests",
        "port": 8080,
    },
    "java-gradle": {
        "language": "java",
        "framework": "gradle",
        "start_command": "./gradlew bootRun",
        "test_command": "./gradlew test",
        "lint_commands": ["./gradlew checkstyleMain"],
        "type_check_command": "./gradlew compileJava",
        "audit_command": None,
        "install_command": "./gradlew build -x test",
        "port": 8080,
    },
    "rust": {
        "language": "rust",
        "framework": "rust",
        "start_command": "cargo run",
        "test_command": "cargo test",
        "lint_commands": ["cargo clippy -- -D warnings"],
        "type_check_command": "cargo check",
        "audit_command": "cargo audit",
        "install_command": "cargo build",
        "port": 8080,
    },
    "unknown": {
        "language": "unknown",
        "framework": "unknown",
        "start_command": None,
        "test_command": None,
        "lint_commands": [],
        "type_check_command": None,
        "audit_command": None,
        "install_command": None,
        "port": None,
    },
}


def _try_load_slothops_yml(repo_dir: str) -> dict | None:
    """Try to load `.slothops.yml` from the repo root."""
    yml_path = os.path.join(repo_dir, ".slothops.yml")
    yaml_path = os.path.join(repo_dir, ".slothops.yaml")
    
    target = None
    if os.path.exists(yml_path):
        target = yml_path
    elif os.path.exists(yaml_path):
        target = yaml_path
    
    if not target:
        return None
    
    try:
        import yaml  # optional dependency
        with open(target, "r") as f:
            data = yaml.safe_load(f)
        logger.info("📄 Loaded .slothops.yml config from repo")
        return data if isinstance(data, dict) else None
    except ImportError:
        # Fallback: try simple key-value parsing if PyYAML isn't installed
        logger.warning("PyYAML not installed — attempting basic .slothops.yml parse")
        try:
            config = {}
            with open(target, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if ":" in line:
                        key, val = line.split(":", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if val.lower() == "true":
                            val = True
                        elif val.lower() == "false":
                            val = False
                        elif val.isdigit():
                            val = int(val)
                        config[key] = val
            return config if config else None
        except Exception:
            return None
    except Exception as e:
        logger.warning("Failed to load .slothops.yml: %s", e)
        return None


def _detect_node_variant(repo_dir: str) -> str:
    """Determine if Node project uses TypeScript."""
    ts_config = os.path.join(repo_dir, "tsconfig.json")
    if os.path.exists(ts_config):
        return "node-ts"
    
    pkg_path = os.path.join(repo_dir, "package.json")
    if os.path.exists(pkg_path):
        try:
            with open(pkg_path, "r") as f:
                pkg = json.load(f)
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "typescript" in deps:
                return "node-ts"
        except Exception:
            pass
    return "node"


def _detect_python_variant(repo_dir: str) -> str:
    """Determine Python framework (Django, Flask, or generic)."""
    if os.path.exists(os.path.join(repo_dir, "manage.py")):
        return "python-django"
    
    req_path = os.path.join(repo_dir, "requirements.txt")
    if os.path.exists(req_path):
        try:
            with open(req_path, "r") as f:
                content = f.read().lower()
            if "flask" in content:
                return "python-flask"
            if "django" in content:
                return "python-django"
        except Exception:
            pass
    
    # Check for common Flask patterns
    for name in ["app.py", "wsgi.py"]:
        path = os.path.join(repo_dir, name)
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    src = f.read(2048)
                if "flask" in src.lower() or "Flask(" in src:
                    return "python-flask"
            except Exception:
                pass
    
    return "python"


def _extract_start_command_from_pkg(repo_dir: str) -> str | None:
    """Try to read the 'start' script from package.json."""
    pkg_path = os.path.join(repo_dir, "package.json")
    if not os.path.exists(pkg_path):
        return None
    try:
        with open(pkg_path, "r") as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        if "start" in scripts:
            return "npm start"
        if "dev" in scripts:
            return "npm run dev"
        # Look for a main entry point
        main = pkg.get("main")
        if main:
            return f"node {main}"
    except Exception:
        pass
    return None


def detect_stack(repo_dir: str) -> dict:
    """
    Detect the tech stack for a given repository directory.
    
    Returns a config dict with keys:
        language, framework, start_command, test_command,
        lint_commands, type_check_command, audit_command,
        install_command, port
    
    Priority:
        1. `.slothops.yml` overrides (merged on top of auto-detected)
        2. Auto-detection from marker files
    """
    # Step 1: Auto-detect base stack
    detected_key = "unknown"
    
    if os.path.exists(os.path.join(repo_dir, "package.json")):
        detected_key = _detect_node_variant(repo_dir)
    elif os.path.exists(os.path.join(repo_dir, "requirements.txt")) or \
         os.path.exists(os.path.join(repo_dir, "setup.py")) or \
         os.path.exists(os.path.join(repo_dir, "pyproject.toml")):
        detected_key = _detect_python_variant(repo_dir)
    elif os.path.exists(os.path.join(repo_dir, "go.mod")):
        detected_key = "go"
    elif os.path.exists(os.path.join(repo_dir, "pom.xml")):
        detected_key = "java-maven"
    elif os.path.exists(os.path.join(repo_dir, "build.gradle")) or \
         os.path.exists(os.path.join(repo_dir, "build.gradle.kts")):
        detected_key = "java-gradle"
    elif os.path.exists(os.path.join(repo_dir, "Cargo.toml")):
        detected_key = "rust"
    
    config = dict(STACK_CONFIGS[detected_key])  # copy
    
    # Enrich Node start command from package.json
    if detected_key.startswith("node"):
        start_cmd = _extract_start_command_from_pkg(repo_dir)
        if start_cmd:
            config["start_command"] = start_cmd
    
    # Enrich port from package.json scripts or Procfile
    # (keep default for now, .slothops.yml can override)
    
    logger.info("🔍 Auto-detected stack: %s (lang=%s, framework=%s)", 
                detected_key, config["language"], config["framework"])
    
    # Step 2: Merge .slothops.yml overrides
    yml_config = _try_load_slothops_yml(repo_dir)
    if yml_config:
        # Map common YAML keys to our config keys
        key_map = {
            "stack": None,  # informational only
            "language": "language",
            "framework": "framework",
            "start": "start_command",
            "start_command": "start_command",
            "test": "test_command",
            "test_command": "test_command",
            "lint": "lint_commands",
            "lint_commands": "lint_commands",
            "type_check": "type_check_command",
            "audit": "audit_command",
            "install": "install_command",
            "port": "port",
        }
        
        for yml_key, cfg_key in key_map.items():
            if yml_key in yml_config and cfg_key:
                val = yml_config[yml_key]
                # Normalize lint to always be a list
                if cfg_key == "lint_commands" and isinstance(val, str):
                    val = [val]
                config[cfg_key] = val
                logger.info("📄 .slothops.yml override: %s = %s", cfg_key, val)
    
    return config
