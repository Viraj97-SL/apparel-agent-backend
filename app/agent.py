import os
import sys
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import TypedDict, Annotated, Sequence
import operator

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
    trim_messages,
)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_tavily import TavilySearch

from langchain_mcp_adapters.client import MultiServerMCPClient

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.chat_with_rag import create_rag_chain
from app.sales_tools import (
    create_draft_order, confirm_order_details,
    view_cart, remove_from_cart, get_order_status,
)
from app.observability import configure_langsmith, run_metadata
from app.memory.episodic import episodic_memory
from app.memory.semantic import semantic_memory

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LangSmith — configure before anything else so all traces are captured
# ---------------------------------------------------------------------------
configure_langsmith()

# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found.")

# Model IDs — make configurable so upgrading to next Gemini release is a one-line env change
GEMINI_SUPERVISOR_MODEL = os.getenv("GEMINI_SUPERVISOR_MODEL", "gemini-2.5-pro")
GEMINI_WORKER_MODEL = os.getenv("GEMINI_WORKER_MODEL", "gemini-2.5-flash")

# ---------------------------------------------------------------------------
# 1. Enhanced Agent State (LangGraph v0.3)
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    # Plan-and-Execute: list of steps the planner generated
    plan: list[str]
    current_step: int
    # Reflexion: self-critique history; used to decide retry
    reflections: list[str]
    # Memory layer: injected context from long-term MongoDB store
    memory_context: str
    # Extracted user profile (size prefs, style, budget)
    user_profile: dict
    # Propagated through every node for tool injection + tracing
    thread_id: str
    next: str


# ---------------------------------------------------------------------------
# 2. LLM Setup
# ---------------------------------------------------------------------------
llm_supervisor = ChatGoogleGenerativeAI(
    model=GEMINI_SUPERVISOR_MODEL,
    temperature=0.1,
    google_api_key=GOOGLE_API_KEY,
    thinking_budget=8000,
)

llm_worker = ChatGoogleGenerativeAI(
    model=GEMINI_WORKER_MODEL,
    temperature=0.0,
    google_api_key=GOOGLE_API_KEY,
    thinking_budget=2000,
)

# Multimodal model for style advice (same Flash, different temp)
llm_vision = ChatGoogleGenerativeAI(
    model=GEMINI_WORKER_MODEL,
    temperature=0.3,
    google_api_key=GOOGLE_API_KEY,
)

# ---------------------------------------------------------------------------
# 3. RAG Agent
# ---------------------------------------------------------------------------
logger.info("Initializing Policy Agent (RAG)...")
rag_agent_chain = create_rag_chain()
logger.info("Policy Agent initialized.")

# ---------------------------------------------------------------------------
# 4. Tool initialisation — wrapped in an async factory to avoid module-level
#    asyncio.run() which makes the module un-importable in tests.
# ---------------------------------------------------------------------------
_tools_initialized = False
mcp_tools_list: list = []
sales_tools_list: list = []
mcp_client = None
data_tool_lookup: dict = {}
llm_query = None
llm_sales = None


@asynccontextmanager
async def tool_lifespan():
    """Initialise MCP + sales tools once; tear down MCP client on exit."""
    global _tools_initialized, mcp_tools_list, sales_tools_list, mcp_client
    global data_tool_lookup, llm_query, llm_sales

    if not _tools_initialized:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        env_vars = {**os.environ, "PYTHONPATH": project_root}

        mcp_client = MultiServerMCPClient(
            {
                "data_query": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": [os.path.join(current_dir, "data_query_server.py")],
                    "env": env_vars,
                }
            }
        )
        mcp_tools_list = await mcp_client.get_tools()
        sales_tools_list = [
            create_draft_order, confirm_order_details,
            view_cart, remove_from_cart, get_order_status,
        ]

        all_tools = mcp_tools_list + sales_tools_list
        data_tool_lookup = {t.name: t for t in all_tools}

        llm_query = llm_worker.bind_tools(mcp_tools_list)
        llm_sales = llm_worker.bind_tools(sales_tools_list)

        _tools_initialized = True
        logger.info("Data Query tools: %s", [t.name for t in mcp_tools_list])
        logger.info("Sales tools: %s", [t.name for t in sales_tools_list])

    yield

    if mcp_client:
        try:
            await mcp_client.__aexit__(None, None, None)
        except Exception:
            pass


async def ensure_tools():
    """Initialise tools if not already done (called at app startup)."""
    async with tool_lifespan():
        pass


# Tools are initialised in the FastAPI lifespan (server.py).
# Do NOT call asyncio.run() here — it creates a throwaway event loop that
# breaks the psycopg_pool AsyncConnectionPool used by the checkpointer.

# ---------------------------------------------------------------------------
# 5. Web Search Tool
# ---------------------------------------------------------------------------
web_search_tool = TavilySearch(max_results=4, name="tavily_general_search")
web_search_tools_list = [web_search_tool]
llm_with_web_search_tools = llm_worker.bind_tools(web_search_tools_list)
web_search_tool_lookup = {t.name: t for t in web_search_tools_list}

# ---------------------------------------------------------------------------
# 6. Supervisor (Router)
# ---------------------------------------------------------------------------
class RouteArgs(BaseModel):
    next_node: str = Field(
        ...,
        enum=[
            "memory_injector",
            "planner",
            "rag_agent",
            "data_query_agent",
            "sales_agent",
            "web_search_agent",
            "style_advisor",
            "visual_search",
            "occasion_planner",
            "reflection",
            "__end__",
        ],
    )


@tool("route", args_schema=RouteArgs)
def route(next_node: str) -> str:
    """Route to the next node."""
    return next_node


llm_with_route = llm_supervisor.bind_tools([route])

supervisor_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are the Supervisor Router for 'Pamorya', an elite Sri Lankan apparel store AI.

**OBJECTIVE:** Route to exactly one specialist. Never answer the user yourself.

**SPECIALISTS:**

1. **sales_agent** (HIGHEST PRIORITY)
   - User wants to buy, order, purchase, pay, or checkout
   - User provides or corrects size, quantity, name, address, or phone number
   - User asks to view cart, remove item, check order status, track delivery
   - Previous AI message asked for order details → any user reply goes here
   - User replies with ONLY a size ("M", "medium", "size 8") or number after browsing

2. **data_query_agent** (INVENTORY)
   - Browsing categories, checking stock/price/sizes, searching specific products
   - "What dresses do you have?", "Show me tops under LKR 3000", "Is [X] in stock?"

3. **rag_agent** (POLICY & GREETINGS)
   - Shipping times, return/exchange policy, store hours, brand info
   - Greetings: hi, hello, thanks, bye

4. **web_search_agent** (EXTERNAL TRENDS)
   - Fashion trends, what's trending, celebrity styles, colour forecasts
   - Any question about the outside fashion world, not Pamorya inventory

5. **style_advisor** (FASHION ADVICE)
   - User uploads image asking "does this suit me?" or "what goes with this?"
   - Explicit requests for outfit combinations, colour matching, styling tips
   - Image present but user wants styling tips/advice (NOT finding similar items)

6. **visual_search** (IMAGE SEARCH)
   - User uploads ANY image and wants to find similar items in the catalogue
   - "Find something like this", "Do you have anything similar?", "Match this outfit"
   - Image present + shopping/find/similar intent → visual_search (not style_advisor)

7. **occasion_planner** (EVENT OUTFIT PLANNING)
   - User has a specific event/occasion with a location, date, or budget constraint
   - "I need an outfit for...", "What should I wear to...", "Planning for a..."
   - Must involve an actual occasion, not just style browsing

8. **planner** (COMPLEX MULTI-STEP)
   - "Find me a full outfit for a wedding under LKR 15,000" (multi-item, multi-constraint)
   - Do NOT use for simple single-category queries

9. **reflection** (QUALITY CHECK)
   - Only if last AI response was clearly incomplete or missed the question
   - Use at most once per conversation turn

**ROUTING RULES (in order):**
1. Last ToolMessage contains "COD_SUCCESS" → `__end__` immediately
2. Last AIMessage has no tool_calls and is a complete answer → `__end__`
3. User provided name/address/phone number → `sales_agent`
4. Any buying/ordering intent OR size reply after browsing → `sales_agent`
5. Cart/order status request → `sales_agent`
6. Browsing/stock/price → `data_query_agent`
7. Policy/greeting → `rag_agent`
8. Trends/external fashion → `web_search_agent`
9. Image + shopping/find/similar intent → `visual_search`
10. Image + style/advice intent → `style_advisor`
11. Specific event with location/date/budget → `occasion_planner`
12. Complex multi-item outfit → `planner`

Call the 'route' tool with `next_node`.
""",
        ),
        MessagesPlaceholder(variable_name="messages"),
    ]
)


async def supervisor_router(state: AgentState) -> dict:
    logger.info("--- Supervisor Routing ---")
    messages = list(state["messages"])
    last_message = messages[-1]

    # Fast-path: COD confirmed → done
    if isinstance(last_message, ToolMessage) and "COD_SUCCESS" in (last_message.content or ""):
        logger.info("Supervisor: COD_SUCCESS tool result → __end__")
        return {"next": "__end__"}

    if isinstance(last_message, AIMessage) and not last_message.tool_calls:
        logger.info("Supervisor: clean AI response → __end__")
        return {"next": "__end__"}

    ai_response = await (supervisor_prompt | llm_with_route).ainvoke({"messages": messages})

    next_node = "__end__"
    if ai_response.tool_calls:
        next_node = ai_response.tool_calls[0]["args"].get("next_node", "__end__")

    logger.info("Supervisor → %s", next_node)
    return {"next": next_node}


# ---------------------------------------------------------------------------
# 7. Memory Injector Node (Layer 3 — populated fully in Sprint 2)
# ---------------------------------------------------------------------------
async def memory_injector_node(state: AgentState) -> dict:
    """
    Layer 1: trim working memory to 8k tokens.
    Layer 2: load episodic session context from Redis.
    Layer 3: load semantic long-term facts from MongoDB Atlas.
    Injects combined context string into state for downstream agents.
    """
    thread_id = state.get("thread_id", "")

    # Layer 1 — trim working memory
    trimmed = trim_messages(
        list(state["messages"]),
        max_tokens=8000,
        strategy="last",
        token_counter=llm_worker,
        include_system=True,
        allow_partial=False,
    )
    trimmed_delta = trimmed if trimmed != list(state["messages"]) else []

    # Layer 2 — episodic (Redis)
    session_ctx = {}
    if thread_id:
        try:
            session_ctx = await asyncio.to_thread(episodic_memory.get_session_context, thread_id)
        except Exception as e:
            logger.warning("Episodic load failed: %s", e)

    # Layer 3 — semantic (MongoDB)
    semantic_ctx = ""
    user_profile = state.get("user_profile", {})
    if thread_id:
        try:
            semantic_ctx = await asyncio.to_thread(semantic_memory.format_as_context, thread_id)
        except Exception as e:
            logger.warning("Semantic load failed: %s", e)

    parts = []
    if semantic_ctx:
        parts.append(f"Known user preferences:\n{semantic_ctx}")
    if session_ctx.get("recent_products"):
        parts.append(f"Recently viewed: {', '.join(session_ctx['recent_products'])}")

    memory_context = "\n\n".join(parts) if parts else ""

    return {
        "messages": trimmed_delta,
        "memory_context": memory_context,
        "user_profile": user_profile,
    }


# ---------------------------------------------------------------------------
# 8. Planner Node (Plan-and-Execute pattern)
# ---------------------------------------------------------------------------
PLANNER_PROMPT = """You are a planning assistant for Pamorya, a Sri Lankan fashion store.

The user has a complex request that needs multiple steps. Break it down into 2–4 clear, ordered steps.
Each step should be a single, actionable instruction for a specialist agent.

Return ONLY a numbered list of steps. No preamble, no explanation.

Example:
1. Search inventory for wedding dresses under LKR 8000
2. Search inventory for matching accessories (earrings, necklace)
3. Check if the top 2 dress picks are in stock in size M
4. Summarise a complete outfit recommendation with total price

User request: {query}
"""


async def planner_node(state: AgentState) -> dict:
    """Decomposes complex multi-step queries into an execution plan."""
    logger.info("--- Planner Node ---")
    last_human = next(
        (m for m in reversed(list(state["messages"])) if isinstance(m, HumanMessage)),
        None,
    )
    query = last_human.content if last_human else ""

    plan_response = await llm_supervisor.ainvoke(
        PLANNER_PROMPT.format(query=query)
    )
    plan_text = plan_response.content if isinstance(plan_response.content, str) else ""
    steps = [
        line.strip()
        for line in plan_text.split("\n")
        if line.strip() and line.strip()[0].isdigit()
    ]

    logger.info("Plan generated: %d steps", len(steps))
    return {
        "plan": steps,
        "current_step": 0,
        "messages": [AIMessage(content=f"I'll handle this step by step:\n{plan_text}")],
    }


# ---------------------------------------------------------------------------
# 9. RAG Agent Node
# ---------------------------------------------------------------------------
async def rag_agent_node(state: AgentState) -> dict:
    logger.info("--- Policy Agent (RAG) ---")
    messages = list(state["messages"])
    last_human = next(
        (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
    )
    query = last_human.content if last_human else ""

    memory_ctx = state.get("memory_context", "")
    enriched_query = f"{query}\n\n[User context: {memory_ctx}]" if memory_ctx else query

    response_str = await rag_agent_chain.ainvoke(enriched_query)
    return {"messages": [AIMessage(content=response_str)]}


# ---------------------------------------------------------------------------
# 10. Data Query Agent Node
# ---------------------------------------------------------------------------
DATA_QUERY_SYSTEM = """You are an Inventory Assistant for 'Pamorya', a premium Sri Lankan apparel store.

**YOUR TOOLS:**
1. `get_available_categories()` — for "What do you sell?" / "What categories do you have?"
2. `list_products(category_filter="...")` — for browsing by category. Map user terms:
   - dresses / frocks → 'Dresses'
   - skirts → 'Skirts'
   - pants / trousers → 'Pants & Trousers'
   - tops / blouses / shirts → 'Tops & Blouses'
   - sets / co-ords / matching / coordinates → 'Sets & Co-ords'
   - jumpers / knits / knitwear → 'Jumpers & Knits'
3. `query_product_database(search_query="...")` — for specific products, colours, or style keywords.

**RULES:**
- Always include `<img src="...">` tags from tool output verbatim — don't remove them.
- Never invent products. Use only what tools return.
- If "No products found": suggest a related category or broader search.
- After showing products, always end with:
  "💬 To buy: just tell me which one you'd like and your size (e.g. 'I'll take the [name] in M')."

**FOLLOW-UP QUERIES:**
- "Show me more" → call the same tool again with offset or different filter
- "In red / blue / any colour" → use `query_product_database(search_query="red dresses")`
- "Cheaper" / "Under LKR X" → note the price filter and mention it when showing products
{memory_section}
"""


async def data_query_agent_node(state: AgentState) -> dict:
    logger.info("--- Data Query Agent ---")
    memory_ctx = state.get("memory_context", "")
    memory_section = f"\n**USER PREFERENCES (from memory):** {memory_ctx}" if memory_ctx else ""
    system = DATA_QUERY_SYSTEM.format(memory_section=memory_section)
    messages = [HumanMessage(content=system)] + list(state["messages"])
    ai_response = await llm_query.ainvoke(messages)
    return {"messages": [ai_response]}


# ---------------------------------------------------------------------------
# 11. Sales Agent Node
# ---------------------------------------------------------------------------
SALES_SYSTEM = """You are the Sales Agent for Pamorya, a premium Sri Lankan fashion store. Your job is to close orders warmly and efficiently.

**TOOLS AVAILABLE:**
- `create_draft_order(product_name, size, quantity, thread_id)` — adds item to cart
- `view_cart(thread_id)` — shows current cart
- `remove_from_cart(product_name, thread_id)` — removes item
- `confirm_order_details(customer_name, address, phone, thread_id)` — confirms COD order
- `get_order_status(order_number, thread_id)` — checks existing order status

**STEP-BY-STEP PROCESS:**

1. **Identify the product**: Look at the recent conversation. The user likely mentioned a product name. If unclear, ask once: "Which item would you like?"

2. **Get size and quantity**: If the user just said a size (e.g. "M", "medium", "size 10"), pair it with the product from context. Default quantity is 1 unless stated.

3. **Call create_draft_order**: Once you have product + size. Show the total and delivery estimate from the response.

4. **Handle OUT_OF_STOCK**: If returned, apologise and list the available sizes clearly.

5. **Collect delivery details**: Ask for all three in ONE message:
   "To confirm your order, I just need:
   1. Your full name
   2. Delivery address (include city/district)
   3. Phone number (for delivery coordination)"

6. **Handle partial info**: If the user only provided some details, ask ONLY for the missing ones. Never ask for details already given.

7. **Call confirm_order_details**: When you have name + address + phone.

8. **On COD_SUCCESS**: Read the receipt JSON and relay warmly:
   - Order number
   - Items and total
   - Delivery date estimate
   - "We'll WhatsApp you at [phone] when dispatched"

**EDGE CASES:**
- User wants to change item → `remove_from_cart` → `create_draft_order` for the new item
- User asks "how much total?" → `view_cart`
- User asks "where is my order?" → `get_order_status`
- User changes address mid-flow → note it and use the new one in `confirm_order_details`

**TONE:** Warm, professional, concise. Handle Sri Lankan cities/addresses naturally (Colombo, Kandy, Galle, etc.).
"""


async def sales_agent_node(state: AgentState) -> dict:
    logger.info("--- Sales Agent ---")
    messages = [HumanMessage(content=SALES_SYSTEM)] + list(state["messages"])
    return {"messages": [await llm_sales.ainvoke(messages)]}


# ---------------------------------------------------------------------------
# 12. Tool Executor Node (shared by data_query + sales)
# ---------------------------------------------------------------------------
async def data_query_tool_executor_node(state: AgentState, config: RunnableConfig) -> dict:
    logger.info("--- Tool Executor ---")
    messages = list(state["messages"])
    last_message = messages[-1]

    if not last_message.tool_calls:
        return {"messages": []}

    thread_id = (
        config.get("configurable", {}).get("thread_id", "guest_user")
        if config
        else state.get("thread_id", "guest_user")
    )

    tasks = []
    for tc in last_message.tool_calls:
        name = tc["name"]
        args = dict(tc["args"])
        if name in {"create_draft_order", "confirm_order_details", "view_cart", "remove_from_cart"}:
            args["thread_id"] = thread_id
        logger.info(" -> tool=%s args=%s", name, args)
        t = data_tool_lookup.get(name)
        if not t:
            tasks.append((tc["id"], None, f"Error: Tool '{name}' not found."))
        else:
            tasks.append((tc["id"], t, args))

    tool_messages = []
    for tool_id, t, args_or_err in tasks:
        if t is None:
            tool_messages.append(ToolMessage(content=str(args_or_err), tool_call_id=tool_id))
            continue
        try:
            if hasattr(t, "ainvoke"):
                result = await t.ainvoke(args_or_err)
            else:
                result = await asyncio.to_thread(t.invoke, args_or_err)
        except Exception as e:
            result = f"Tool error: {e}"
        tool_messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))

    logger.info("Tool results: %s", [m.content[:80] for m in tool_messages])
    return {"messages": tool_messages}


# ---------------------------------------------------------------------------
# 13. Web Search Agent + Executor
# ---------------------------------------------------------------------------
WEB_SEARCH_SYSTEM = """You are a fashion trend researcher for Pamorya. Use `tavily_general_search` to find current, relevant information.
Focus on: current fashion trends, celebrity styles, colour palettes, styling tips.
Always relate findings back to what Pamorya might offer."""


async def web_search_agent_node(state: AgentState) -> dict:
    logger.info("--- Web Search Agent (Gemini Grounding) ---")
    messages = list(state["messages"])
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    query = last_human.content if last_human else "fashion trends"

    try:
        from google import genai as _genai
        from google.genai import types as _genai_types

        _client = _genai.Client(api_key=GOOGLE_API_KEY)
        grounded_prompt = (
            f"You are a fashion trend researcher for Pamorya, a premium Sri Lankan apparel store. "
            f"Use Google Search to find current, relevant information about: {query}\n"
            f"Focus on: current fashion trends, celebrity styles, colour palettes, styling tips. "
            f"Always relate findings to what Pamorya might offer (dresses, tops, skirts, sets, knitwear)."
        )
        response = await asyncio.to_thread(
            _client.models.generate_content,
            model=GEMINI_WORKER_MODEL,
            contents=grounded_prompt,
            config=_genai_types.GenerateContentConfig(
                tools=[_genai_types.Tool(google_search=_genai_types.GoogleSearch())],
            ),
        )
        answer = response.text
        logger.info("Gemini grounding succeeded for web search")
        return {"messages": [AIMessage(content=answer)]}
    except Exception as e:
        logger.warning("Gemini grounding failed (%s) — falling back to Tavily", e)
        full_messages = [HumanMessage(content=WEB_SEARCH_SYSTEM)] + messages
        ai_response = await llm_with_web_search_tools.ainvoke(full_messages)
        return {"messages": [ai_response]}


async def web_search_tool_executor_node(state: AgentState) -> dict:
    logger.info("--- Web Search Executor ---")
    messages = list(state["messages"])
    last_message = messages[-1]
    tool_messages = []

    if not last_message.tool_calls:
        return {"messages": []}

    for tc in last_message.tool_calls:
        t = web_search_tool_lookup.get(tc["name"])
        if t:
            try:
                result = await asyncio.to_thread(t.invoke, tc["args"])
                # Format as clean markdown so the web_search_agent receives readable text
                if isinstance(result, list):
                    formatted = "\n\n".join(
                        f"**{r.get('title', '')}**\n{r.get('content', '')}\nSource: {r.get('url', '')}"
                        for r in result
                        if isinstance(r, dict)
                    )
                    content = formatted if formatted else str(result)
                else:
                    content = str(result)
            except Exception as e:
                logger.warning("Web search tool error: %s", e)
                content = f"Search unavailable: {e}"
            tool_messages.append(ToolMessage(content=content, tool_call_id=tc["id"]))

    return {"messages": tool_messages}


# ---------------------------------------------------------------------------
# 14. Style Advisor Node (Multimodal — Gemini Vision)
# ---------------------------------------------------------------------------
STYLE_ADVISOR_SYSTEM = """You are Pamorya's personal style advisor. You specialise in Sri Lankan fashion and contemporary trends.

When analysing outfit images:
- Identify key garment types, colours, and patterns
- Suggest Pamorya products that complement the user's existing wardrobe
- Give specific, actionable styling advice
- Consider the local climate (tropical) and cultural context

If no image is provided, give advice based on the description.
"""


async def style_advisor_node(state: AgentState) -> dict:
    """Multimodal style advice node. Handles both image+text and text-only queries."""
    logger.info("--- Style Advisor ---")
    messages = list(state["messages"])

    memory_ctx = state.get("memory_context", "")
    system_with_context = STYLE_ADVISOR_SYSTEM
    if memory_ctx:
        system_with_context += f"\n\n**User's known preferences:** {memory_ctx}"

    full_messages = [HumanMessage(content=system_with_context)] + messages
    response = await llm_vision.ainvoke(full_messages)
    return {"messages": [response]}


# ---------------------------------------------------------------------------
# Shared helper — MCP tools return list[{"type":"text","text":"..."}] or str
# ---------------------------------------------------------------------------
def _extract_tool_text(result) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return "\n".join(
            item.get("text", str(item)) if isinstance(item, dict) else str(item)
            for item in result
        )
    if isinstance(result, dict):
        return result.get("text", str(result))
    return str(result)


# ---------------------------------------------------------------------------
# 14b. Visual Search Node (Image → catalogue matching)
# ---------------------------------------------------------------------------
VISUAL_SEARCH_PROMPT = """You are Pamorya's visual style search engine. Analyze the uploaded fashion image.

Extract EXACTLY these attributes as a JSON object:
{
  "garment_type": "e.g. midi dress / crop top / wide-leg trousers",
  "primary_colour": "e.g. dusty rose / navy blue",
  "secondary_colours": ["e.g. white", "cream"],
  "style_keywords": ["e.g. cottagecore", "floral", "puff sleeve", "relaxed fit"],
  "occasion": "e.g. casual / formal / beach / office"
}

Return ONLY the JSON. No prose."""


async def visual_search_node(state: AgentState) -> dict:
    """Analyzes an uploaded image with Gemini vision then searches the product catalogue."""
    import re as _re
    import json as _json

    logger.info("--- Visual Search Node ---")
    messages = list(state["messages"])

    # Sync invoke — prevents this intermediate extraction from appearing in the SSE stream
    vision_messages = [HumanMessage(content=VISUAL_SEARCH_PROMPT)] + messages
    vision_response = await asyncio.to_thread(llm_vision.invoke, vision_messages)
    vision_text = vision_response.content if isinstance(vision_response.content, str) else ""

    attrs = {}
    json_match = _re.search(r"\{.*\}", vision_text, _re.DOTALL)
    if json_match:
        try:
            attrs = _json.loads(json_match.group())
        except Exception:
            attrs = {}

    garment_type = attrs.get("garment_type", "dress")
    primary_colour = attrs.get("primary_colour", "")
    style_keywords = attrs.get("style_keywords", [])

    search_query = f"{garment_type} {primary_colour} {' '.join(style_keywords[:2])}".strip()

    product_results = ""
    q_tool = data_tool_lookup.get("query_product_database")
    if q_tool:
        try:
            if hasattr(q_tool, "ainvoke"):
                raw = await q_tool.ainvoke({"search_query": search_query})
            else:
                raw = await asyncio.to_thread(q_tool.invoke, {"search_query": search_query})
            product_results = _extract_tool_text(raw)
        except Exception as e:
            logger.warning("Visual search product lookup failed: %s", e)

    style_summary = f"Detected: {garment_type}" + (f" in {primary_colour}" if primary_colour else "")

    if product_results:
        response_text = (
            f"**Style detected:** {style_summary}\n\n"
            f"**Similar items from Pamorya:**\n{product_results}"
        )
    else:
        response_text = (
            f"**Style detected:** {style_summary}\n\n"
            "I wasn't able to search the catalogue right now — please try again in a moment."
        )

    return {"messages": [AIMessage(content=response_text)]}


# ---------------------------------------------------------------------------
# 14c. Occasion Planner Node (Event-based outfit planning)
# ---------------------------------------------------------------------------
OCCASION_EXTRACT_PROMPT = """Extract occasion details from this message as JSON:
{{
  "occasion_type": "e.g. beach wedding / office party / casual day out",
  "venue_or_location": "e.g. Galle / Colombo / outdoor",
  "date_or_timing": "e.g. next Saturday / this weekend / unknown",
  "budget_lkr": 0,
  "style_preference": "e.g. elegant / casual / beach-appropriate"
}}
Return ONLY the JSON.

Message: {message}"""


async def occasion_planner_node(state: AgentState) -> dict:
    """Plans a complete outfit for a specific occasion using parallel product searches."""
    import re as _re
    import json as _json

    logger.info("--- Occasion Planner Node ---")
    messages = list(state["messages"])
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    user_message = last_human.content if last_human else ""

    # Sync invoke — prevents JSON extraction from leaking into the SSE stream
    extract_response = await asyncio.to_thread(
        llm_worker.invoke, OCCASION_EXTRACT_PROMPT.format(message=user_message)
    )
    extract_text = extract_response.content if isinstance(extract_response.content, str) else ""
    occasion = {}
    json_match = _re.search(r"\{.*\}", extract_text, _re.DOTALL)
    if json_match:
        try:
            occasion = _json.loads(json_match.group())
        except Exception:
            occasion = {}

    occasion_type = occasion.get("occasion_type", "special occasion")
    venue = occasion.get("venue_or_location", "")
    date_or_timing = occasion.get("date_or_timing", "unknown")
    budget_lkr = occasion.get("budget_lkr", 0)
    style_preference = occasion.get("style_preference", "elegant")

    dress_query = f"{occasion_type} {style_preference} dress"
    accessories_query = f"accessories earrings necklace {occasion_type}"
    shoes_query = f"shoes sandals heels {style_preference}"

    q_tool = data_tool_lookup.get("query_product_database")
    dress_r = acc_r = shoes_r = ""
    if q_tool:
        async def _search(query_str: str) -> str:
            try:
                if hasattr(q_tool, "ainvoke"):
                    raw = await asyncio.wait_for(q_tool.ainvoke({"search_query": query_str}), timeout=15)
                else:
                    raw = await asyncio.wait_for(
                        asyncio.to_thread(q_tool.invoke, {"search_query": query_str}), timeout=15
                    )
                return _extract_tool_text(raw)
            except Exception as e:
                logger.warning("Occasion planner search failed for '%s': %s", query_str, e)
                return ""

        try:
            dress_r, acc_r, shoes_r = await asyncio.gather(
                _search(dress_query),
                _search(accessories_query),
                _search(shoes_query),
            )
        except Exception as e:
            logger.warning("Occasion planner parallel search failed: %s", e)
            return {"messages": [AIMessage(content="Our product catalogue is temporarily unavailable. Please try again.")]}
    else:
        return {"messages": [AIMessage(content="Our product catalogue is temporarily unavailable. Please try again.")]}

    weather_note = ""
    if venue and venue.lower() not in ("unknown", "outdoor", ""):
        try:
            weather_result = await asyncio.wait_for(
                asyncio.to_thread(web_search_tool.invoke, {"query": f"weather {venue} {date_or_timing}"}),
                timeout=8,
            )
            weather_note = _extract_tool_text(weather_result)[:200] if weather_result else ""
        except Exception as e:
            logger.warning("Weather lookup failed (non-fatal): %s", e)

    budget_str = f"LKR {budget_lkr}" if budget_lkr else "not specified"
    venue_str = venue or "not specified"
    assemble_prompt = f"""You are Pamorya's personal stylist. Build a complete outfit recommendation.

Occasion: {occasion_type}
Location: {venue_str}
Timing: {date_or_timing}
Budget: {budget_str}
Style: {style_preference}
Weather info: {weather_note or 'not available'}

Available dresses/tops:
{dress_r[:600]}

Available accessories:
{acc_r[:400]}

Available shoes:
{shoes_r[:400]}

Write a complete outfit recommendation using this EXACT format:
**Your {occasion_type} outfit plan** ✨

**The Look:**
[2-3 sentence style description]

**1. Dress/Top:** [product name + price from dress results]
**2. Accessories:** [product from accessories results]
**3. Shoes:** [product from shoes results]

**Total:** ~LKR [estimated sum]

[Weather note if available]

💬 Ready to order the complete look? Just say "Yes, add all to cart" and I'll handle it!
"""
    final_response = await llm_supervisor.ainvoke(assemble_prompt)
    response_text = final_response.content if isinstance(final_response.content, str) else str(final_response)
    return {"messages": [AIMessage(content=response_text)]}


# ---------------------------------------------------------------------------
# 15. Reflection Node (Reflexion pattern)
# ---------------------------------------------------------------------------
REFLECTION_PROMPT = """You are a quality reviewer for an AI fashion assistant.

Review the last response and decide: is it good enough to send to the customer?

GOOD: specific, helpful, answers the question, appropriate length.
NEEDS_RETRY: vague, too short, missed the question, factually wrong.

Last response: {last_response}

Reply with exactly one word: GOOD or NEEDS_RETRY.
Then on a new line, if NEEDS_RETRY, explain in one sentence what was wrong.
"""


async def reflection_node(state: AgentState) -> dict:
    """Self-critique the last AI response. If poor quality, flag for retry."""
    logger.info("--- Reflection Node ---")
    messages = list(state["messages"])
    last_ai = next(
        (m for m in reversed(messages) if isinstance(m, AIMessage) and m.content),
        None,
    )
    if not last_ai:
        return {"next": "__end__"}

    review = await llm_worker.ainvoke(
        REFLECTION_PROMPT.format(last_response=str(last_ai.content)[:500])
    )
    review_text = review.content if isinstance(review.content, str) else ""
    verdict = review_text.strip().split("\n")[0].strip().upper()

    reflections = list(state.get("reflections", []))
    reflections.append(review_text)

    # Only retry once to avoid infinite loops
    if verdict == "NEEDS_RETRY" and len(reflections) <= 1:
        logger.info("Reflection: NEEDS_RETRY — looping back to supervisor")
        return {"reflections": reflections, "next": "supervisor"}

    logger.info("Reflection: %s", verdict)
    return {"reflections": reflections, "next": "__end__"}


# ---------------------------------------------------------------------------
# 16. Memory Writer Node (Layer 3 — wired to MongoDB in Sprint 2)
# ---------------------------------------------------------------------------
MEMORY_EXTRACT_PROMPT = """Extract any user facts worth remembering from this conversation snippet.
Facts to extract: preferred sizes, style preferences, budget range, favourite colours, past purchases.

Conversation:
{snippet}

Return a JSON object with keys matching the fact types above. Only include facts that are explicitly stated.
If nothing notable, return an empty object {{}}.
"""


async def memory_writer_node(state: AgentState) -> dict:
    """
    Extracts user facts from recent messages and persists them:
    - Layer 3 (MongoDB): style preferences, sizes, budget, past purchases
    - Layer 2 (Redis): recently viewed products (session-scoped)
    Non-blocking — failures are logged and swallowed.
    """
    thread_id = state.get("thread_id", "")
    if not thread_id:
        return {}

    messages = list(state["messages"])
    recent = messages[-4:] if len(messages) >= 4 else messages
    snippet = "\n".join(
        f"{'User' if isinstance(m, HumanMessage) else 'AI'}: {str(m.content)[:200]}"
        for m in recent
    )

    # Extract and persist facts asynchronously
    async def _persist():
        try:
            response = await llm_worker.ainvoke(
                MEMORY_EXTRACT_PROMPT.format(snippet=snippet)
            )
            raw = response.content if isinstance(response.content, str) else ""

            import re as _re
            json_match = _re.search(r"\{.*\}", raw, _re.DOTALL)
            if not json_match:
                return
            facts: dict = __import__("json").loads(json_match.group())

            CATEGORY_MAP = {
                "preferred_sizes": "preferences",
                "style_preferences": "preferences",
                "budget_range": "preferences",
                "favourite_colours": "preferences",
                "past_purchases": "history",
            }
            for key, value in facts.items():
                if value:
                    category = CATEGORY_MAP.get(key, "preferences")
                    await asyncio.to_thread(
                        semantic_memory.put,
                        thread_id, category, key, str(value),
                    )
            logger.info("Semantic memory updated for thread %s", thread_id)
        except Exception as e:
            logger.warning("Memory writer failed (non-fatal): %s", e)

    asyncio.create_task(_persist())
    return {}


# ---------------------------------------------------------------------------
# 17. Deep Research Subgraph
# ---------------------------------------------------------------------------
class ResearchState(TypedDict):
    query: str
    search_results: list[str]
    synthesis: str
    hops: int


async def research_search_node(state: ResearchState) -> dict:
    """Single hop of web search."""
    results = await asyncio.to_thread(web_search_tool.invoke, {"query": state["query"]})
    current = list(state.get("search_results", []))
    current.append(str(results))
    return {"search_results": current, "hops": state.get("hops", 0) + 1}


async def research_synthesize_node(state: ResearchState) -> dict:
    """Synthesise all search results into a coherent answer."""
    combined = "\n\n---\n\n".join(state.get("search_results", []))
    prompt = f"""Synthesise these search results into a concise, useful answer about fashion/style.
Focus on practical insights relevant to a Sri Lankan fashion shopper.

Search results:
{combined[:3000]}

Synthesis:"""
    response = await llm_worker.ainvoke(prompt)
    return {"synthesis": response.content if isinstance(response.content, str) else ""}


def should_continue_research(state: ResearchState) -> str:
    if state.get("hops", 0) >= 2:
        return "synthesize"
    results = state.get("search_results", [])
    if results and len(results[-1]) > 200:
        return "synthesize"
    return "search"


research_graph = StateGraph(ResearchState)
research_graph.add_node("search", research_search_node)
research_graph.add_node("synthesize", research_synthesize_node)
research_graph.set_entry_point("search")
research_graph.add_conditional_edges("search", should_continue_research, {
    "search": "search",
    "synthesize": "synthesize",
})
research_graph.add_edge("synthesize", END)
compiled_research_graph = research_graph.compile()


async def deep_research_node(state: AgentState) -> dict:
    """Multi-hop deep research node — wraps the research subgraph."""
    logger.info("--- Deep Research Node ---")
    last_human = next(
        (m for m in reversed(list(state["messages"])) if isinstance(m, HumanMessage)),
        None,
    )
    query = last_human.content if last_human else "fashion trends"

    result = await compiled_research_graph.ainvoke({"query": query, "search_results": [], "hops": 0})
    synthesis = result.get("synthesis", "No results found.")
    return {"messages": [AIMessage(content=synthesis)]}


# ---------------------------------------------------------------------------
# 18. Conditional Edge Helpers
# ---------------------------------------------------------------------------
def check_for_tool_calls(state: AgentState) -> str:
    last = state["messages"][-1]
    return "continue_with_tools" if getattr(last, "tool_calls", None) else "supervisor"


def reflection_edge(state: AgentState) -> str:
    return state.get("next", "__end__")


# ---------------------------------------------------------------------------
# 19. Build the Graph
# ---------------------------------------------------------------------------
logger.info("Building LangGraph v0.3 graph...")

workflow = StateGraph(AgentState)

workflow.add_node("supervisor", supervisor_router)
workflow.add_node("memory_injector", memory_injector_node)
workflow.add_node("planner", planner_node)
workflow.add_node("rag_agent", rag_agent_node)
workflow.add_node("data_query_agent", data_query_agent_node)
workflow.add_node("sales_agent", sales_agent_node)
workflow.add_node("data_query_tool_executor", data_query_tool_executor_node)
workflow.add_node("sales_tool_executor", data_query_tool_executor_node)
workflow.add_node("web_search_agent", web_search_agent_node)
workflow.add_node("web_search_tool_executor", web_search_tool_executor_node)
workflow.add_node("style_advisor", style_advisor_node)
workflow.add_node("visual_search", visual_search_node)
workflow.add_node("occasion_planner", occasion_planner_node)
workflow.add_node("reflection", reflection_node)
workflow.add_node("memory_writer", memory_writer_node)
workflow.add_node("deep_research", deep_research_node)

# Entry: memory injection first, then supervisor routing
workflow.set_entry_point("memory_injector")
workflow.add_edge("memory_injector", "supervisor")

# Supervisor routes to specialists
workflow.add_conditional_edges("supervisor", lambda s: s["next"])

# Each agent: check for tool calls or return to supervisor
workflow.add_conditional_edges(
    "rag_agent", check_for_tool_calls,
    {"continue_with_tools": "supervisor", "supervisor": "supervisor"},
)
workflow.add_conditional_edges(
    "data_query_agent", check_for_tool_calls,
    {"continue_with_tools": "data_query_tool_executor", "supervisor": "supervisor"},
)
workflow.add_conditional_edges(
    "sales_agent", check_for_tool_calls,
    {"continue_with_tools": "sales_tool_executor", "supervisor": "supervisor"},
)
workflow.add_conditional_edges(
    "web_search_agent", check_for_tool_calls,
    {"continue_with_tools": "web_search_tool_executor", "supervisor": "supervisor"},
)
workflow.add_conditional_edges(
    "style_advisor", check_for_tool_calls,
    {"continue_with_tools": "supervisor", "supervisor": "supervisor"},
)
workflow.add_edge("visual_search", "memory_writer")
workflow.add_edge("occasion_planner", "memory_writer")

# Executors return to their parent agents
workflow.add_edge("data_query_tool_executor", "data_query_agent")
workflow.add_edge("sales_tool_executor", "sales_agent")
workflow.add_edge("web_search_tool_executor", "web_search_agent")

# Planner → supervisor (to start executing the plan)
workflow.add_edge("planner", "supervisor")

# Deep research → memory_writer → end
workflow.add_edge("deep_research", "memory_writer")
workflow.add_edge("memory_writer", END)

# Reflection can loop back to supervisor or end
workflow.add_conditional_edges("reflection", reflection_edge, {
    "supervisor": "supervisor",
    "__end__": END,
})

# ---------------------------------------------------------------------------
# 20. Compile with Checkpointer
# ---------------------------------------------------------------------------
async def create_memory() -> object:
    """
    Build the LangGraph checkpointer.
    Production: AsyncPostgresSaver (Railway PostgreSQL).
    Local dev: AsyncSqliteSaver fallback.
    """
    db_url = os.getenv("DATABASE_URL", "")

    if db_url:
        try:
            from psycopg_pool import AsyncConnectionPool
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            pg_url = db_url.replace("postgres://", "postgresql://")
            pool = AsyncConnectionPool(
                conninfo=pg_url,
                min_size=2,
                max_size=10,
                open=False,
                kwargs={"autocommit": True, "prepare_threshold": 0},
            )
            await pool.open()
            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()
            logger.info("Checkpointer: PostgreSQL (Railway)")
            return checkpointer
        except Exception as exc:
            logger.warning("PostgreSQL checkpointer failed (%s) — falling back to SQLite", exc)

    conn = await aiosqlite.connect("checkpoints.db")
    logger.info("Checkpointer: SQLite (local dev)")
    return AsyncSqliteSaver(conn=conn)


# Graph is compiled in server.py lifespan after the event loop is running.
# `workflow` is exported so server.py can call workflow.compile(checkpointer=memory).
