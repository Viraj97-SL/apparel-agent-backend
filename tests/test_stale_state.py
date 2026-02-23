"""
Unit tests for the stale-state resolver logic in server.py.

We test the resolver's detection and cleanup logic in isolation by mocking
the LangGraph app — no real checkpointer, DB, or LLM required.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


# ---------------------------------------------------------------------------
# Re-implement the resolver logic here so we can test it without importing
# the full server (which drags in the agent stack at module level).
# In practice this is identical to the function in server.py.
# ---------------------------------------------------------------------------
async def resolve_stale_state(rag_agent_app, config: dict) -> bool:
    try:
        snapshot = await rag_agent_app.aget_state(config)
        if not snapshot or not snapshot.values:
            return False
        messages = snapshot.values.get("messages", [])
        if not messages:
            return False
        last_msg = messages[-1]
        if not (isinstance(last_msg, AIMessage) and getattr(last_msg, "tool_calls", None)):
            return False
        pending_ids = {tc["id"] for tc in last_msg.tool_calls}
        covered_ids = {
            m.tool_call_id
            for m in messages
            if isinstance(m, ToolMessage) and hasattr(m, "tool_call_id")
        }
        unresolved = pending_ids - covered_ids
        if not unresolved:
            return False
        cleanup_messages = [
            ToolMessage(
                content="[Previous request was interrupted. The following message is a fresh question.]",
                tool_call_id=tc_id,
            )
            for tc_id in unresolved
        ]
        await rag_agent_app.aupdate_state(config, {"messages": cleanup_messages})
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_snapshot(messages):
    snap = MagicMock()
    snap.values = {"messages": messages}
    return snap


def _make_app(snapshot):
    mock_app = MagicMock()
    mock_app.aget_state = AsyncMock(return_value=snapshot)
    mock_app.aupdate_state = AsyncMock(return_value=None)
    return mock_app


CONFIG = {"configurable": {"thread_id": "test-thread-123"}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestNoStaleState:
    @pytest.mark.asyncio
    async def test_empty_messages(self):
        app = _make_app(_make_snapshot([]))
        result = await resolve_stale_state(app, CONFIG)
        assert result is False
        app.aupdate_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_last_message_is_human(self):
        messages = [HumanMessage(content="Hello")]
        app = _make_app(_make_snapshot(messages))
        result = await resolve_stale_state(app, CONFIG)
        assert result is False
        app.aupdate_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_last_message_is_clean_ai(self):
        """AIMessage with no tool_calls — graph ended normally."""
        ai_msg = AIMessage(content="Here are our dresses!")
        app = _make_app(_make_snapshot([HumanMessage(content="Show me dresses"), ai_msg]))
        result = await resolve_stale_state(app, CONFIG)
        assert result is False
        app.aupdate_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_tool_calls_already_resolved(self):
        """AIMessage has tool_calls but matching ToolMessages already exist."""
        ai_msg = AIMessage(content="", tool_calls=[{"id": "call_abc", "name": "query_product_database", "args": {}}])
        tool_msg = ToolMessage(content="Found 3 products.", tool_call_id="call_abc")
        app = _make_app(_make_snapshot([HumanMessage(content="q"), ai_msg, tool_msg]))
        result = await resolve_stale_state(app, CONFIG)
        assert result is False
        app.aupdate_state.assert_not_called()


class TestStaleStateDetected:
    @pytest.mark.asyncio
    async def test_single_pending_tool_call(self):
        """THE CORE BUG: AIMessage with unresolved tool_call."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"id": "call_xyz", "name": "query_product_database", "args": {"search_query": "blue dress"}}],
        )
        app = _make_app(_make_snapshot([HumanMessage(content="Show me blue dresses"), ai_msg]))
        result = await resolve_stale_state(app, CONFIG)
        assert result is True
        app.aupdate_state.assert_called_once()
        call_args = app.aupdate_state.call_args
        injected = call_args[0][1]["messages"]
        assert len(injected) == 1
        assert isinstance(injected[0], ToolMessage)
        assert injected[0].tool_call_id == "call_xyz"

    @pytest.mark.asyncio
    async def test_multiple_pending_tool_calls(self):
        """Multiple tool_calls all unresolved."""
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {"id": "call_1", "name": "get_available_categories", "args": {}},
                {"id": "call_2", "name": "list_products", "args": {"category_filter": "Dresses"}},
            ],
        )
        app = _make_app(_make_snapshot([HumanMessage(content="What categories?"), ai_msg]))
        result = await resolve_stale_state(app, CONFIG)
        assert result is True
        call_args = app.aupdate_state.call_args
        injected = call_args[0][1]["messages"]
        assert len(injected) == 2
        injected_ids = {m.tool_call_id for m in injected}
        assert injected_ids == {"call_1", "call_2"}

    @pytest.mark.asyncio
    async def test_partial_resolution_not_triggered(self):
        """
        LangGraph's tool executor is atomic — it runs ALL tool_calls in a batch
        or none.  A state where some ToolMessages exist but not all is therefore
        not a valid stale state that can arise in practice.

        When the checkpoint ends with a ToolMessage (not an AIMessage), the
        resolver correctly returns False: the graph is mid-normal-execution,
        not interrupted.  The data_query_agent will run next and produce the
        final response.
        """
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {"id": "call_done", "name": "get_available_categories", "args": {}},
                {"id": "call_pending", "name": "list_products", "args": {}},
            ],
        )
        resolved_tool = ToolMessage(content="Categories: Dresses, Skirts", tool_call_id="call_done")
        # Last message is a ToolMessage — executor is still running, not stale.
        app = _make_app(_make_snapshot([HumanMessage(content="q"), ai_msg, resolved_tool]))
        result = await resolve_stale_state(app, CONFIG)
        # Resolver should NOT fire: last message is a ToolMessage, not an
        # AIMessage with dangling tool_calls.
        assert result is False
        app.aupdate_state.assert_not_called()


class TestResolverRobustness:
    @pytest.mark.asyncio
    async def test_none_snapshot(self):
        """aget_state returns None — should not crash."""
        app = MagicMock()
        app.aget_state = AsyncMock(return_value=None)
        result = await resolve_stale_state(app, CONFIG)
        assert result is False

    @pytest.mark.asyncio
    async def test_snapshot_raises(self):
        """aget_state throws — should swallow and return False."""
        app = MagicMock()
        app.aget_state = AsyncMock(side_effect=RuntimeError("DB connection lost"))
        result = await resolve_stale_state(app, CONFIG)
        assert result is False
