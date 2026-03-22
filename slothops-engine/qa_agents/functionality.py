import json
import logging
import os
import subprocess
from google import genai
from google.genai import types

logger = logging.getLogger("slothops.qa.functionality")

FUNCTIONALITY_TEST_PROMPT = """
You are an expert QA Engineer. 
I will provide you with a set of changed files from a Pull Request.
The repository uses: {language} with {framework} framework.
Your job is to write a single generic unit test file that tests the core functionality of the new changes.

If {language} is "typescript" or "javascript", write a Jest/Mocha test file.
If {language} is "python", write a pytest file.
If {language} is "go", write a Go test file with `_test.go` suffix.
If {language} is "java", write a JUnit test file.
If {language} is "rust", write a Rust test module.
Otherwise, write the most appropriate test for the language.

Output ONLY valid JSON in the following format, with no markdown formatting around it:
{{
    "tests": [
        {{
            "path": "test_qa_functionality.py",
            "content": "import pytest\\n\\ndef test_something():\\n    pass"
        }}
    ]
}}

CHANGED FILES:
{changed_files}
"""

async def run_functionality_tests(
    repo_dir: str, 
    changed_files: list[dict], 
    gemini_api_key: str,
    stack_config: dict = None
) -> dict:
    """
    1. Ask Gemini to generate test cases for the changed files (using detected stack)
    2. Write them to repo_dir
    3. Run the tests
    """
    if not stack_config:
        stack_config = {"language": "unknown", "framework": "unknown", "test_command": None}
    
    if not changed_files:
        return {"status": "passed", "summary": "No changed files to test."}
        
    language = stack_config.get("language", "unknown")
    framework = stack_config.get("framework", "unknown")
    test_command = stack_config.get("test_command")
    
    logger.info("Functionality QA: Generating tests for %s/%s stack...", language, framework)
    client = genai.Client(api_key=gemini_api_key)
    
    files_str = ""
    for cf in changed_files:
        files_str += f"\n--- {cf.get('path')} ---\n{cf.get('content')}\n"
        
    prompt = FUNCTIONALITY_TEST_PROMPT.format(
        changed_files=files_str, 
        language=language, 
        framework=framework
    )
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
        )
        resp_text = response.text.strip()
        if resp_text.startswith("```json"):
            resp_text = resp_text[7:-3].strip()
        elif resp_text.startswith("```"):
            resp_text = resp_text[3:-3].strip()
            
        data = json.loads(resp_text)
        tests = data.get("tests", [])
    except Exception as e:
        logger.error("Failed to generate functionality tests: %s", e)
        return {"status": "warning", "summary": f"Failed to generate tests via LLM: {e}"}
        
    if not tests:
        return {"status": "passed", "summary": "LLM decided no functionality tests were needed."}
        
    # Write the tests
    test_paths = []
    for t in tests:
        t_path = os.path.join(repo_dir, t["path"])
        os.makedirs(os.path.dirname(t_path), exist_ok=True)
        with open(t_path, "w") as f:
            f.write(t["content"])
        test_paths.append(t["path"])
        
    # Run tests using stack-detected test runner
    logger.info("Functionality QA: Running tests %s", test_paths)
    
    # Determine command based on stack config or file extension fallback
    first_test = test_paths[0]
    cmd = None
    
    if language in ("typescript", "javascript"):
        cmd = ["npx", "--yes", "jest", "--passWithNoTests", "--forceExit"] + test_paths
    elif language == "python":
        cmd = ["python", "-m", "pytest"] + test_paths
    elif language == "go":
        cmd = ["go", "test", "./..."]
    elif language == "java":
        # Run via maven or gradle depending on framework
        if framework == "maven":
            cmd = ["mvn", "test"]
        elif framework == "gradle":
            cmd = ["./gradlew", "test"]
    elif language == "rust":
        cmd = ["cargo", "test"]
    else:
        # File extension fallback
        if first_test.endswith((".ts", ".js")):
            cmd = ["npx", "--yes", "jest", "--passWithNoTests"] + test_paths
        elif first_test.endswith(".py"):
            cmd = ["python", "-m", "pytest"] + test_paths
    
    if not cmd:
        return {"status": "warning", "summary": f"No test runner configured for {language} stack."}
        
    try:
        res = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True, timeout=90)
        if res.returncode == 0:
            return {
                "status": "passed",
                "summary": f"Generated {len(test_paths)} test files. All passed successfully."
            }
        else:
            return {
                "status": "failed",
                "summary": f"Generated test failed.\n\nOutput:\n{res.stdout[:500]}",
                "failures": res.stdout[:1000]
            }
    except subprocess.TimeoutExpired:
        logger.warning("Test framework timed out.")
        return {"status": "warning", "summary": "Test framework timed out (>90s)."}
    except Exception as e:
        logger.error("Functionality test execution failed: %s", e)
        return {"status": "warning", "summary": f"Failed to execute test runner: {e}"}
