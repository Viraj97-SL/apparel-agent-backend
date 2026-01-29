import os
import sys
import asyncio
from dotenv import load_dotenv
from typing import TypedDict, Annotated, Sequence
import operator
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools.tavily_search import TavilySearchResults
# MCP Adapter Imports
from langchain_mcp_adapters.client import MultiServerMCPClient
# --- Our Custom Imports ---
from app.chat_with_rag import create_rag_chain
# --- NEW IMPORT: Sales Tools ---
from app.sales_tools import create_draft_order, confirm_order_details

# --- LangGraph Imports ---
from langgraph.graph import StateGraph, END
# Use AsyncSqliteSaver for async support
import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
# For supervisor tool-calling
from langchain_core.tools import tool
# 🟢 NEW IMPORT: Required for threading
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
import nest_asyncio

# Apply the patch for nested event loops
nest_asyncio.apply()

# Load environment variables
load_dotenv()

# --- 1. CRITICAL: Capture and Validate API Keys ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not GOOGLE_API_KEY:
    print("❌ CRITICAL ERROR: GOOGLE_API_KEY is missing!")
    raise ValueError("GOOGLE_API_KEY not found.")


# --- 2. Define Agent State ---
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next: str


# --- 3. Define Agents and Tools ---

# --- HYBRID BRAIN SETUP ---
# 1. The "Big Brain" (Supervisor)
llm_supervisor = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0.2,
    google_api_key=GOOGLE_API_KEY
)

# 2. The "Fast Worker" (Data / Web / Tool Agents)
llm_worker = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0.0,
    google_api_key=GOOGLE_API_KEY
)

# --- Agent 1: The Policy Agent (RAG) ---
print("Initializing Policy Agent (RAG)...")
rag_agent_chain = create_rag_chain()
print("Policy Agent initialized.")

# --- Agent 2: The Data Query & Sales Agents ---
print("Initializing Data & Sales Tools...")
python_path = sys.executable


async def initialize_tools():
    # 1. Setup MCP (Data Query Tools)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    env_vars = dict(os.environ)
    env_vars["PYTHONPATH"] = project_root

    client = MultiServerMCPClient(
        {
            "data_query": {
                "transport": "stdio",
                "command": python_path,
                "args": [os.path.join(current_dir, "data_query_server.py")],
                "env": env_vars
            }
        }
    )
    mcp_tools = await client.get_tools()

    # 2. Setup Local Sales Tools (Imported manually)
    local_sales_tools = [create_draft_order, confirm_order_details]

    return mcp_tools, local_sales_tools, client


# Initialize tools
mcp_tools_list, sales_tools_list, mcp_client = asyncio.run(initialize_tools())

# Create a Master Lookup for the Executor Node
# We merge both lists so the executor can find tools by name
all_tools = mcp_tools_list + sales_tools_list
data_tool_lookup = {t.name: t for t in all_tools}

# Bind specific tools to specific LLM instances
llm_query = llm_worker.bind_tools(mcp_tools_list)
llm_sales = llm_worker.bind_tools(sales_tools_list)

print(f"Data Query tools initialized: {[t.name for t in mcp_tools_list]}")
print(f"Sales Agent tools initialized: {[t.name for t in sales_tools_list]}")

# --- Agent 3: The Web Search Agent ---
print("Initializing Web Search Tool...")
web_search_tool = TavilySearchResults(max_results=3, name="tavily_general_search")
web_search_tools_list = [web_search_tool]
llm_with_web_search_tools = llm_worker.bind_tools(web_search_tools_list)
web_search_tool_lookup = {t.name: t for t in web_search_tools_list}


# --- 4. Define Graph Nodes (all async) ---

async def rag_agent_node(state: AgentState):
    """Calls the RAG chain for policy questions."""
    print("\n--- Calling Policy Agent ---")
    messages = state["messages"]
    last_human_message = messages[-1].content
    response_str = await rag_agent_chain.ainvoke(last_human_message)
    return {"messages": [AIMessage(content=response_str)]}


async def data_query_agent_node(state: AgentState):
    """Calls the WORKER LLM bound to the Query tools."""
    print("\n--- Calling Data Query Agent ---")

    system_prompt = """You are an Inventory Assistant. 
    **GUIDELINES:**
    1. Use 'list_products' to see what we sell.
    2. Use 'query_product_database' for specific items.
    3. If the tool says "No products found", apologize.
    4. **Images:** Always append the exact image tags (e.g. <img src...>) from the tool output to your message.
    """

    messages = [HumanMessage(content=system_prompt)] + state["messages"]
    ai_response = await llm_query.ainvoke(messages)
    return {"messages": [ai_response]}


async def sales_agent_node(state: AgentState):
    """Calls the WORKER LLM bound to the Sales tools."""
    print("\n--- Calling Sales Agent ---")

    system_prompt = """You are the Sales Agent. Your goal is to secure the order. **PROCESS:**
    1. **Clarify the Order:** Ensure you know the Product Name, Size, and Quantity.
       - Check the immediate conversation history for the product.
       - If the user responds with just size/quantity, infer the product from the context.
    2. **Create Draft:** Once you have product, size, and quantity, call 'create_draft_order' with the details.
       - This tool returns the Total Price. Show this to the user.
    3. **Get Customer Info:** After the draft is created, ask for: Full Name, Shipping Address, Phone Number.
    4. **Confirm:** Once you have the info, parse it carefully and call 'confirm_order_details'.
       - Parse user responses like "Name: X, Address: Y, Number: Z".
       - If successful, thank them and mention their order is confirmed!
    **TONE:** Professional, efficient, and warm."""

    messages = [HumanMessage(content=system_prompt)] + state["messages"]
    return {"messages": [await llm_sales.ainvoke(messages)]}


# 🟢 CRITICAL FIX: Added 'config' parameter to capture Thread ID
async def data_query_tool_executor_node(state: AgentState, config: RunnableConfig):
    """Executes BOTH Data Query and Sales tools with Thread ID injection."""
    print("\n--- Calling Data/Sales Tool Executor ---")
    messages = state["messages"]
    last_message = messages[-1]
    tool_messages = []

    # Extract the thread_id from the LangGraph config
    # This ID is unique to the user's browser session
    thread_id = config.get("configurable", {}).get("thread_id", "guest_user")
    print(f"DEBUG: Using Thread ID for Database: {thread_id}")

    if not last_message.tool_calls:
        return {"messages": []}

    tasks = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        # 🟢 INJECT THREAD ID:
        # If the tool is a sales tool, pass the thread_id so the DB knows who this is
        if tool_name in ["create_draft_order", "confirm_order_details"]:
            tool_args["thread_id"] = thread_id

        print(f" -> Preparing tool: {tool_name} with args {tool_args}")

        # Look up tool in the master dictionary
        tool_to_call = data_tool_lookup.get(tool_name)

        if not tool_to_call:
            tasks.append((tool_call["id"], f"Error: Tool '{tool_name}' not found."))
        else:
            # Handle both async and sync tools
            if asyncio.iscoroutinefunction(tool_to_call.invoke) or hasattr(tool_to_call, 'ainvoke'):
                tasks.append((tool_call["id"], tool_to_call.ainvoke(tool_args)))
            else:
                tasks.append((tool_call["id"], tool_to_call.invoke(tool_args)))

    # Execute tasks
    results = []
    for tool_id, task in tasks:
        try:
            if asyncio.iscoroutine(task):
                res = await task
            else:
                res = task
            results.append((tool_id, res))
        except Exception as e:
            results.append((tool_id, f"Error: {e}"))

    for tool_id, result in results:
        tool_messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))

    print("Tool Observations:", [msg.content for msg in tool_messages])
    return {"messages": tool_messages}


async def web_search_agent_node(state: AgentState):
    print("\n--- Calling Web Search Agent ---")
    messages = [HumanMessage(content="Use tavily_general_search")] + list(state["messages"])
    ai_response = await llm_with_web_search_tools.ainvoke(messages)
    return {"messages": [ai_response]}


async def web_search_tool_executor_node(state: AgentState):
    print("\n--- Calling Web Search Executor ---")
    messages = state["messages"]
    last_message = messages[-1]
    tool_messages = []
    if not last_message.tool_calls: return {"messages": []}

    for tool_call in last_message.tool_calls:
        tool_to_call = web_search_tool_lookup.get(tool_call["name"])
        if tool_to_call:
            res = tool_to_call.invoke(tool_call["args"])
            tool_messages.append(ToolMessage(content=str(res), tool_call_id=tool_call["id"]))

    return {"messages": tool_messages}


# --- 5. Define the Supervisor (Router) ---
print("Initializing Supervisor...")


class RouteArgs(BaseModel):
    next_node: str = Field(..., enum=["rag_agent", "data_query_agent", "sales_agent", "web_search_agent", "__end__"])


@tool("route", args_schema=RouteArgs)
def route(next_node: str) -> str:
    """Route to the next node."""
    return next_node


llm_with_route = llm_supervisor.bind_tools([route])

supervisor_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", """You are the 'supervisor' of an apparel store system. **ROUTING RULES:**
1. **'rag_agent':** General greetings, store policies, shipping info, or returns.
2. **'data_query_agent':** BROWSING ONLY. Questions about product details, prices, stock availability, or sizes—ONLY if not in a buying context.
3. **'sales_agent':** BUYING INTENT. If the user expresses purchase interest (e.g., "I want to buy", "add to cart", "purchase", "take my money"), or provides shipping/customer info. CRITICAL: Also route here for follow-ups—if the previous AI message asked for size, quantity, or customer details in a buying context, and the user provides them (e.g., "Size M, one"), treat it as sales continuation.
4. **'web_search_agent':** ONLY for generic fashion trends outside our inventory.
**CRITICAL:**
- If the user references a specific product and shows buying intent (e.g., "I want this [product]"), route to 'sales_agent'.
- If the last message was a Tool Output confirming an order (e.g., containing 'SUCCESS' or 'COD_SUCCESS'), route to '__end__'.
- Always prioritize sales if the conversation involves confirming an order.
- Route to '__end__' only if no further action is needed."""),
        MessagesPlaceholder(variable_name="messages"),
    ]
)


async def supervisor_router(state: AgentState):
    print("\n--- Supervisor Routing ---")
    messages = state["messages"]
    last_message = messages[-1]

    if isinstance(last_message, AIMessage) and not last_message.tool_calls:
        print("Supervisor decided: -> __end__")
        return {"next": "__end__"}

    ai_response = await (supervisor_prompt | llm_with_route).ainvoke({"messages": messages})

    if ai_response.tool_calls:
        next_node = ai_response.tool_calls[0]["args"].get("next_node", "__end__")
    else:
        next_node = "__end__"

    print(f"Supervisor decided: -> {next_node}")
    return {"next": next_node}


# --- 6. Define Conditional Edges ---
def check_for_tool_calls(state: AgentState) -> str:
    last_message = state["messages"][-1]
    return "continue_with_tools" if last_message.tool_calls else "supervisor"


# --- 7. Build the Graph ---
print("Building graph...")
workflow = StateGraph(AgentState)

workflow.add_node("supervisor", supervisor_router)
workflow.add_node("rag_agent", rag_agent_node)
workflow.add_node("data_query_agent", data_query_agent_node)
workflow.add_node("sales_agent", sales_agent_node)
workflow.add_node("data_query_tool_executor", data_query_tool_executor_node)
workflow.add_node("sales_tool_executor", data_query_tool_executor_node)  # Re-use the executor function
workflow.add_node("web_search_agent", web_search_agent_node)
workflow.add_node("web_search_tool_executor", web_search_tool_executor_node)

workflow.set_entry_point("supervisor")

workflow.add_conditional_edges("supervisor", lambda state: state["next"])

workflow.add_conditional_edges("rag_agent", check_for_tool_calls,
                               {"continue_with_tools": "supervisor", "supervisor": "supervisor"})
workflow.add_conditional_edges("data_query_agent", check_for_tool_calls,
                               {"continue_with_tools": "data_query_tool_executor", "supervisor": "supervisor"})
workflow.add_conditional_edges("sales_agent", check_for_tool_calls,
                               {"continue_with_tools": "sales_tool_executor", "supervisor": "supervisor"})
workflow.add_conditional_edges("web_search_agent", check_for_tool_calls,
                               {"continue_with_tools": "web_search_tool_executor", "supervisor": "supervisor"})

workflow.add_edge("data_query_tool_executor", "data_query_agent")
workflow.add_edge("sales_tool_executor", "sales_agent")
workflow.add_edge("web_search_tool_executor", "web_search_agent")


# --- 8. Compile ---
async def create_memory():
    conn = await aiosqlite.connect("checkpoints.db")
    return AsyncSqliteSaver(conn=conn)


memory = asyncio.run(create_memory())
app = workflow.compile(checkpointer=memory)
print("\n--- Graph Compiled Successfully! ---")