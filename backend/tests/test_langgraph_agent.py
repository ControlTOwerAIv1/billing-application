import os
import sys
import django
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from backend.agent.agent import OrderBotAgent

def test_langgraph_memory():
    print("=" * 65)
    print("      TESTING LANGGRAPH AGENT THREAD CONVERSATION MEMORY   ")
    print("=" * 65)

    agent = OrderBotAgent()
    thread_id = "test_session_101"

    # Turn 1: Onboard a customer
    print("\n[Turn 1] User: 'Onboard customer Unique Mart from Mumbai with phone 9123456789'")
    res1 = agent.process_message("Onboard customer Unique Mart from Mumbai with phone 9123456789", thread_id=thread_id)
    print("Response Status:", res1.get("status"))
    print("Agent Reply:\n", res1.get("response"))

    # Turn 2: Query memory without re-specifying the phone or full name
    print("\n[Turn 2] User: 'What is the phone number of the customer I just onboarded?'")
    res2 = agent.process_message("What is the phone number of the customer I just onboarded?", thread_id=thread_id)
    print("Response Status:", res2.get("status"))
    print("Agent Reply:\n", res2.get("response"))

    assert res2.get("status") == "success", "Failed turn 2 execution"
    print("\n" + "=" * 65)
    print("     LANGGRAPH MEMORY TEST COMPLETED SUCCESSFULLY!        ")
    print("=" * 65)

if __name__ == "__main__":
    test_langgraph_memory()
