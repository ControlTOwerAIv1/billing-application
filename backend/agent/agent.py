import os
import sys
import json
import logging
from pathlib import Path
import django

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
django.setup()

from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from backend.config import ANTHROPIC_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, LLM_MODEL
from backend.agent.tools import LANGCHAIN_TOOLS

SYSTEM_PROMPT = """You are OrderBot, an AI-first Supply Chain & Wholesale Distribution Assistant for managing sales, customers, advance purchase orders, and inventory.

Core Guidelines & Protocols:

1. CUSTOMER LISTING & FILTERS:
   - When the user asks generally to list or query customers (e.g., "list customers", "show me our buyers", "get customers list"), DO NOT just dump an unfiltered list. Instead, proactively ask what filter they would like to apply:
     • Location / City (e.g., Kolkata, Jaipur, Delhi)
     • State Code (e.g., 08 for RJ, 19 for WB)
     • Outstanding balance (customers with pending dues)
     • Account status (Approved, Pending, Blocked)
     • Or specify if they wish to see all active customers.
   - If they specify a filter (e.g. "show customers from Kolkata" or "list customers with dues"), immediately use `search_customers` with the respective filter.

2. CUSTOMER LOCATION & DISAMBIGUATION:
   - In all customer interactions and responses, ALWAYS include their location (e.g., "Raj Wholesalers from Kolkata (WB)" or "Sharma Enterprises from Jaipur (RJ)").
   - If multiple customers share the same or similar names when creating an order, recording a payment, or deleting: NEVER guess or assume. Ask for clarification immediately:
     Example: "Did you mean Raj Wholesalers from Kolkata (WB, Ph: +91-98765...) or Raj Wholesalers from Jaipur (RJ, Ph: +91-91234...)?"

3. ADDING A NEW PRODUCT (REQUIRED FIELDS & PHOTO):
   - Adding a product requires ALL of the following fields:
     1. SKU code (e.g. STAT-A4-500)
     2. Product Name
     3. Category (e.g. Stationery, Plastics, Packaging)
     4. Product Photo / Image URL
     5. Unit / Loose price (INR)
     6. Full carton box price (INR)
     7. Full carton quantity (units per carton box)
     8. GST rate (e.g. 18%, 12%, 5%)
   - When the user uploads a photo in Telegram or provides an attached photo URL (e.g. `[Attached Product Image URL(s): ...]`), ALWAYS use that as the `image_url` for `create_product`.
   - If ANY of these fields (especially the photo/image URL) are completely missing from the user's prompt and conversation, DO NOT call `create_product`. Instead, ask the user to provide the missing fields including uploading a product photo before proceeding.

4. ORDER EDIT FLOW:
   - Users can edit existing orders (change status to packed/dispatched/delivered/cancelled, add or remove items, or update item quantities).
   - Use `edit_order` to update the order. Explain the changes made, the updated subtotal and GST breakdown, the new grand total, and any balance adjustments.

5. PAYMENT RECORDING & AMOUNT CLARIFICATION:
   - When recording a payment (`record_payment`), NEVER assume, infer, or default the payment amount to the customer's total outstanding balance unless the user explicitly tells you to pay the full balance (e.g., "record full payment", "clear all dues", "pay 12500").
   - If the user selects, clarifies, or names a customer for a payment (e.g. "for kolkata raj wholesalers" or "add payment for jafer") but has NOT explicitly specified the amount, DO NOT call `record_payment`. Instead, acknowledge the customer with their location and current outstanding balance, and ask the user how much payment amount they want to record (and optionally payment mode like Cash/UPI/Bank).

6. AMBIGUITY CLARIFICATION & ORDER FLOW:
   - When a user picks or clarifies a customer for an order (e.g., 'for raju bhai') but has not yet specified which products, SKUs, or quantities they want, DO NOT call `create_order`. Acknowledge the selected customer with their location and ask what items and quantities they want to order.
   - Whenever any request is ambiguous (such as ambiguous customer identity, unclear product SKU, missing required fields, unclear quantities, or unspecified payment amount), ALWAYS stop and clarify with the user before moving on with execution.

7. BEHAVIOR & CONTEXT:
   - Be helpful, concise, and professional. Format outputs with clear bullet points, currency symbols (₹), and highlighted voucher numbers.

8. TRANSPORT MANAGEMENT & CUSTOMER CREATION:
   - Users can add transports / logistics carrier services (e.g., "add transport VRL Logistics phone 9876543210", "create transport Blue Dart"). Use `create_transport` to add them. Use `list_transports` to view available carriers.
   - When creating a customer (`create_customer`), ALWAYS check or ask which transport the customer will use for shipments. If no transport was provided in the initial prompt, proactively present the available transports and ask the user which transport this customer prefers. Use `assign_customer_transport` when they specify one.
   - When creating an order (`create_order`), orders can travel through either of the transports. It defaults to the customer's assigned transport unless the user specifies a different transport.
"""

import warnings
warnings.filterwarnings("ignore", message=".*uses fixed sampling defaults.*", category=UserWarning)

def get_langchain_model(model_name: str):
    """
    Instantiates appropriate LangChain ChatModel based on model_name prefix.
    Supports Gemini, OpenAI, Claude/Anthropic.
    """
    model_str = model_name or LLM_MODEL or "gemini/gemini-2.5-flash"
    raw_name = model_str.split("/", 1)[-1] if "/" in model_str else model_str

    if "gemini" in model_str.lower():
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = GEMINI_API_KEY or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key and not os.getenv("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = api_key
        return ChatGoogleGenerativeAI(model=raw_name, google_api_key=api_key)

    elif "claude" in model_str.lower() or "anthropic" in model_str.lower():
        from langchain_anthropic import ChatAnthropic
        api_key = ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY")
        return ChatAnthropic(model=raw_name, api_key=api_key, temperature=0.0)

    elif "gpt" in model_str.lower() or "openai" in model_str.lower():
        from langchain_openai import ChatOpenAI
        api_key = OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
        return ChatOpenAI(model=raw_name, api_key=api_key, temperature=0.0)

    else:
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = GEMINI_API_KEY or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        return ChatGoogleGenerativeAI(model=raw_name or "gemini-2.5-flash", google_api_key=api_key)

class OrderBotAgent:
    def __init__(self, model_name: str = None, checkpointer = None):
        self.model_name = model_name or LLM_MODEL or "gemini/gemini-2.5-flash"
        
        # Populate env vars for LiteLLM if set in backend/config
        if GEMINI_API_KEY and not os.getenv("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
        if ANTHROPIC_API_KEY and not os.getenv("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
        if OPENAI_API_KEY and not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

        self.checkpointer = checkpointer or MemorySaver()
        self.llm = get_langchain_model(self.model_name)
        self.graph = create_react_agent(
            model=self.llm,
            tools=LANGCHAIN_TOOLS,
            prompt=SYSTEM_PROMPT,
            checkpointer=self.checkpointer
        )

    def process_message(self, user_message: str, chat_history: list = None, thread_id: str = "default") -> dict:
        """
        Processes user message using LangGraph ReAct agent with thread-isolated checkpointer memory.
        Fully LLM Provider-Agnostic via LiteLLM.
        """
        config = {"configurable": {"thread_id": thread_id}}

        try:
            res = self.graph.invoke({"messages": [("user", user_message)]}, config=config)
            
            messages = res.get("messages", [])
            final_content = "Done."
            tool_calls_executed = []
            
            if messages:
                last_msg = messages[-1]
                if hasattr(last_msg, "content"):
                    raw_content = last_msg.content
                    if isinstance(raw_content, list):
                        parts = []
                        for block in raw_content:
                            if isinstance(block, dict) and "text" in block:
                                parts.append(block["text"])
                            elif isinstance(block, str):
                                parts.append(block)
                        final_content = "\n".join(parts) if parts else str(raw_content)
                    else:
                        final_content = str(raw_content or "Done.")

                for msg in messages:
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            tool_calls_executed.append({
                                "tool": tc.get("name"),
                                "args": tc.get("args"),
                            })

            return {
                "status": "success",
                "message": final_content,
                "response": final_content,
                "tool_calls": tool_calls_executed
            }

        except Exception as e:
            err_str = str(e)
            if "RateLimitError" in type(e).__name__ or "429" in err_str or "quota" in err_str.lower():
                msg = f"⚠️ Model '{self.model_name}' was rate limited (429 Quota Exceeded). Please try again in a moment."
            else:
                msg = f"⚠️ LangGraph Agent Error calling '{self.model_name}': {err_str}"

            print(f"[LangGraph Error]: {msg}")
            return {"status": "error", "message": msg, "response": msg}

    def process_command(self, user_intent: str, module_name: str = "customers", provided_data: dict = None) -> dict:
        return self.process_message(user_intent)

    def clear_memory(self, thread_id: str = "default") -> None:
        """Wipes the conversation checkpoint memory for a given thread (chat)."""
        try:
            self.checkpointer.delete_thread(thread_id)
        except Exception as e:
            print(f"[Agent Clear Memory Error]: {e}")

