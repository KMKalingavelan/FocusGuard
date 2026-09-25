"""
FocusGuard — Voice Messages
Single clear professional reminder message played when student is absent.
"""

# The ONLY voice message — played when person is not in the camera frame
ABSENT_REMINDER = "Please come back to study area immediately."

def get_reminder_message(style="Professional", level=1):
    """Returns the single absent reminder message regardless of style or level."""
    return ABSENT_REMINDER

def get_motivational_hook(state="AWAY"):
    """Returns on-screen hook text for the UI banner."""
    if state == "AWAY":
        return "🚨 STUDENT NOT IN FRAME — Please Return to Study Area"
    return "📖 STAY FOCUSED & KEEP STUDYING!"
