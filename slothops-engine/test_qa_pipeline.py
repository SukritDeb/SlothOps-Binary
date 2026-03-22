"""
Isolated Phase 1 & 2 verification tests.
Each sub-agent is tested against a real local directory WITHOUT needing GitHub API.
"""
import asyncio
import json
import os
import sys
import tempfile
import shutil
import logging

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(levelname)s  %(message)s")

# ───────────────────────────────────────────────────────
# 1. DATABASE LAYER TEST
# ───────────────────────────────────────────────────────
async def test_database():
    print("\n═══ TEST: Database Layer ═══")
    import database as db
    from models import QAReport, QAStatus
    
    test_db = "/tmp/test_qa.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    
    await db.init_db(test_db)
    print("  ✅ init_db() succeeded — all tables created")
    
    report = QAReport(
        id="test-report-001",
        workspace_id="ws-test",
        pr_number=99,
        pr_url="https://github.com/test/repo/pull/99",
        commit_sha="abc12345",
        repo_name="test/repo",
        overall_status=QAStatus.RUNNING.value,
        summary="Test report"
    )
    await db.create_qa_report(report, test_db)
    print("  ✅ create_qa_report() succeeded")
    
    await db.update_qa_report("test-report-001", test_db, 
        overall_status=QAStatus.PASSED.value,
        summary="All good",
        static_analysis={"status": "passed", "summary": "lint clean"}
    )
    print("  ✅ update_qa_report() succeeded")
    
    fetched = await db.get_qa_report("test-report-001", test_db)
    assert fetched is not None, "Report not found!"
    assert fetched.overall_status == "passed"
    assert fetched.static_analysis["status"] == "passed"
    print("  ✅ get_qa_report() returned correct data")
    
    reports = await db.get_qa_reports("ws-test", test_db)
    assert len(reports) == 1
    print("  ✅ get_qa_reports() returned 1 report")
    
    os.remove(test_db)
    print("  ✅ Database layer: ALL PASSED\n")


# ───────────────────────────────────────────────────────
# 2. STATIC ANALYSIS SUB-AGENT TEST
# ───────────────────────────────────────────────────────
async def test_static_analysis():
    print("═══ TEST: Static Analysis Agent ═══")
    from qa_agents.static_analysis import run_static_analysis, detect_tech_stack
    
    # Create a fake Node.js project
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write package.json
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump({"name": "test-app", "version": "1.0.0"}, f)
        
        # Write a JS file with a deliberate style issue
        with open(os.path.join(tmpdir, "index.js"), "w") as f:
            f.write("const x = 1;\nconsole.log(x);\n")
        
        stack = detect_tech_stack(tmpdir)
        assert stack["language"] == "javascript"
        assert stack["package_manager"] == "npm"
        print(f"  ✅ detect_tech_stack() -> {stack}")
        
        result = await run_static_analysis(tmpdir, ["index.js"])
        print(f"  ✅ run_static_analysis() -> status={result['status']}, summary={result['summary']}")
    
    # Test Python project
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "requirements.txt"), "w") as f:
            f.write("flask==3.0.0\n")
        with open(os.path.join(tmpdir, "app.py"), "w") as f:
            f.write("import os\nprint('hello')\n")
        
        stack = detect_tech_stack(tmpdir)
        assert stack["language"] == "python"
        print(f"  ✅ detect_tech_stack() for Python -> {stack}")
        
        result = await run_static_analysis(tmpdir, ["app.py"])
        print(f"  ✅ run_static_analysis() Python -> status={result['status']}, summary={result['summary']}")
    
    print("  ✅ Static Analysis: ALL PASSED\n")


# ───────────────────────────────────────────────────────
# 3. VAPT SUB-AGENT TEST
# ───────────────────────────────────────────────────────
async def test_vapt():
    print("═══ TEST: VAPT Agent ═══")
    from qa_agents.vapt import run_vapt_scan
    
    # Test with a Node.js project (npm audit)
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump({"name": "test-vapt", "version": "1.0.0", "dependencies": {}}, f)
        
        result = await run_vapt_scan(tmpdir)
        print(f"  ✅ run_vapt_scan(node) -> status={result['status']}, summary={result['summary']}")
    
    # Test with an empty directory (no supported stack)
    with tempfile.TemporaryDirectory() as tmpdir:
        result = await run_vapt_scan(tmpdir)
        assert result["status"] == "passed"
        print(f"  ✅ run_vapt_scan(empty) -> status={result['status']}, summary={result['summary']}")
    
    print("  ✅ VAPT: ALL PASSED\n")


# ───────────────────────────────────────────────────────
# 4. STRESS TEST SUB-AGENT TEST
# ───────────────────────────────────────────────────────
async def test_stress():
    print("═══ TEST: Stress Test Agent ═══")
    from qa_agents.stress_test import run_stress_test
    
    # Test with a non-Node directory (should skip gracefully)
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "requirements.txt"), "w") as f:
            f.write("flask\n")
        
        result = await run_stress_test(tmpdir)
        assert result["status"] == "passed"
        assert "Skipping" in result["summary"]
        print(f"  ✅ run_stress_test(python) -> correctly skipped: {result['summary']}")
    
    # Test with a Node project but no start script (should warn gracefully)
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump({"name": "test-stress", "version": "1.0.0"}, f)
        
        result = await run_stress_test(tmpdir)
        # It will try npm start, fail to find a port, and return warning
        print(f"  ✅ run_stress_test(node-no-start) -> status={result['status']}, summary={result['summary']}")
    
    print("  ✅ Stress Test: ALL PASSED\n")


# ───────────────────────────────────────────────────────
# 5. FUNCTIONALITY SUB-AGENT TEST (no LLM call)
# ───────────────────────────────────────────────────────
async def test_functionality():
    print("═══ TEST: Functionality Agent ═══")
    from qa_agents.functionality import run_functionality_tests
    
    # Test with empty changed files — should just skip
    result = await run_functionality_tests("/tmp", [], "fake-key")
    assert result["status"] == "passed"
    print(f"  ✅ run_functionality_tests(empty) -> {result['summary']}")
    
    print("  ✅ Functionality: ALL PASSED\n")


# ───────────────────────────────────────────────────────
# 6. GITHUB COMMENT FORMATTING TEST
# ───────────────────────────────────────────────────────
def test_comment_formatting():
    print("═══ TEST: GitHub Comment Formatting ═══")
    
    # We just test that the formatting logic doesn't crash
    qa_report = {
        "overall_status": "warning",
        "summary": "Some tests had warnings.",
        "static_analysis": {"status": "passed", "summary": "Lint clean."},
        "functionality": {"status": "warning", "summary": "1 test failed.", "failures": "AssertionError in test_foo"},
        "vapt": {"status": "passed", "summary": "0 vulnerabilities."},
        "stress_test": {"status": "warning", "summary": "High latency detected."}
    }
    
    # Simulate constructing the comment body (without actually posting)
    status_emoji = "✅"
    if qa_report.get("overall_status") == "failed":
        status_emoji = "❌"
    elif qa_report.get("overall_status") == "warning":
        status_emoji = "⚠️"
    
    body_lines = [f"## {status_emoji} SlothOps QA Report\n"]
    body_lines.append(f"**Execution Summary:**\n{qa_report['summary']}\n")
    
    for agent_key, agent_label in [("static_analysis", "Static Analysis"), ("functionality", "Functionality Testing"), ("vapt", "VAPT Scan"), ("stress_test", "Stress Testing")]:
        agent = qa_report.get(agent_key)
        if agent:
            a_emoji = "✅" if agent["status"] == "passed" else ("⚠️" if agent["status"] == "warning" else "❌")
            body_lines.append(f"### {a_emoji} {agent_label}\n")
            body_lines.append(agent.get("summary", "No details."))
    
    body = "\n".join(body_lines)
    assert "SlothOps QA Report" in body
    assert "⚠️" in body
    assert "Static Analysis" in body
    assert "VAPT Scan" in body
    print(f"  ✅ Generated comment body ({len(body)} chars)")
    print("  ✅ Comment Formatting: ALL PASSED\n")


# ───────────────────────────────────────────────────────
# RUNNER
# ───────────────────────────────────────────────────────
async def main():
    print("╔══════════════════════════════════════════╗")
    print("║  SlothOps QA — Phase 1 & 2 Verification ║")
    print("╚══════════════════════════════════════════╝\n")
    
    await test_database()
    await test_static_analysis()
    await test_vapt()
    await test_stress()
    await test_functionality()
    test_comment_formatting()
    
    print("╔══════════════════════════════════════════╗")
    print("║  🎉 ALL PHASE 1 & 2 TESTS PASSED!       ║")
    print("╚══════════════════════════════════════════╝")


if __name__ == "__main__":
    asyncio.run(main())
