import os
import sys
import django
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from backend.agent.agent import OrderBotAgent
from backend.agent.tools import tool_search_customers, tool_search_products, tool_list_orders

def test_agent_tools():
    print("=" * 65)
    print("      TESTING ORDERBOT AGENT TOOL DISPATCH SYSTEM         ")
    print("=" * 65)

    agent = OrderBotAgent()

    # 1. Direct tool execution test
    print("\n[1] Searching customers...")
    res_cust = tool_search_customers("Raju")
    print("Search Result:", res_cust)

    print("\n[2] Searching products...")
    res_prod = tool_search_products("TOY")
    print("Search Result:", res_prod)

    print("\n[3] Listing orders...")
    res_orders = tool_list_orders()
    print("List Orders Result:", res_orders)

    print("\n" + "=" * 65)
    print("     AGENT TOOL DISPATCH TEST COMPLETED SUCCESSFULLY!     ")
    print("=" * 65)

if __name__ == "__main__":
    test_agent_tools()
