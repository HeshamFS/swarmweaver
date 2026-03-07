#!/usr/bin/env python3
"""
Security Hook Tests
===================

Tests for the bash command security validation logic.
Run with: python test_security.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path for imports when running as script
sys.path.insert(0, str(Path(__file__).parent.parent))

from hooks.security import (
    bash_security_hook,
    extract_commands,
    _strip_inline_comments,
    validate_chmod_command,
    validate_helper_script,
    validate_pkill_command,
    ALLOWED_HELPER_SCRIPTS,
)


def _run_hook_test(command: str, should_block: bool) -> bool:
    """Test a single command against the security hook."""
    input_data = {"tool_name": "Bash", "tool_input": {"command": command}}
    result = asyncio.run(bash_security_hook(input_data))
    was_blocked = result.get("decision") == "block"

    if was_blocked == should_block:
        status = "PASS"
    else:
        status = "FAIL"
        expected = "blocked" if should_block else "allowed"
        actual = "blocked" if was_blocked else "allowed"
        reason = result.get("reason", "")
        print(f"  {status}: {command!r}")
        print(f"         Expected: {expected}, Got: {actual}")
        if reason:
            print(f"         Reason: {reason}")
        return False

    print(f"  {status}: {command!r}")
    return True


def test_extract_commands():
    """Test the command extraction logic."""
    print("\nTesting command extraction:\n")
    passed = 0
    failed = 0

    test_cases = [
        ("ls -la", ["ls"]),
        ("npm install && npm run build", ["npm", "npm"]),
        ("cat file.txt | grep pattern", ["cat", "grep"]),
        ("/usr/bin/node script.js", ["node"]),
        ("VAR=value ls", ["ls"]),
        ("git status || git init", ["git", "git"]),
        ("git add x && git commit -m 'msg'", ["git", "git"]),
        # G2A: Inline comments should be stripped
        ("ls # comment", ["ls"]),
        ("mkdir -p dir # create directory", ["mkdir"]),
        # G2B: Subshell parentheses should be handled
        ("(mkdir -p dir && cd dir)", ["mkdir", "cd"]),
        ("(echo hello)", ["echo"]),
        # G2C: $() command substitution in variable assignments
        ('PROJECT_NAME=$(basename "$PWD")', ["basename"]),
        ('PROJECT_NAME=$(basename "$PWD") && mkdir -p x', ["basename", "mkdir"]),
        # Pipes with python -c
        ("cat file | python3 -c 'import sys'", ["cat", "python3"]),
    ]

    for cmd, expected in test_cases:
        result = extract_commands(cmd)
        if result == expected:
            print(f"  PASS: {cmd!r} -> {result}")
            passed += 1
        else:
            print(f"  FAIL: {cmd!r}")
            print(f"         Expected: {expected}, Got: {result}")
            failed += 1

    return passed, failed


def test_strip_inline_comments():
    """Test inline comment stripping respects quotes."""
    print("\nTesting inline comment stripping:\n")
    passed = 0
    failed = 0

    test_cases = [
        ("ls # comment", "ls"),
        ('echo "hello # world"', 'echo "hello # world"'),
        ("echo 'test' # comment", "echo 'test'"),
        ("# full line comment", ""),
        ("mkdir -p dir # create", "mkdir -p dir"),
        ('grep "pattern#1" file', 'grep "pattern#1" file'),
    ]

    for cmd, expected in test_cases:
        result = _strip_inline_comments(cmd)
        if result == expected:
            print(f"  PASS: {cmd!r} -> {result!r}")
            passed += 1
        else:
            print(f"  FAIL: {cmd!r}")
            print(f"         Expected: {expected!r}, Got: {result!r}")
            failed += 1

    return passed, failed


def test_validate_chmod():
    """Test chmod command validation."""
    print("\nTesting chmod validation:\n")
    passed = 0
    failed = 0

    # Test cases: (command, should_be_allowed, description)
    test_cases = [
        # Allowed cases
        ("chmod +x init.sh", True, "basic +x"),
        ("chmod +x script.sh", True, "+x on any script"),
        ("chmod u+x init.sh", True, "user +x"),
        ("chmod a+x init.sh", True, "all +x"),
        ("chmod ug+x init.sh", True, "user+group +x"),
        ("chmod +x file1.sh file2.sh", True, "multiple files"),
        # Blocked cases
        ("chmod 777 init.sh", False, "numeric mode"),
        ("chmod 755 init.sh", False, "numeric mode 755"),
        ("chmod +w init.sh", False, "write permission"),
        ("chmod +r init.sh", False, "read permission"),
        ("chmod -x init.sh", False, "remove execute"),
        ("chmod -R +x dir/", False, "recursive flag"),
        ("chmod --recursive +x dir/", False, "long recursive flag"),
        ("chmod +x", False, "missing file"),
    ]

    for cmd, should_allow, description in test_cases:
        allowed, reason = validate_chmod_command(cmd)
        if allowed == should_allow:
            print(f"  PASS: {cmd!r} ({description})")
            passed += 1
        else:
            expected = "allowed" if should_allow else "blocked"
            actual = "allowed" if allowed else "blocked"
            print(f"  FAIL: {cmd!r} ({description})")
            print(f"         Expected: {expected}, Got: {actual}")
            if reason:
                print(f"         Reason: {reason}")
            failed += 1

    return passed, failed


def test_validate_helper_scripts():
    """Test helper script execution validation."""
    print("\nTesting helper script validation:\n")
    passed = 0
    failed = 0

    # Test cases: (command, should_be_allowed, description)
    test_cases = [
        # Allowed helper scripts
        ("./init.sh", True, "basic ./init.sh"),
        ("./init.sh arg1 arg2", True, "init.sh with arguments"),
        ("/path/to/init.sh", True, "absolute path to init.sh"),
        ("../dir/init.sh", True, "relative path with init.sh"),
        ("./start-backend.sh", True, "start-backend.sh"),
        ("./start-frontend.sh", True, "start-frontend.sh"),
        ("./run_test.sh", True, "run_test.sh"),
        ("./setup-frontend.sh", True, "setup-frontend.sh"),
        # Blocked cases
        ("./malicious.sh", False, "malicious script"),
        ("./init.py", False, "python script"),
        ("bash init.sh", False, "bash invocation without path"),
        ("sh init.sh", False, "sh invocation without path"),
        ("init.sh", False, "no path prefix"),
        ("start-backend.sh", False, "no path prefix"),
    ]

    for cmd, should_allow, description in test_cases:
        allowed, reason = validate_helper_script(cmd)
        if allowed == should_allow:
            print(f"  PASS: {cmd!r} ({description})")
            passed += 1
        else:
            expected = "allowed" if should_allow else "blocked"
            actual = "allowed" if allowed else "blocked"
            print(f"  FAIL: {cmd!r} ({description})")
            print(f"         Expected: {expected}, Got: {actual}")
            if reason:
                print(f"         Reason: {reason}")
            failed += 1

    return passed, failed


def test_validate_pkill():
    """Test pkill command validation."""
    print("\nTesting pkill validation:\n")
    passed = 0
    failed = 0

    test_cases = [
        # Allowed: exact match
        ("pkill node", True, "exact node"),
        ("pkill vite", True, "exact vite"),
        ("pkill -f node", True, "pkill -f node"),
        ("pkill -f 'node server.js'", True, "pkill -f with space"),
        # Allowed: pattern starting with allowed process name
        ('pkill -f "vite.*3010"', True, "vite pattern with port"),
        ("pkill -f 'vite.*3010'", True, "vite pattern single quotes"),
        # Blocked: non-dev processes
        ("pkill bash", False, "bash not allowed"),
        ("pkill chrome", False, "chrome not allowed"),
        ("pkill systemd", False, "systemd not allowed"),
    ]

    for cmd, should_allow, description in test_cases:
        allowed, reason = validate_pkill_command(cmd)
        if allowed == should_allow:
            print(f"  PASS: {cmd!r} ({description})")
            passed += 1
        else:
            expected = "allowed" if should_allow else "blocked"
            actual = "allowed" if allowed else "blocked"
            print(f"  FAIL: {cmd!r} ({description})")
            print(f"         Expected: {expected}, Got: {actual}")
            if reason:
                print(f"         Reason: {reason}")
            failed += 1

    return passed, failed


def main():
    print("=" * 70)
    print("  SECURITY HOOK TESTS")
    print("=" * 70)

    passed = 0
    failed = 0

    # Test command extraction
    ext_passed, ext_failed = test_extract_commands()
    passed += ext_passed
    failed += ext_failed

    # Test inline comment stripping
    comment_passed, comment_failed = test_strip_inline_comments()
    passed += comment_passed
    failed += comment_failed

    # Test chmod validation
    chmod_passed, chmod_failed = test_validate_chmod()
    passed += chmod_passed
    failed += chmod_failed

    # Test helper script validation
    helper_passed, helper_failed = test_validate_helper_scripts()
    passed += helper_passed
    failed += helper_failed

    # Commands that SHOULD be blocked
    print("\nCommands that should be BLOCKED:\n")
    dangerous = [
        # Not in allowlist - dangerous system commands
        "shutdown now",
        "reboot",
        "rm -rf /",
        "rmdir dir/",
        "dd if=/dev/zero of=/dev/sda",
        "nc -l 4444",
        "netcat localhost 80",
        "ssh user@host",
        "scp file.txt user@host:",
        # Not in allowlist - package managers that could install malicious packages
        "apt install package",
        "apt-get install package",
        "yum install package",
        "brew install package",
        # killall not allowed (only pkill with specific processes)
        "killall node",
        "killall python",
        # pkill with non-dev processes
        "pkill bash",
        "pkill chrome",
        "pkill systemd",
        "pkill sshd",
        # Shell injection attempts
        "$(echo pkill) node",
        'eval "pkill node"',
        # chmod with disallowed modes
        "chmod 777 file.sh",
        "chmod 755 file.sh",
        "chmod +w file.sh",
        "chmod -R +x dir/",
        # Non-allowed scripts
        "./malicious.sh",
        "./setup.sh",  # Not in ALLOWED_HELPER_SCRIPTS
        "./deploy.sh",
    ]

    for cmd in dangerous:
        if _run_hook_test(cmd, should_block=True):
            passed += 1
        else:
            failed += 1

    # Commands that SHOULD be allowed
    print("\nCommands that should be ALLOWED:\n")
    safe = [
        # File inspection
        "ls -la",
        "cat README.md",
        "head -100 file.txt",
        "tail -20 log.txt",
        "wc -l file.txt",
        "grep -r pattern src/",
        "find . -name '*.py'",
        "diff file1.txt file2.txt",
        # File operations
        "cp file1.txt file2.txt",
        "mv old.txt new.txt",
        "mkdir newdir",
        "mkdir -p path/to/dir",
        "touch newfile.txt",
        "rm file.txt",
        # Network commands (allowed for development use)
        "curl https://example.com",
        "wget https://example.com",
        # Directory
        "pwd",
        # Python development (NEW)
        "python3 --version",
        "python3 test.py",
        "python3 -c 'print(1)'",
        "pip install requests",
        "pip3 install -r requirements.txt",
        "pytest tests/",
        "uvicorn app:app --reload",
        "alembic upgrade head",
        # Node.js development
        "npm install",
        "npm run build",
        "npm test",
        "npx create-next-app",
        "node server.js",
        "pnpm install",
        "pnpm dev",
        "yarn install",
        "yarn build",
        # Version control
        "git status",
        "git commit -m 'test'",
        "git add . && git commit -m 'msg'",
        "git add x && git commit -m 'msg'",
        # Process management
        "ps aux",
        "lsof -i :3000",
        "sleep 2",
        "kill 12345",
        # Allowed pkill patterns for dev servers
        "pkill node",
        "pkill npm",
        "pkill -f node",
        "pkill -f 'node server.js'",
        "pkill vite",
        "pkill -f 'vite.*3010'",
        "pkill next",
        # Shell utilities
        "echo hello",
        "printf 'test'",
        "env",
        "which python3",
        "type node",
        "export PATH=$PATH:/usr/local/bin",
        "true",
        "false",
        "test -f file.txt",
        # Chained commands
        "npm install && npm run build",
        "ls | grep test",
        "python3 --version && pip --version",
        # Full paths
        "/usr/local/bin/node app.js",
        "/usr/bin/python3 script.py",
        # TypeScript compiler (tsc)
        "./node_modules/.bin/tsc --noEmit",
        "npx tsc --noEmit",
        # chmod +x (allowed)
        "chmod +x init.sh",
        "chmod +x script.sh",
        "chmod u+x init.sh",
        "chmod a+x init.sh",
        # Helper scripts (allowed)
        "./init.sh",
        "./init.sh --production",
        "/path/to/init.sh",
        "./start-backend.sh",
        "./start-frontend.sh",
        "./run_test.sh",
        "./setup-frontend.sh",
        # Combined chmod and script execution
        "chmod +x init.sh && ./init.sh",
        "chmod +x start-backend.sh && ./start-backend.sh",
        # Shell script execution
        "bash -c 'echo hello'",
        "sh -c 'pwd'",
        # G2A: Commands with inline comments
        "ls -la # list all files",
        "mkdir -p src # create source dir",
        # G2B: Subshell syntax
        "(mkdir -p dir && cd dir)",
        "(echo hello)",
        # G2C: Variable assignment with $() substitution
        'PROJECT_NAME=$(basename "$PWD") && mkdir -p "$PROJECT_NAME"',
        # Symlinks (G2D: ln already in allowlist)
        "ln -s source target",
    ]

    for cmd in safe:
        if _run_hook_test(cmd, should_block=False):
            passed += 1
        else:
            failed += 1

    # Summary
    print("\n" + "-" * 70)
    print(f"  Results: {passed} passed, {failed} failed")
    print("-" * 70)

    if failed == 0:
        print("\n  ALL TESTS PASSED")
        return 0
    else:
        print(f"\n  {failed} TEST(S) FAILED")
        return 1


def test_security_hook_full_suite():
    """Run the full security hook test suite via pytest."""
    result = main()
    assert result == 0, f"Security hook tests failed with exit code {result}"


if __name__ == "__main__":
    sys.exit(main())
