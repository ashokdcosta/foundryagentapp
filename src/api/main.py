"""FastAPI application for Foundry Agent Service with RetailOrchestrator integration."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import sys
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
import uuid

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    # Try alternative location
    load_dotenv()

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agents.foundry_client import get_project_client, validate_config

app = FastAPI(title="Foundry Agent API")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
PROJECT_ENDPOINT = os.getenv("PROJECT_ENDPOINT")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
ORCHESTRATOR_AGENT_ID = os.getenv("ORCHESTRATOR_AGENT_ID")  # Pre-created agent ID (optional)

# Initialize Azure credentials
try:
    credential = DefaultAzureCredential()
except Exception as e:
    print(f"Warning: Failed to initialize credentials: {e}")
    credential = None


# ============================================================================
# FUNCTION CALLING: Tool Definitions & Implementations
# ============================================================================

def create_restock_task(sku: str, quantity: int, store_id: str, priority: str = "normal") -> Dict[str, Any]:
    """
    Create a restock task for inventory replenishment.
    
    Args:
        sku: Stock Keeping Unit identifier
        quantity: Number of units to restock
        store_id: Target store identifier
        priority: Priority level (low, normal, high)
    
    Returns:
        Task creation result with ID and status
    """
    task_id = str(uuid.uuid4())[:8]
    return {
        "success": True,
        "task_id": task_id,
        "sku": sku,
        "quantity": quantity,
        "store_id": store_id,
        "priority": priority,
        "status": "created",
        "timestamp": datetime.utcnow().isoformat(),
        "message": f"Restock task {task_id} created for {quantity} units of SKU {sku} at store {store_id} with {priority} priority"
    }


def open_planogram_ticket(store_id: str, department: str, issue_type: str, description: str) -> Dict[str, Any]:
    """
    Open a ticket for planogram compliance issues.
    
    Args:
        store_id: Target store identifier
        department: Department with the issue (e.g., grocery, health&beauty)
        issue_type: Type of issue (non-compliance, damage, missing)
        description: Detailed description of the issue
    
    Returns:
        Ticket creation result with ticket ID and status
    """
    ticket_id = f"PLG-{str(uuid.uuid4())[:8].upper()}"
    return {
        "success": True,
        "ticket_id": ticket_id,
        "store_id": store_id,
        "department": department,
        "issue_type": issue_type,
        "description": description,
        "status": "open",
        "priority": "normal" if issue_type == "non-compliance" else "high",
        "timestamp": datetime.utcnow().isoformat(),
        "message": f"Planogram ticket {ticket_id} opened for store {store_id} in {department} department: {issue_type}"
    }


# Tool registry mapping function names to implementations
TOOL_FUNCTIONS = {
    "create_restock_task": create_restock_task,
    "open_planogram_ticket": open_planogram_ticket,
}

# Tool schemas (OpenAI format) for agent to understand available functions
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "create_restock_task",
            "description": "Create a restock task for inventory replenishment. Use this when inventory is low or out of stock and needs refilling.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "Stock Keeping Unit identifier (e.g., SKU-12345)"
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Number of units to restock"
                    },
                    "store_id": {
                        "type": "string",
                        "description": "Target store identifier (e.g., STORE-001)"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "normal", "high"],
                        "description": "Priority level for the restock task"
                    }
                },
                "required": ["sku", "quantity", "store_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_planogram_ticket",
            "description": "Open a ticket for planogram compliance issues. Use this when there are shelf execution, display, or planogram adherence problems.",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_id": {
                        "type": "string",
                        "description": "Target store identifier (e.g., STORE-001)"
                    },
                    "department": {
                        "type": "string",
                        "description": "Department with the issue (e.g., grocery, health&beauty, electronics)"
                    },
                    "issue_type": {
                        "type": "string",
                        "enum": ["non-compliance", "damage", "missing"],
                        "description": "Type of planogram issue"
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description of the planogram issue"
                    }
                },
                "required": ["store_id", "department", "issue_type", "description"]
            }
        }
    }
]


def execute_tool_call(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool call and return the result.
    
    Args:
        tool_name: Name of the tool function to execute
        tool_input: Input parameters for the function
    
    Returns:
        Result of the tool execution
    """
    if tool_name not in TOOL_FUNCTIONS:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}",
            "available_tools": list(TOOL_FUNCTIONS.keys())
        }
    
    try:
        tool_func = TOOL_FUNCTIONS[tool_name]
        result = tool_func(**tool_input)
        return result
    except TypeError as e:
        return {
            "success": False,
            "error": f"Invalid parameters for {tool_name}: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error executing {tool_name}: {str(e)}"
        }


# Pydantic Models
class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    userId: str
    message: str


class Citation(BaseModel):
    """Citation model for sources."""
    source: str
    url: Optional[str] = None


class DebugInfo(BaseModel):
    """Debug information about agent calls."""
    sub_agents_used: Optional[List[str]] = None
    tool_calls_executed: Optional[List[str]] = None
    orchestrator_agent_id: Optional[str] = None
    timestamp: Optional[str] = None


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    answer: str
    citations: Optional[List[Citation]] = None
    debug: Optional[DebugInfo] = None


def _parse_agent_response(response_text: str, run=None, project_client=None) -> dict:
    """
    Parse agent response and extract structured information.
    
    Looks for patterns like:
    - (1) WHAT WE SEE / (1) What we see
    - (2) LIKELY CAUSES / (2) Likely causes
    - (3) RECOMMENDED ACTIONS / (3) Recommended actions
    - (4) FOLLOW-UP QUESTION / (4) Follow-up question
    
    Also extracts sub-agents called from run metadata.
    """
    sections = {
        "answer": response_text,
        "sub_agents": [],
        "tool_calls": []
    }
    
    # Extract tool calls from run steps (connected agents appear as tool calls)
    if run and project_client:
        thread_id = getattr(run, 'thread_id', None)
        run_id = getattr(run, 'id', None)
        
        if DEBUG:
            print(f"[DEBUG] _parse_agent_response: thread_id={thread_id}, run_id={run_id}")
        
        if thread_id and run_id:
            try:
                # Use correct SDK pattern: project_client.agents.run_steps.list()
                run_steps = project_client.agents.run_steps.list(thread_id=thread_id, run_id=run_id)
                step_count = 0
                for step in run_steps:
                    step_count += 1
                    step_type = getattr(step, 'type', 'unknown')
                    if DEBUG:
                        print(f"[DEBUG] Step {step_count}: type={step_type}, has step_details={hasattr(step, 'step_details')}")
                    
                    if hasattr(step, 'step_details'):
                        details = step.step_details
                        details_type = type(details).__name__
                        if DEBUG:
                            print(f"[DEBUG] Step details type: {details_type}")
                        
                        # Check for tool calls in step details
                        if hasattr(details, 'tool_calls'):
                            if DEBUG:
                                print(f"[DEBUG] Found {len(details.tool_calls)} tool calls in step")
                            for tool_call in details.tool_calls:
                                tool_type = getattr(tool_call, 'type', '')
                                if DEBUG:
                                    print(f"[DEBUG] Tool call type: {tool_type}, attrs: {[a for a in dir(tool_call) if not a.startswith('_')]}")
                                
                                # Connected agent tool calls
                                if tool_type == 'connected_agent':
                                    # tool_call is dict-like, try multiple ways to get agent name
                                    agent_name = None
                                    if hasattr(tool_call, 'connected_agent'):
                                        agent_name = getattr(tool_call.connected_agent, 'name', None)
                                    elif hasattr(tool_call, 'get'):
                                        # Dict-like access
                                        ca = tool_call.get('connected_agent', {})
                                        if isinstance(ca, dict):
                                            agent_name = ca.get('name')
                                        elif hasattr(ca, 'name'):
                                            agent_name = ca.name
                                    
                                    # Try getting name from output (connected agent response)
                                    if not agent_name and hasattr(tool_call, 'get'):
                                        output = tool_call.get('output', '')
                                        if output:
                                            # Try to infer agent from output content
                                            output_str = str(output).lower()
                                            if 'storeops' in output_str:
                                                agent_name = 'StoreOpsAgent'
                                            elif 'inventory' in output_str:
                                                agent_name = 'InventoryAgent'
                                            elif 'planogram' in output_str:
                                                agent_name = 'PlanogramAgent'
                                    
                                    # Try to get from id pattern
                                    if not agent_name and hasattr(tool_call, 'id'):
                                        call_id = tool_call.id if hasattr(tool_call, 'id') else tool_call.get('id', '')
                                        if DEBUG:
                                            print(f"[DEBUG] Connected agent call_id: {call_id}")
                                    
                                    if DEBUG:
                                        print(f"[DEBUG] Connected agent name resolved: {agent_name}")
                                    if agent_name and agent_name not in sections["sub_agents"]:
                                        sections["sub_agents"].append(agent_name)
                                        sections["tool_calls"].append(f"connected_agent:{agent_name}")
                                
                                # Function tool calls
                                elif tool_type == 'function':
                                    if hasattr(tool_call, 'function'):
                                        func_name = getattr(tool_call.function, 'name', None)
                                        if func_name:
                                            sections["tool_calls"].append(func_name)
                                            # Map tool names to agent names
                                            if func_name in ("StoreOpsAgent", "InventoryAgent", "PlanogramAgent"):
                                                if func_name not in sections["sub_agents"]:
                                                    sections["sub_agents"].append(func_name)
                if DEBUG:
                    print(f"[DEBUG] Total steps processed: {step_count}")
            except Exception as e:
                if DEBUG:
                    print(f"[DEBUG] Error listing run steps: {e}")
    
    # Fallback: Extract from run.tool_calls if available
    if not sections["sub_agents"] and run and hasattr(run, 'tool_calls') and run.tool_calls:
        for tool_call in run.tool_calls:
            if hasattr(tool_call, 'function') and hasattr(tool_call.function, 'name'):
                tool_name = tool_call.function.name
                sections["tool_calls"].append(tool_name)
                # Map tool names to agent names
                if tool_name == "StoreOpsAgent":
                    sections["sub_agents"].append("StoreOpsAgent")
                elif tool_name == "InventoryAgent":
                    sections["sub_agents"].append("InventoryAgent")
                elif tool_name == "PlanogramAgent":
                    sections["sub_agents"].append("PlanogramAgent")
    
    # Also look for mentions in response text (fallback)
    response_lower = response_text.lower()
    if "storeopsa" in response_lower and "StoreOpsAgent" not in sections["sub_agents"]:
        sections["sub_agents"].append("StoreOpsAgent")
    if "inventorya" in response_lower and "InventoryAgent" not in sections["sub_agents"]:
        sections["sub_agents"].append("InventoryAgent")
    if "planograma" in response_lower and "PlanogramAgent" not in sections["sub_agents"]:
        sections["sub_agents"].append("PlanogramAgent")
    
    return sections


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/config")
def get_config():
    """Get configuration (non-sensitive)."""
    return {
        "project_endpoint": PROJECT_ENDPOINT,
        "debug_mode": DEBUG,
        "available_tools": list(TOOL_FUNCTIONS.keys()),
    }


@app.get("/tools")
def get_tools():
    """Get available tools for agent function calling."""
    return {
        "tools": TOOLS_SCHEMA,
        "count": len(TOOLS_SCHEMA),
        "functions": list(TOOL_FUNCTIONS.keys())
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Chat endpoint that routes queries to RetailOrchestrator agent with function calling support.
    
    Uses the azure-ai-agents 1.1.0 API with create_thread_and_process_run for automatic
    tool calling handling.
    
    Args:
        request: ChatRequest with userId and message
        
    Returns:
        ChatResponse with answer, optional citations and debug info
    """
    try:
        # Validate configuration
        validate_config()
        
        # Get project client
        project_client = get_project_client()
        
        # Get or create orchestrator agent
        orchestrator_id = ORCHESTRATOR_AGENT_ID
        if not orchestrator_id:
            # Try to get agent by name
            try:
                agents = project_client.agents.list_agents()
                for agent in agents:
                    if agent.name == "RetailOrchestrator":
                        orchestrator_id = agent.id
                        break
            except Exception as e:
                if DEBUG:
                    print(f"[DEBUG] Could not list agents: {e}")
        
        if not orchestrator_id:
            raise HTTPException(
                status_code=500,
                detail="RetailOrchestrator agent not found. Create it first using src/agents/create_orchestrator_agent.py"
            )
        
        # Use the correct Azure SDK 1.1.0 API
        # Create thread with user message and run agent with automatic tool processing
        try:
            from azure.ai.agents.models import AgentThreadCreationOptions, MessageAttachment
            
            # Create thread with initial message
            thread_options = AgentThreadCreationOptions()
            thread_options['messages'] = [
                {
                    'role': 'user',
                    'content': request.message
                }
            ]
            
            if DEBUG:
                print(f"[DEBUG] Creating thread and running agent {orchestrator_id}")
                print(f"[DEBUG] User message: {request.message}")
            
            # Create and run agent with automatic tool processing
            # This handles the full conversation loop including tool calling
            run = project_client.agents.create_thread_and_process_run(
                agent_id=orchestrator_id,
                thread=thread_options
            )
            
            if DEBUG:
                print(f"[DEBUG] Run completed. Status: {getattr(run, 'status', 'unknown')}")
                print(f"[DEBUG] Run dict keys: {list(run.__dict__.keys()) if hasattr(run, '__dict__') else 'N/A'}")
            
            # Extract response from the thread's messages
            # The run object doesn't contain messages - we need to list them from the thread
            agent_response = None
            thread_id = getattr(run, 'thread_id', None)
            
            if thread_id:
                if DEBUG:
                    print(f"[DEBUG] Thread ID: {thread_id}")
                
                # List messages in the thread to get the assistant's response
                # Use the correct SDK pattern: project_client.agents.messages.list()
                try:
                    # Try simpler method first: get_last_message_text_by_role
                    try:
                        agent_response = project_client.agents.messages.get_last_message_text_by_role(
                            thread_id=thread_id, role="assistant"
                        )
                        if DEBUG:
                            print(f"[DEBUG] Got response via get_last_message_text_by_role: {agent_response[:100] if agent_response else 'None'}...")
                    except Exception as e1:
                        if DEBUG:
                            print(f"[DEBUG] get_last_message_text_by_role failed: {e1}")
                        # Fall back to listing messages
                        messages = project_client.agents.messages.list(thread_id=thread_id)
                        
                        if DEBUG:
                            print(f"[DEBUG] Messages type: {type(messages)}")
                    
                    # Iterate through messages to find assistant response
                    for msg in messages:
                        if hasattr(msg, 'role') and msg.role == 'assistant':
                            if hasattr(msg, 'content'):
                                content = msg.content
                                if isinstance(content, str):
                                    agent_response = content
                                elif isinstance(content, list) and len(content) > 0:
                                    # Handle content blocks (TextMessageContent)
                                    text_parts = []
                                    for block in content:
                                        if hasattr(block, 'text') and hasattr(block.text, 'value'):
                                            text_parts.append(block.text.value)
                                        elif hasattr(block, 'text'):
                                            text_parts.append(str(block.text))
                                        elif hasattr(block, 'value'):
                                            text_parts.append(block.value)
                                    if text_parts:
                                        agent_response = "\n".join(text_parts)
                                break
                except Exception as e2:
                    if DEBUG:
                        print(f"[DEBUG] Error listing messages: {e2}")
                except Exception as e:
                    if DEBUG:
                        print(f"[DEBUG] Error getting messages: {e}")
            
            # Fallback: try other attributes on run object
            if not agent_response:
                if hasattr(run, 'response'):
                    agent_response = run.response
                elif hasattr(run, 'output'):
                    agent_response = run.output
                elif hasattr(run, 'result'):
                    agent_response = run.result
            
            # Final fallback message if nothing found
            if not agent_response:
                agent_response = (
                    f"The RetailOrchestrator agent has processed your request about: '{request.message}'. "
                    f"Enable DEBUG mode in .env for more details about the agent execution."
                )
            
            # Parse response for sub-agents and tool calls
            parsed = _parse_agent_response(agent_response, run, project_client)
            
            # Build response with debug info
            debug_info = None
            if DEBUG:
                sub_agents = parsed["sub_agents"] if parsed["sub_agents"] else None
                tool_calls = parsed["tool_calls"] if parsed["tool_calls"] else None
                
                # If no sub-agents detected but should have been called
                if not sub_agents and not tool_calls:
                    warning = "No specialist agents were invoked. Routing may have failed. User message: " + request.message
                    debug_info = DebugInfo(
                        sub_agents_used=None,
                        tool_calls_executed=None,
                        orchestrator_agent_id=orchestrator_id,
                        timestamp=datetime.now(timezone.utc).isoformat()
                    )
                else:
                    debug_info = DebugInfo(
                        sub_agents_used=sub_agents,
                        tool_calls_executed=tool_calls if tool_calls else None,
                        orchestrator_agent_id=orchestrator_id,
                        timestamp=datetime.now(timezone.utc).isoformat()
                    )
            
            return ChatResponse(
                answer=agent_response,
                citations=None,
                debug=debug_info
            )
        
        except Exception as e:
            if DEBUG:
                print(f"[DEBUG] Error in create_thread_and_process_run: {e}")
                print(f"[DEBUG] Error type: {type(e).__name__}")
            # Return error response
            return ChatResponse(
                answer=f"I encountered an issue connecting to the RetailOrchestrator agent. Please ensure the agent is properly configured and your Azure credentials are valid. Error: {str(e)[:200]}",
                debug=DebugInfo(
                    orchestrator_agent_id=orchestrator_id,
                    timestamp=datetime.utcnow().isoformat()
                )
            )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        error_detail = str(e)
        if DEBUG:
            error_detail = f"{error_detail}\n[Debug: {type(e).__name__}]"
        raise HTTPException(status_code=500, detail=error_detail)


@app.post("/agent/chat")
def legacy_chat(message: str):
    """Legacy chat endpoint for backward compatibility."""
    request = ChatRequest(userId="anonymous", message=message)
    return chat(request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
