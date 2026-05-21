"""
Routing logic tests — verify supervisor decisions without calling the LLM.
Tests use the state machine directly to validate conditional edge routing.

conftest.py pre-imports app.agent with asyncio.run stubbed, so these tests
never trigger MCP or LLM initialisation.
"""
import os
import pytest
from unittest.mock import MagicMock, AsyncMock

os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("TAVILY_API_KEY", "test-tavily")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


class TestCheckForToolCalls:
    """check_for_tool_calls helper routes based on last message type."""

    def test_routes_to_supervisor_when_no_tool_calls(self):
        from langchain_core.messages import AIMessage
        from app.agent import check_for_tool_calls
        state = {"messages": [AIMessage(content="Hello!")]}
        result = check_for_tool_calls(state)
        assert result == "supervisor"

    def test_routes_to_continue_with_tools_when_tool_calls_present(self):
        from langchain_core.messages import AIMessage
        from app.agent import check_for_tool_calls
        ai_msg = AIMessage(content="")
        ai_msg.tool_calls = [{"id": "1", "name": "some_tool", "args": {}}]
        state = {"messages": [ai_msg]}
        result = check_for_tool_calls(state)
        assert result == "continue_with_tools"


class TestSupervisorFastPaths:
    """Supervisor router fast paths (no LLM call)."""

    @pytest.mark.asyncio
    async def test_clean_ai_message_routes_to_end(self):
        from langchain_core.messages import AIMessage
        from app.agent import supervisor_router
        state = {
            "messages": [AIMessage(content="Here are our dresses!")],
            "plan": [],
            "current_step": 0,
            "reflections": [],
            "memory_context": "",
            "user_profile": {},
            "thread_id": "t1",
            "next": "",
        }
        result = await supervisor_router(state)
        assert result["next"] == "__end__"

    @pytest.mark.asyncio
    async def test_cod_success_tool_message_routes_to_end(self):
        import json
        from langchain_core.messages import ToolMessage
        from app.agent import supervisor_router
        receipt = json.dumps({"status": "COD_SUCCESS", "order_number": "PAM-20260521-AB12"})
        state = {
            "messages": [ToolMessage(content=receipt, tool_call_id="t1")],
            "plan": [],
            "current_step": 0,
            "reflections": [],
            "memory_context": "",
            "user_profile": {},
            "thread_id": "t1",
            "next": "",
        }
        result = await supervisor_router(state)
        assert result["next"] == "__end__"


class TestSalesAgentPromptContents:
    """Verify the SALES_SYSTEM prompt handles critical edge cases."""

    def test_sales_system_mentions_partial_info_handling(self):
        from app.agent import SALES_SYSTEM
        assert "missing" in SALES_SYSTEM.lower() or "partial" in SALES_SYSTEM.lower() or "only" in SALES_SYSTEM.lower()

    def test_sales_system_mentions_delivery_date(self):
        from app.agent import SALES_SYSTEM
        assert "delivery" in SALES_SYSTEM.lower()

    def test_sales_system_mentions_whatsapp(self):
        from app.agent import SALES_SYSTEM
        assert "whatsapp" in SALES_SYSTEM.lower()

    def test_data_query_system_mentions_buy_hint(self):
        from app.agent import DATA_QUERY_SYSTEM
        assert "buy" in DATA_QUERY_SYSTEM.lower() or "order" in DATA_QUERY_SYSTEM.lower()
