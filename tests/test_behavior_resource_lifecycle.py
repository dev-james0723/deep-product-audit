"""Regression check for explicit SQLite cleanup; no platform-specific FD API."""
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock

import behavior_lab as lab


class ResourceLifecycleTests(unittest.TestCase):
    def test_demo_explicitly_closes_every_sqlite_connection(self):
        connections = []  # Strong references prevent GC from hiding a missing close.
        lock = threading.Lock()
        real_connect = sqlite3.connect
        real_temporary_directory = tempfile.TemporaryDirectory

        def tracked_connect(*args, **kwargs):
            # Queries below run after owned handler threads have stopped. Disable
            # only the thread-identity check so it cannot masquerade as "closed".
            kwargs["check_same_thread"] = False
            connection = real_connect(*args, **kwargs)
            with lock:
                connections.append(connection)
            return connection

        with real_temporary_directory(prefix="behavior-resource-test-") as owned:
            def owned_temporary_directory(*args, **kwargs):
                kwargs["dir"] = owned
                return real_temporary_directory(*args, **kwargs)

            result, cleanup_error = None, None
            try:
                with mock.patch.object(lab.sqlite3, "connect", side_effect=tracked_connect), \
                        mock.patch.object(lab.tempfile, "TemporaryDirectory", side_effect=owned_temporary_directory):
                    try:
                        result = lab.run_demo()
                    except OSError as error:
                        # On Windows an open database may first prevent directory
                        # removal. Still inspect the held connections, then close
                        # every handle before this test's outer directory cleanup.
                        cleanup_error = error

                self.assertGreater(len(connections), 0, "The fixture must create real SQLite connections")
                still_open = []
                for index, connection in enumerate(connections):
                    try:
                        connection.execute("SELECT 1").fetchone()
                    except sqlite3.ProgrammingError as error:
                        self.assertIn("closed database", str(error))
                    else:
                        still_open.append(index)
                self.assertEqual(still_open, [],
                                 f"Fixture teardown left {len(still_open)} of {len(connections)} SQLite connections open")
                self.assertIsNone(cleanup_error, f"Owned fixture cleanup failed: {cleanup_error}")
                self.assertTrue(result["demo_validated"], result)
            finally:
                for connection in connections:
                    connection.close()


if __name__ == "__main__":
    unittest.main()
