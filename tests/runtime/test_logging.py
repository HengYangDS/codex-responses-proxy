#!/usr/bin/env python3
"""Unit contracts for bounded secret-safe operational logging."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.runtime import logging


class RuntimeLoggingTests(unittest.TestCase):
    def test_labels_and_paths_never_expose_caller_controlled_values(self) -> None:
        self.assertEqual(
            logging.safe_request_path("/v1/private path?secret=value"), "/v1/private_path"
        )
        self.assertEqual(logging.safe_request_path("relative?secret=value"), "/invalid-path")
        with mock.patch.object(logging.urllib.parse, "urlsplit", side_effect=ValueError):
            self.assertEqual(logging.safe_request_path("private"), "/invalid-path")
        self.assertEqual(
            (
                logging.safe_exception_label(ValueError("private")),
                logging.safe_exception_label(None),
            ),
            ("ValueError", "UnknownError"),
        )

    def test_logging_redacts_and_bounds_retention_without_becoming_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proxy.log"
            with (
                mock.patch.object(logging, "LOG_PATH", str(path)),
                mock.patch.object(logging, "LOG_MAX_BYTES", 16),
                mock.patch.object(logging, "LOG_BACKUP_COUNT", 2),
                mock.patch.object(logging.sys.stderr, "write"),
            ):
                logging.log(
                    "authorization: Bearer private-token encrypted=gAAAA-secret" + "x" * 2048
                )
                text = path.read_text()
                self.assertNotIn("private-token", text)
                self.assertNotIn("gAAAA-secret", text)
                path.write_text("x" * 17)
                logging.log("rotation")
                self.assertIn("discarded_oversized_bytes=17", path.read_text())
                path.write_text("x" * 12)
                (path.parent / "proxy.log.1").write_text("y" * 17)
                logging.log("backup rotation")
                self.assertTrue((path.parent / "proxy.log.1").exists())
                with mock.patch.object(logging, "LOG_BACKUP_COUNT", 0):
                    path.write_text("x" * 12)
                    logging.log("no backups")
                with mock.patch.object(Path, "exists", return_value=False):
                    path.write_text("x" * 12)
                    logging.log("no prior backup")
                (path.parent / "proxy.log.1").write_text("y" * 12)
                path.write_text("x" * 12)
                logging.log("retained backup")
                path.write_text("short")
                self.assertEqual(logging._rotate_log_if_needed(path, 1), 0)
                with mock.patch.object(Path, "lstat", side_effect=OSError):
                    self.assertEqual(logging._rotate_log_if_needed(path, 1), 0)
                path.unlink()
                path.mkdir()
                logging.log("ignored errors")
                with mock.patch.object(logging.sys.stderr, "write", side_effect=OSError):
                    logging.log("stderr error")


if __name__ == "__main__":
    unittest.main()
