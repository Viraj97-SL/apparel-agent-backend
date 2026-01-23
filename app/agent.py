import os
import json
import sys
import asyncio
from dotenv import load_dotenv
from typing import TypedDict, Annotated, Sequence, List
import operator
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_community.tools.tavily_search import TavilySearchResults
# MCP Adapter Imports
from langchain_mcp_adapters.client import MultiServerMCPClient
# --- Our Custom Imports ---
from app.chat_with_rag import create_rag_chain
# --- LangGraph Imports ---
from langgraph.graph import StateGraph, END
# Use AsyncSqliteSaver for async support
import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
# For supervisor tool-calling
from langchain_core.tools import tool
from pydantic import BaseModel, Field
import nest_asyncio

# Apply the patch for nested event loops (Fixes RuntimeError on deployment)
nest_asyncio.apply()

# Load environment variables
load_dotenv()

# --- 1. CRITICAL: Capture and Validate API Keys ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GOOGLE_API_KEY:
    print("❌ CRITICAL ERROR: GOOGLE_API_KEY is missing!")
    raise ValueError("GOOGLE_API_KEY not found. Please check your Railway settings.")
if not TAVILY_API_KEY:
    print("WARNING: TAVILY_API_KEY not found. Web search will fail.")


# --- 2. Define Agent State ---
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next: str


# --- 3. Define Agents and Tools ---

# --- HYBRID BRAIN SETUP ---
# 1. The "Big Brain" (Supervisor)
llm_supervisor = ChatGoogleGenerativeAI(
    model="gemini-2.5-pro",
    temperature=0.2,
    google_api_key=GOOGLE_API_KEY
)

# 2. The "Fast Worker" (Data / Web / Tool Agents)
llm_worker = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.0,
    google_api_key=GOOGLE_API_KEY
)

# --- Agent 1: The Policy Agent (RAG) ---
print("Initializing Policy Agent (RAG)...")
rag_agent_chain = create_rag_chain()
if rag_agent_chain is None:
    print("Error: RAG chain (Policy Agent) could not be created.")
    exit()
print("Policy Agent initialized.")

# --- Agent 2: The Data Query & Sales Agents (via MCP) ---
print("Initializing Data Query Tools via MCP...")
python_path = sys.executable  # Path to your Python executable


async def initialize_data_tools():
    # 1. Get the project root directory (one level up from this file)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)

    # 2. Prepare the environment variables
    # We copy the current environment and add PYTHONPATH so the subprocess can find 'app'
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
    tools = await client.get_tools()
    return tools, client


# Run the async init and assign results
data_tools_list, mcp_client = asyncio.run(initialize_data_tools())
data_tool_lookup = {t.name: t for t in data_tools_list}

# --- UPDATE: SPLIT TOOLS BY AGENT ---
sales_tools_names = ["create_draft_order", "generate_payment_link"]
# Filter tools: Query agent gets everything EXCEPT sales tools; Sales agent gets ONLY sales tools
query_tools = [t for t in data_tools_list if t.name not in sales_tools_names]
sales_tools = [t for t in data_tools_list if t.name in sales_tools_names]

# Bind specific tools to specific LLM instances
llm_query = llm_worker.bind_tools(query_tools)
llm_sales = llm_worker.bind_tools(sales_tools)

print(f"Data Query tools initialized: {[t.name for t in query_tools]}")
print(f"Sales Agent tools initialized: {[t.name for t in sales_tools]}")

# --- Agent 3: The Web Search Agent ---
print("Initializing Web Search Tool...")
web_search_tool = TavilySearchResults(max_results=3, name="tavily_general_search")
web_search_tools_list = [web_search_tool]

# Bind tools to the WORKER model
llm_with_web_search_tools = llm_worker.bind_tools(web_search_tools_list)
web_search_tool_lookup = {t.name: t for t in web_search_tools_list}
print("Web Search tool initialized.")


# --- 4. Define Graph Nodes (all async) ---

async def rag_agent_node(state: AgentState):
    """Calls the RAG chain for policy questions."""
    print("\n--- Calling Policy Agent ---")
    messages = state["messages"]
    last_human_message = messages[-1].content
    # Use .ainvoke for async RAG
    response_str = await rag_agent_chain.ainvoke(last_human_message)
    return {"messages": [AIMessage(content=response_str)]}


async def data_query_agent_node(state: AgentState):
    """Calls the WORKER LLM bound to the Query tools."""
    print("\n--- Calling Data Query Agent (Worker LLM) ---")

    system_prompt = """You are an Inventory Assistant. 
    **GOAL:** Provide helpful answers about products (Price, Size, Stock) and orders (Status, Returns).

    **GUIDELINES:**
    1. Use 'list_products' if the user asks to see what we sell.
    2. Use 'query_product_database' for specific items.
    3. If the tool says "No products found", apologize and do NOT search the web.
    4. **Handling Sales:** If a user wants to BUY something, just output their request or say "I'll connect you to sales." The Supervisor will route them to the Sales Agent.
    5. **Images:** Always append the exact image tags (e.g. <img src...>) from the tool output to your message.
    """

    messages = [HumanMessage(content=system_prompt)] + state["messages"]
    # Use llm_query (bound to query tools)
    ai_response = await llm_query.ainvoke(messages)
    return {"messages": [ai_response]}


async def sales_agent_node(state: AgentState):
    """Calls the WORKER LLM bound to the Sales tools."""
    print("\n--- Calling Sales Agent (Worker LLM) ---")

    system_prompt = """You are the Sales Agent. Your goal is to CLOSE THE DEAL professionally and warmly.

    **YOUR PROCESS:**
    1. **Multi-Step Collection:** You do NOT need all details in one message. It is better to be conversational.
       - Example: First ask for the product/size. Then ask for the name/email. Then address.
       - Don't overwhelm the user with a giant list of questions unless they ask.

    2. **Handling Multiple Products (The "Cart"):**
       - The user might want to buy multiple items (e.g., "I want the Verona dress" ... later ... "Also add the Crimson skirt").
       - **CRITICAL:** Check the *entire conversation history*. If they mentioned Item A earlier and Item B now, the final order must include **BOTH**.
       - Before creating the order, confirm the full list: "So that's one Verona (M) and one Crimson Skirt (S). Correct?"

    3. **Closing the Sale:**
       - Once you have Name, Email, Address, Phone, and ALL Items (with sizes/quantities), call the 'create_draft_order' tool.
       - The 'items' argument must be a valid JSON String representing a LIST of items.
       - Example: items='[{"product_name": "Verona", "size": "M", "quantity": 1}, {"product_name": "Crimson", "size": "S", "quantity": 1}]'

    4. **Payment:**
       - After the order is created, call 'generate_payment_link' and share the URL.

    **FORMATTING RULES:**
    - **Do NOT use asterisks (*)** or bullet points for every single line. It looks messy.
    - Write in full, polite sentences.
    - Bad: "* Name? * Email?"
    - Good: "Could you please share your full name and email address?"
    """

    messages = [HumanMessage(content=system_prompt)] + state["messages"]
    return {"messages": [await llm_sales.ainvoke(messages)]}


async def data_query_tool_executor_node(state: AgentState):
    """Executes the Data Query AND Sales tools (Shared MCP Executor)."""
    print("\n--- Calling Data/Sales Tool Executor ---")
    messages = state["messages"]
    last_message = messages[-1]
    tool_messages = []

    if not last_message.tool_calls:
        return {"messages": []}

    tasks = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        print(f" -> Preparing tool: {tool_name} with args {tool_args}")

        # Look up tool in the master dictionary
        tool_to_call = data_tool_lookup.get(tool_name)

        if not tool_to_call:
            tasks.append((tool_call["id"], f"Error: Tool '{tool_name}' not found."))
        else:
            tasks.append(
                (tool_call["id"], tool_to_call.ainvoke(tool_args))
            )
    try:
        awaitable_tasks = [task for _, task in tasks if asyncio.iscoroutine(task)]
        results = await asyncio.gather(*awaitable_tasks)
        result_iter = iter(results)
        for i, (tool_call_id, task_or_error) in enumerate(tasks):
            if asyncio.iscoroutine(task_or_error):
                observation = next(result_iter)
            else:
                observation = task_or_error
            tool_messages.append(
                ToolMessage(content=str(observation), tool_call_id=tool_call_id)
            )
    except Exception as e:
        print(f"Error during tool execution: {e}")
        for tool_call in last_message.tool_calls:
            tool_messages.append(
                ToolMessage(content=f"Error executing tool {tool_call['name']}: {e}", tool_call_id=tool_call["id"])
            )
    print("Tool Observations:", [msg.content for msg in tool_messages])
    return {"messages": tool_messages}


async def web_search_agent_node(state: AgentState):
    """Calls the WORKER LLM bound to the Web Search tools."""
    print("\n--- Calling Web Search Agent (Worker LLM) ---")

    system_prompt = (
        "You are a helpful assistant with access to a web search tool. "
        "Your task is to answer the user's question using the 'tavily_general_search' tool. "
        "Do not hallucinate tool names. Simply call the tool with the user's query."
    )

    messages = [HumanMessage(content=system_prompt)] + list(state["messages"])
    ai_response = await llm_with_web_search_tools.ainvoke(messages)
    return {"messages": [ai_response]}


async def web_search_tool_executor_node(state: AgentState):
    """Executes the Web Search tools sequentially."""
    print("\n--- Calling Web Search Tool Executor ---")
    messages = state["messages"]
    last_message = messages[-1]
    tool_messages = []
    if not last_message.tool_calls:
        return {"messages": []}
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        print(f" -> Executing tool: {tool_name} with args {tool_args}")
        tool_to_call = web_search_tool_lookup.get(tool_name)
        if not tool_to_call:
            observation = f"Error: Tool '{tool_name}' not found."
        else:
            try:
                observation = tool_to_call.invoke(tool_args)
            except Exception as e:
                observation = f"Error executing tool {tool_name}: {e}"
        tool_messages.append(ToolMessage(content=str(observation), tool_call_id=tool_call["id"]))
    return {"messages": tool_messages}


# --- 5. Define the Supervisor (Router) ---
print("Initializing Supervisor...")


# Define Route tool
class RouteArgs(BaseModel):
    # Added "sales_agent" to the enum
    next_node: str = Field(..., enum=["rag_agent", "data_query_agent", "sales_agent", "web_search_agent", "__end__"])


@tool("route", args_schema=RouteArgs)
def route(next_node: str) -> str:
    """Route to the next node."""
    return next_node


# Bind route tool to the SUPERVISOR model
llm_with_route = llm_supervisor.bind_tools([route])

supervisor_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", """You are the 'supervisor' of an apparel store customer service system.

        **YOUR GOAL:** Route the conversation to the right specialist, OR end the turn if the user's question is answered.

        **AGENTS:**
        1. 'rag_agent': The *Policy Agent*. Use for questions about store policies (shipping, returns, T&Cs), and generic greetings/thanks.
        2. 'data_query_agent': The *Database Agent*. Use for questions about products (price, size, stock) AND browsing ("what do you sell?").
        3. 'sales_agent': The *Sales Agent*. Use ONLY for Buying, Checkout, and Ordering intents (e.g., "I want to buy", "Purchase this", giving shipping info).
        4. 'web_search_agent': The *Public Web Searcher*. Use as a 'catch-all' for fashion trends, company news, etc.

        **CRITICAL ROUTING RULES:**
        1. **CHECK THE LAST MESSAGE:** - If the *last message* is from an **AI Agent** (not the User) and it answers the question or provides the requested info, you MUST route to **'__end__'**.
           - If the *last message* is from the **User**, route it to the correct specialist.

        2. **CHECK FOR FOLLOW-UPS:** - If the AI asked for clarification on a product -> 'data_query_agent'.
           - If the AI asked for shipping/payment info -> 'sales_agent'.

        3. **GREETINGS/CLOSINGS:**
           - "Hi", "Hello", "Thanks" -> 'rag_agent'.
           - "Bye", "Exit" -> '__end__'.

        **SECURITY PROTOCOL:**
        1. You are an Apparel Customer Service Agent. Refuse irrelevant questions (coding, math, politics).
        2. If a user asks for "all orders", REFUSE.

        You MUST call the 'route' tool with the next_node argument.
        """),
        MessagesPlaceholder(variable_name="messages"),
    ]
)


async def supervisor_router(state: AgentState):
    """Routes the conversation to the appropriate agent."""
    print("\n--- Supervisor Routing ---")
    messages = state["messages"]
    last_message = messages[-1]

    # 1. HARD STOP: If an agent just spoke, end the turn.
    if isinstance(last_message, AIMessage) and not last_message.tool_calls:
        print("Supervisor decided: -> __end__ (Agent finished)")
        return {"next": "__end__"}

    # 2. Ask the Supervisor LLM
    ai_response = await (supervisor_prompt | llm_with_route).ainvoke({"messages": messages})

    # 3. SAFE PARSING
    if ai_response.tool_calls:
        args = ai_response.tool_calls[0]["args"]
        next_node = args.get("next_node", "__end__")
    else:
        next_node = "__end__"

    print(f"Supervisor decided: -> {next_node}")
    return {"next": next_node}


# --- 6. Define Conditional Edges ---
def check_for_tool_calls(state: AgentState) -> str:
    """If the agent called tools, run the executor. Otherwise, loop back to supervisor."""
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "continue_with_tools"
    else:
        return "supervisor"


# --- 7. Build the Graph ---
# --- 7. Build the Graph ---
print("Building graph...")
workflow = StateGraph(AgentState)

# Add all nodes
workflow.add_node("supervisor", supervisor_router)
workflow.add_node("rag_agent", rag_agent_node)
workflow.add_node("data_query_agent", data_query_agent_node)
workflow.add_node("sales_agent", sales_agent_node)

# --- CRITICAL FIX: Split Executors ---
# We use the same function logic, but register it as two distinct nodes.
# This allows us to route "Data" results back to the Data Agent
# and "Sales" results back to the Sales Agent.
workflow.add_node("data_query_tool_executor", data_query_tool_executor_node)
workflow.add_node("sales_tool_executor", data_query_tool_executor_node)

workflow.add_node("web_search_agent", web_search_agent_node)
workflow.add_node("web_search_tool_executor", web_search_tool_executor_node)

# Set the entry point
workflow.set_entry_point("supervisor")

# Supervisor conditional edges
workflow.add_conditional_edges(
    "supervisor",
    lambda state: state["next"],
    {
        "rag_agent": "rag_agent",
        "data_query_agent": "data_query_agent",
        "sales_agent": "sales_agent",
        "web_search_agent": "web_search_agent",
        "__end__": END,
    },
)

# RAG agent edge
workflow.add_conditional_edges(
    "rag_agent",
    check_for_tool_calls,
    {
        "continue_with_tools": "supervisor",
        "supervisor": "supervisor"
    }
)

# Data Query Edges
workflow.add_conditional_edges(
    "data_query_agent",
    check_for_tool_calls,
    {
        "continue_with_tools": "data_query_tool_executor", # Go to Data Executor
        "supervisor": "supervisor",
    },
)

# Sales Agent Edges
workflow.add_conditional_edges(
    "sales_agent",
    check_for_tool_calls,
    {
        "continue_with_tools": "sales_tool_executor", # Go to Sales Executor
        "supervisor": "supervisor",
    },
)

# --- CRITICAL FIX: Close the Loop ---
# Route tool outputs BACK to the agents so they can read the data and answer the user.
workflow.add_edge("data_query_tool_executor", "data_query_agent")
workflow.add_edge("sales_tool_executor", "sales_agent")

# Web Search agent edges
workflow.add_conditional_edges(
    "web_search_agent",
    check_for_tool_calls,
    {
        "continue_with_tools": "web_search_tool_executor",
        "supervisor": "supervisor",
    },
)
workflow.add_edge("web_search_tool_executor", "web_search_agent")


# --- 8. Compile the Graph and Set Up Memory ---
async def create_memory():
    # Use a file-based DB for persistence across server restarts
    conn = await aiosqlite.connect("checkpoints.db")
    return AsyncSqliteSaver(conn=conn)


memory = asyncio.run(create_memory())
app = workflow.compile(checkpointer=memory)
print("\n--- Graph Compiled Successfully! ---")