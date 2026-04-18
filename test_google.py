import sys
import asyncio
from friday.tools.google_suite import list_upcoming_events, list_recent_emails

def test_google():
    print("=== Testing Google Calendar ===")
    try:
        events = list_upcoming_events(days=2)
        print(events)
    except Exception as e:
        print(f"Calendar Error: {e}")

    print("\n=== Testing Gmail ===")
    try:
        emails = list_recent_emails(limit=3)
        print(emails)
    except Exception as e:
        print(f"Gmail Error: {e}")

if __name__ == "__main__":
    test_google()
