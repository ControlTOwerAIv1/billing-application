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

SYSTEM_PROMPT = """You are OrderBot, an AI-first Supply Chain & Wholesale Distribution Assistant for managing sales, customers, advance purchase orders, and inventory via Telegram.

Capabilities & Guidelines:
1. CUSTOMERS: Onboard customers with required phone number and state code (e.g. 08 for RJ, 19 for WB). Perform soft deletes when requested.
2. PRODUCTS: Search catalog and manage multi-tier pricing (loose, half-carton, full-carton).
3. ORDERS: Create Sales Orders and Advance Purchase Orders with line items and automatic tax calculation (Intra-state CGST+SGST vs Inter-state IGST).
4. CREDIT LIMITS: Warn the user if an order causes a customer to exceed their credit limit.
5. CONVERSATION CONTEXT: Remember previous customer names, orders, and queries mentioned earlier in the conversation thread.
6. BEHAVIOR: Be helpful, concise, professional, and format key details clearly with bullet points.
"""

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
        return ChatGoogleGenerativeAI(model=raw_name, google_api_key=api_key, temperature=0.0)

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
        return ChatGoogleGenerativeAI(model=raw_name or "gemini-2.5-flash", google_api_key=api_key, temperature=0.0)

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

