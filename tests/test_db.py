import unittest
import os
import sys
import tempfile

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import DatabaseManager

class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.db = DatabaseManager(self.temp_db.name)

    def tearDown(self):
        del self.db
        import gc
        gc.collect()
        try:
            if os.path.exists(self.temp_db.name):
                os.remove(self.temp_db.name)
        except Exception:
            pass

    def test_session_lifecycle(self):
        session_id = self.db.start_session()
        self.assertIsNotNone(session_id)
        
        self.db.update_session(
            session_id=session_id,
            duration=60,
            focused=48,
            away=12,
            distracted=0,
            reminders=1,
            score=80.0
        )

        recent = self.db.get_recent_sessions(limit=5)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["focus_score"], 80.0)

    def test_aggregate_stats(self):
        s1 = self.db.start_session()
        self.db.update_session(s1, 100, 80, 20, 0, 1, 80.0)

        s2 = self.db.start_session()
        self.db.update_session(s2, 200, 180, 20, 0, 0, 90.0)

        stats = self.db.get_aggregate_stats()
        self.assertEqual(stats["total_sessions"], 2)
        self.assertEqual(stats["total_duration"], 300)
        self.assertEqual(stats["avg_focus_score"], 85.0)

if __name__ == "__main__":
    unittest.main()
