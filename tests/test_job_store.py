import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs import JobStore


class JobStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "jobs.json"
        self.store = JobStore(str(self.path))

    def test_create_applies_defaults_truncation_and_filters(self):
        long_title = "T" * 300
        long_body = "B" * 2000

        first = self.store.create(
            title=long_title,
            job_type="job",
            channel="general",
            created_by="ben",
            body=long_body,
        )
        second = self.store.create(
            title="Second",
            job_type="job",
            channel="debug",
            created_by="ben",
        )

        self.assertEqual(first["status"], "done")
        self.assertEqual(first["sort_order"], 1)
        self.assertEqual(second["sort_order"], 2)
        self.assertEqual(len(first["title"]), 120)
        self.assertEqual(len(first["body"]), 1000)
        self.assertEqual(len(self.store.list_all(status="done")), 2)
        self.assertEqual(len(self.store.list_all(channel="debug")), 1)

    def test_update_status_assigns_order_in_target_group(self):
        a = self.store.create("A", "job", "general", "ben")
        b = self.store.create("B", "job", "general", "ben")

        moved_a = self.store.update_status(a["id"], "open")
        moved_b = self.store.update_status(b["id"], "open")
        same_status = self.store.update_status(b["id"], "open")

        self.assertEqual(moved_a["status"], "open")
        self.assertEqual(moved_a["sort_order"], 1)
        self.assertEqual(moved_b["sort_order"], 2)
        self.assertEqual(same_status["sort_order"], 2)
        self.assertIsNone(self.store.update_status(a["id"], "not-a-status"))

    def test_reorder_uses_explicit_order_and_appends_others(self):
        j1 = self.store.create("One", "job", "general", "ben")
        j2 = self.store.create("Two", "job", "general", "ben")
        j3 = self.store.create("Three", "job", "general", "ben")

        self.store.update_status(j1["id"], "open")
        self.store.update_status(j2["id"], "open")
        self.store.update_status(j3["id"], "open")

        changed = self.store.reorder("open", [j3["id"], j1["id"]])

        open_jobs = self.store.list_all(status="open")
        ordered_ids = [
            job["id"]
            for job in sorted(
                open_jobs,
                key=lambda x: int(x.get("sort_order", 0) or 0),
                reverse=True,
            )
        ]
        changed_ids = {int(item["id"]) for item in changed}

        self.assertEqual(ordered_ids, [j3["id"], j1["id"], j2["id"]])
        self.assertEqual(changed_ids, {j1["id"], j2["id"]})
        self.assertEqual(self.store.reorder("not-a-status", [j1["id"]]), [])

    def test_callbacks_and_messages_emit_expected_actions(self):
        events = []

        def on_change(action, data):
            events.append((action, data))

        self.store.on_change(on_change)

        job = self.store.create("Task", "job", "general", "ben")
        self.store.update_title(job["id"], "Task updated")
        msg = self.store.add_message(
            job["id"],
            sender="codex",
            text="consider option A",
            attachments=[{"url": "/uploads/a.png", "name": "a.png"}],
            msg_type="suggestion",
        )
        deleted = self.store.delete(job["id"])

        actions = [action for action, _ in events]
        self.assertEqual(actions, ["create", "update", "message", "delete"])
        self.assertEqual(msg["job_id"], job["id"])
        self.assertEqual(msg["type"], "suggestion")
        self.assertEqual(msg["attachments"][0]["name"], "a.png")
        self.assertEqual(deleted["id"], job["id"])
        self.assertIsNone(self.store.get(job["id"]))

    def test_persistence_round_trip_reloads_jobs_and_ids(self):
        created = self.store.create("Persist me", "job", "general", "ben")

        reloaded = JobStore(str(self.path))
        fetched = reloaded.get(created["id"])
        next_job = reloaded.create("Second", "job", "general", "ben")

        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["title"], "Persist me")
        self.assertEqual(next_job["id"], created["id"] + 1)


if __name__ == "__main__":
    unittest.main()
