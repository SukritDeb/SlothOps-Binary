"""
SlothOps Engine — Code Fetcher
Downloads relevant source files from the target GitHub repository
using PyGithub so the LLM has context for generating fixes.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from github import Github, GithubException

logger = logging.getLogger("slothops.code_fetcher")

# Max number of import files to fetch alongside the main file
_MAX_IMPORT_FILES = 3


def _get_test_path(file_path: str) -> Optional[str]:
    """
    Derive the conventional test file path from a source file path.

    Convention: ``src/routes/users.ts`` → ``tests/routes/users.test.ts``
    """
    if not file_path:
        return None

    # src/ → tests/
    test_path = file_path
    if test_path.startswith("src/"):
        test_path = "tests/" + test_path[4:]

    # .ts → .test.ts   |   .js → .test.js
    for ext in (".ts", ".js"):
        if test_path.endswith(ext):
            test_path = test_path[: -len(ext)] + f".test{ext}"
            return test_path

    return None


def _extract_imports(source: str, base_dir: str) -> list[str]:
    """
    Parse local import paths from TypeScript / JavaScript source.

    Matches:
        import ... from './foo'
        import ... from '../services/bar'
        const x = require('./baz')

    Returns absolute repo-relative paths (with .ts extension assumed).
    Skips anything that looks like an npm package (no leading dot).
    """
    pattern = r"""(?:import\s+.*?\s+from\s+['"](\.[^'"]+)['"]|require\(\s*['"](\.[^'"]+)['"]\s*\))"""
    matches = re.findall(pattern, source)

    paths: list[str] = []
    for groups in matches:
        rel = groups[0] or groups[1]
        if not rel:
            continue

        # Resolve relative path against base_dir
        parts = base_dir.rstrip("/").split("/")
        for segment in rel.split("/"):
            if segment == "..":
                if parts:
                    parts.pop()
            elif segment != ".":
                parts.append(segment)
        resolved = "/".join(parts)

        # Add .ts extension if missing
        if not resolved.endswith((".ts", ".js", ".tsx", ".jsx")):
            resolved += ".ts"

        if resolved not in paths:
            paths.append(resolved)

    return paths[:_MAX_IMPORT_FILES]


def _fetch_file(repo, path: str) -> Optional[str]:
    """Fetch a single file's decoded content from GitHub. Returns None on 404."""
    try:
        content_file = repo.get_contents(path)
        if isinstance(content_file, list):
            return None  # It's a directory
        return content_file.decoded_content.decode("utf-8")
    except GithubException as exc:
        if exc.status == 404:
            logger.debug("File not found on GitHub: %s", path)
        else:
            logger.warning("GitHub error fetching %s: %s", path, exc)
        return None


def fetch_code_context(
    file_path: str | None,
    repo,
    source_content_override: str | None = None,
) -> dict[str, str]:
    """
    Fetch code context from GitHub for the failing file.

    Returns a dict mapping file paths to their full content::

        {
            "src/routes/users.ts": "...",
            "tests/routes/users.test.ts": "...",
            "src/services/userService.ts": "...",
        }

    At most 5 files are returned (main + test + up to 3 imports).
    """
    if not file_path:
        return {}

    context: dict[str, str] = {}

    # 1. Main failing file
    main_content = source_content_override or _fetch_file(repo, file_path)
    if main_content:
        context[file_path] = main_content
    else:
        logger.warning("Could not fetch main file: %s", file_path)
        return context

    # 2. Test file
    test_path = _get_test_path(file_path)
    if test_path:
        test_content = _fetch_file(repo, test_path)
        if test_content:
            context[test_path] = test_content

    # 3. Local imports
    base_dir = "/".join(file_path.split("/")[:-1])
    import_paths = _extract_imports(main_content, base_dir)
    for imp_path in import_paths:
        if imp_path not in context:
            imp_content = _fetch_file(repo, imp_path)
            if imp_content:
                context[imp_path] = imp_content

    return context
