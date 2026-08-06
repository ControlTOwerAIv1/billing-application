import os
import sys
import json
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.config import ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, LLM_MODEL
from backend.agent.tools import TOOLS_SCHEMA, EXECUTE_TOOL_MAP

SYSTEM_PROMPT = """You are OrderBot, an AI-first Supply Chain & Wholesale Distribution Assistant for managing sales, customers, advance purchase orders, and inventory via Telegram.

Capabilities & Guidelines:
1. CUSTOMERS: Onboard customers with required phone number and state code (e.g. 08 for RJ, 19 for WB). Perform soft deletes when requested.
2. PRODUCTS: Search catalog and manage multi-tier pricing (loose, half-carton, full-carton).
3. ORDERS: Create Sales Orders and Advance Purchase Orders with line items and automatic tax calculation (Intra-state CGST+SGST vs Inter-state IGST).
4. CREDIT LIMITS: Warn the user if an order causes a customer to exceed their credit limit.
5. BEHAVIOR: Be helpful, concise, professional, and format key details clearly with bullet points.
"""

class OrderBotAgent:
    def __init__(self, model_name: str = None):
        self.model_name = model_name or LLM_MODEL
        # Configure env variables for litellm
        if ANTHROPIC_API_KEY and not os.getenv("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
        if OPENAI_API_KEY and not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
        if GEMINI_API_KEY and not os.getenv("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

    def process_message(self, user_message: str, chat_history: list = None) -> dict:
        """
        Processes incoming user message using LiteLLM with multi-turn tool calling.
        """
        try:
            import litellm
        except ImportError:
            return {
                "status": "error",
                "message": "LiteLLM module is installing. Please try again in a few seconds."
            }

        if chat_history is None:
            chat_history = []

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in chat_history:
            messages.append(msg)

        messages.append({"role": "user", "content": user_message})

        tool_calls_executed = []
        max_turns = 5
        turn = 0

        while turn < max_turns:
            turn += 1
            try:
                response = litellm.completion(
                    model=self.model_name,
                    messages=messages,
                    tools=TOOLS_SCHEMA,
                    tool_choice="auto"
                )
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"LiteLLM Error calling model '{self.model_name}': {str(e)}"
                }

            response_message = response.choices[0].message
            tool_calls = getattr(response_message, "tool_calls", None)

            if not tool_calls:
                # Agent has finished tool calling and produced final text
                final_content = response_message.content or "Done."
                return {
                    "status": "success",
                    "response": final_content,
                    "tool_calls": tool_calls_executed,
                    "updated_history": messages + [{"role": "assistant", "content": final_content}]
                }

            # Convert response_message to dict format for message history
            assistant_msg = {"role": "assistant", "content": response_message.content, "tool_calls": []}
            for tc in tool_calls:
                assistant_msg["tool_calls"].append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                })
            messages.append(assistant_msg)

            # Execute returned tool calls
            for tc in tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except Exception:
                    fn_args = {}

                if fn_name in EXECUTE_TOOL_MAP:
                    tool_result = EXECUTE_TOOL_MAP[fn_name](**fn_args)
                else:
                    tool_result = {"error": f"Unknown tool '{fn_name}'"}

                tool_calls_executed.append({
                    "tool": fn_name,
                    "args": fn_args,
                    "result": tool_result
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": fn_name,
                    "content": json.dumps(tool_result, ensure_ascii=False)
                })
        
        return {
            "status": "success",
            "response": "Completed maximum tool execution steps.",
            "tool_calls": tool_calls_executed,
            "updated_history": messages
        }
