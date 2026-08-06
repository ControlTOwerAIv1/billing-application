import os
import sys
import json
import django
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from backend.config import ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, LLM_MODEL
from backend.agent.agent import OrderBotAgent

def main():
    print("=" * 65)
    print("      ORDERBOT AI CONVERSATIONAL TERMINAL CONSOLE         ")
    print("=" * 65)
    print(f"[+] Active LLM Model: {LLM_MODEL}")

    has_key = bool(ANTHROPIC_API_KEY or OPENAI_API_KEY or GEMINI_API_KEY)
    if not has_key:
        print("[!] Warning: No API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY) found in .env")
        print("    Please set a valid API key in .env to test live AI completions.\n")
    else:
        print("[+] API Key loaded successfully.\n")

    print("Try typing natural language prompts:")
    print(" 1. 'Onboard customer Ramesh Toys from Kolkata with phone 9876543210 and credit limit 50000'")
    print(" 2. 'Add product SKU-100 Remote Car price 250 and carton price 5000'")
    print(" 3. 'Create a sales order for Ramesh Toys: 1 carton of SKU-100'")
    print(" 4. 'Record payment of 2000 from Ramesh Toys via GPay'")
    print(" 5. 'Show ledger for Ramesh Toys'")
    print(" 6. 'Type exit or quit to stop'")
    print("-" * 65)

    agent = OrderBotAgent()
    chat_history = []

    while True:
        try:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit"]:
                print("\nExiting OrderBot CLI. Goodbye!")
                break

            result = agent.process_message(user_input, chat_history=chat_history)

            if result.get("status") == "success":
                chat_history = result.get("updated_history", chat_history)

                # Show tool calls if AI decided to invoke any database tools
                tool_calls = result.get("tool_calls", [])
                if tool_calls:
                    print("\n🤖 [AI Agent Tool Execution Trace]:")
                    for tc in tool_calls:
                        print(f"   ⚙️  Executed Tool: {tc['tool']}")
                        print(f"      Arguments:     {json.dumps(tc['args'])}")
                        print(f"      Database Out:  {json.dumps(tc['result'])}")

                print(f"\nOrderBot AI: {result.get('response')}")
            else:
                print(f"\n❌ Error: {result.get('message')}")

        except KeyboardInterrupt:
            print("\nExiting OrderBot CLI. Goodbye!")
            break

if __name__ == "__main__":
    main()
