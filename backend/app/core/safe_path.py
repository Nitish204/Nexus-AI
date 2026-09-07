"""
NEXUS — Path sanitization for AI-generated file paths.

`GeneratedFile.path` is written by an LLM (the Backend/Frontend/DevOps
agents decide the filename for every file they produce) and stored as
plain text with zero validation anywhere upstream. That path is later
used directly in three places that touch a real filesystem or a real
API:

  1. app/sandbox/runner.py   — writes into a tar stream extracted
     inside a Docker container.
  2. app/services/deployment.py — writes directly onto the HOST
     filesystem (a tempdir on the server actually running NEXUS).
  3. app/services/github_export.py — used as a URL path segment
     against the GitHub Contents API.

None of these treated the path as untrusted input. Concretely:

  `Path("/tmp/nexus-deploy-xyz") / "/etc/cron.d/malicious"` evaluates
  to `Path("/etc/cron.d/malicious")` — pathlib silently drops the base
  directory entirely when the right-hand side is absolute. So a
  generated file path that happens to be (or is manipulated via a
  prompt-injected instruction hidden in a file an agent reads, or a
  crafted task description) an absolute path, or something like
  "../../../etc/cron.d/x", writes outside the intended directory —
  in the deployment case, that's a write to the real host filesystem,
  not a disposable container.

`safe_relative_path()` is the single place that decides whether a
generated path is safe to use, so all three call sites share one
definition of "safe" instead of three ad-hoc ones that could drift.
"""
from __future__ import annotations

import posixpath


class UnsafeGeneratedPath(ValueError):
    """Raised when a GeneratedFile.path can't be safely written to disk."""


def safe_relative_path(raw_path: str) -> str:
    """
    Normalize `raw_path` and guarantee the result is a relative path
    that stays inside its intended root — no absolute paths, no `..`
    segments that climb above the root, no empty/blank paths.

    Returns the normalized, safe relative path (posix-style, using
    forward slashes) on success. Raises UnsafeGeneratedPath otherwise.
    """
    if not raw_path or not raw_path.strip():
        raise UnsafeGeneratedPath("Empty file path.")

    # Normalize backslashes (Windows-style paths an agent might emit)
    # to forward slashes before doing posix-style normalization.
    candidate = raw_path.strip().replace("\\", "/")

    # Reject absolute paths outright — pathlib's `/` operator silently
    # discards the base directory when the right side is absolute,
    # which is exactly the bug being fixed here.
    if candidate.startswith("/") or (len(candidate) > 1 and candidate[1] == ":"):
        raise UnsafeGeneratedPath(f"Absolute paths are not allowed: {raw_path!r}")

    # posixpath.normpath collapses "a/./b" -> "a/b" and resolves
    # "a/../b" -> "b", which lets us reliably detect any attempt to
    # climb above the root: after normalizing, a safe relative path
    # can never start with "..".
    normalized = posixpath.normpath(candidate)
    if normalized == "." or normalized.startswith("..") or normalized.startswith("/"):
        raise UnsafeGeneratedPath(f"Path escapes its project root: {raw_path!r}")

    return normalized
