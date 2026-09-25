import unittest
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice.messages import get_reminder_message, MESSAGES

class TestVoiceMessages(unittest.TestCase):
    def test_message_retrieval(self):
        msg1 = get_reminder_message("Motivational", level=1)
        self.assertIn(msg1, MESSAGES["Motivational"])

        msg_tamil = get_reminder_message("Tamil-English", level=1)
        self.assertIn(msg_tamil, MESSAGES["Tamil-English"])

    def test_escalation(self):
        msg_lvl1 = get_reminder_message("Professional", level=1)
        msg_lvl2 = get_reminder_message("Professional", level=2)
        self.assertNotEqual(msg_lvl1, msg_lvl2)

if __name__ == "__main__":
    unittest.main()
