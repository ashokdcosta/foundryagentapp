"""
Update RetailOrchestrator agent with connected specialist agents.

This script UPDATES an existing orchestrator agent - it does NOT create new agents.
All agent IDs must already exist in Foundry and be specified in environment variables.

Required environment variables:
- PROJECT_ENDPOINT: Azure AI Foundry project endpoint
- ORCHESTRATOR_AGENT_ID: Existing orchestrator agent ID
- ORCHESTRATOR_MODEL_DEPLOYMENT: Model deployment name (deployment name)
- STOREOPS_AGENT_ID: Existing StoreOps specialist agent ID
- INVENTORY_AGENT_ID: Existing Inventory specialist agent ID
- PLANOGRAM_AGENT_ID: Existing Planogram specialist agent ID
- DEBUG: (optional) Enable debug output
"""

import os
import sys
import json
from dotenv import load_dotenv

# Load environment variables from .env file (repo root)
env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

from azure.ai.agents.models import ConnectedAgentTool  # Connected agents tool wrapper [4](https://learn.microsoft.com/en-us/python/api/azure-ai-agents/azure.ai.agents.models.connectedagenttool?view=azure-python)
from azure.core.rest import HttpRequest
from foundry_client import get_project_client


# === Configuration Validation ===

REQUIRED_ENV_VARS = [
    "PROJECT_ENDPOINT",
    "ORCHESTRATOR_AGENT_ID",
    "ORCHESTRATOR_MODEL_DEPLOYMENT",
    "STOREOPS_AGENT_ID",
    "INVENTORY_AGENT_ID",
    "PLANOGRAM_AGENT_ID",
]

API_VERSION = "v1"  # REST update endpoint uses api-version=v1 [1](https://learn.microsoft.com/en-us/rest/api/aifoundry/aiagents/update-agent/update-agent?view=rest-aifoundry-aiagents-v1)


def _debug_enabled() -> bool:
    return os.getenv("DEBUG", "false").strip().lower() == "true"


def validate_all_env_vars():
    """Validate all required environment variables are set. Fail fast if missing."""
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        print("❌ Missing required environment variables:")
        for var in missing:
            print(f"   - {var}")
        print("\nSet these in your .env file before running this script.")
        print("All agents must already exist in Foundry - this script only UPDATES.")
        sys.exit(1)


# === Compatibility Layer: agent retrieval/update ===

def _call_if_exists(obj, method_names, *args, **kwargs):
    """Try method names on obj; call the first that exists."""
    for name in method_names:
        fn = getattr(obj, name, None)
        if callable(fn):
            return fn(*args, **kwargs)
    return None


def get_agent_by_id(project_client, agent_id: str):
    """
    Compatibility: Retrieve an agent by id using whichever SDK method is available.
    Tries get_agent / get / retrieve, then falls back to listing and matching.
    """
    agents_client = project_client.agents

    # 1) direct gets
    agent = _call_if_exists(agents_client, ["get_agent", "get", "retrieve"], agent_id)
    if agent is not None:
        return agent

    # 2) list + match (method names vary by SDK version)
    # Try common list patterns
    candidates = _call_if_exists(agents_client, ["list_agents", "get_agents", "list"],)
    if candidates is None:
        # Some SDKs return a pageable list; others require args. We'll try with no args only.
        raise RuntimeError(
            "Unable to retrieve agent. No supported get/list method found on project_client.agents."
        )

    # Handle pageable or list-like
    try:
        for a in candidates:
            if getattr(a, "id", None) == agent_id:
                return a
    except TypeError:
        # If candidates isn't iterable
        pass

    raise RuntimeError(f"Agent not found for id: {agent_id}")


def update_agent_by_id(project_client, agent_id: str, *, model: str, name: str, instructions: str, tools):
    """
    Compatibility: Update agent using SDK update method if available, else REST fallback.
    tools should be a list of ToolDefinition objects (e.g., ConnectedAgentTool.definitions). [4](https://learn.microsoft.com/en-us/python/api/azure-ai-agents/azure.ai.agents.models.connectedagenttool?view=azure-python)[3](https://learn.microsoft.com/en-us/python/api/azure-ai-agents/azure.ai.agents.models.connectedagenttooldefinition?view=azure-python)
    """
    agents_client = project_client.agents

    # Try SDK methods first
    updated = _call_if_exists(
        agents_client,
        ["update_agent", "update"],
        agent_id,
        model=model,
        name=name,
        instructions=instructions,
        tools=tools,
    )
    if updated is not None:
        return updated

    # REST fallback using AIProjectClient.send_request (supported by AIProjectClient) [2](https://learn.microsoft.com/en-us/python/api/azure-ai-projects/azure.ai.projects.aiprojectclient?view=azure-python)
    if not hasattr(project_client, "send_request"):
        raise RuntimeError("No SDK update method found and project_client lacks send_request for REST fallback.")

    # Tools must be JSON-serializable in REST call: use as_dict() when available (ToolDefinition supports it) [3](https://learn.microsoft.com/en-us/python/api/azure-ai-agents/azure.ai.agents.models.connectedagenttooldefinition?view=azure-python)
    def _tool_to_json(t):
        if hasattr(t, "as_dict") and callable(t.as_dict):
            return t.as_dict(exclude_readonly=True)
        if isinstance(t, dict):
            return t
        # best-effort
        return dict(t)

    body = {
        "model": model,
        "name": name,
        "instructions": instructions,
        "tools": [_tool_to_json(t) for t in tools],
    }

    endpoint = os.environ["PROJECT_ENDPOINT"].rstrip("/")
    url = f"{endpoint}/assistants/{agent_id}?api-version={API_VERSION}"  # Update Agent REST shape [1](https://learn.microsoft.com/en-us/rest/api/aifoundry/aiagents/update-agent/update-agent?view=rest-aifoundry-aiagents-v1)

    req = HttpRequest("POST", url, headers={"Content-Type": "application/json"}, json=body)
    resp = project_client.send_request(req)

    # Successful update returns Agent object in body (200) [1](https://learn.microsoft.com/en-us/rest/api/aifoundry/aiagents/update-agent/update-agent?view=rest-aifoundry-aiagents-v1)
    if resp.status_code < 200 or resp.status_code >= 300:
        raise RuntimeError(f"REST update failed: HTTP {resp.status_code} - {resp.text()}")

    try:
        return resp.json()
    except Exception:
        return resp.text()


def validate_agent_exists(project_client, agent_id: str, agent_name: str) -> bool:
    """Validate that an agent exists in Foundry by ID."""
    try:
        agent = get_agent_by_id(project_client, agent_id)
        print(f"  ✓ {agent_name}: {agent_id} (found: {getattr(agent, 'name', 'unknown')})")
        return True
    except Exception as e:
        print(f"  ❌ {agent_name}: {agent_id} NOT FOUND")
        print(f"      Error: {e}")
        return False


# === Connected Agent Tools ===

def build_connected_agent_tools():
    """
    Build connected agent tool definitions using ConnectedAgentTool SDK class.
    
    Returns:
        list: Flattened list of tool definitions from ConnectedAgentTool.definitions
    """
    storeops_id = os.getenv("STOREOPS_AGENT_ID")
    inventory_id = os.getenv("INVENTORY_AGENT_ID")
    planogram_id = os.getenv("PLANOGRAM_AGENT_ID")
    
    # Create ConnectedAgentTool objects using SDK pattern
    storeops_tool = ConnectedAgentTool(
        id=storeops_id,
        name="StoreOpsAgent",
        description="Expert in store operations, SOPs, compliance, and operational processes. Call for questions about standard operating procedures, staff training, incident response, policy adherence, or process improvement."
    )
    
    inventory_tool = ConnectedAgentTool(
        id=inventory_id,
        name="InventoryAgent",
        description="Expert in inventory management, stock levels, out-of-stock risks, and replenishment planning. Call for questions about inventory health, OOS situations, SKU availability, or supply decisions."
    )
    
    planogram_tool = ConnectedAgentTool(
        id=planogram_id,
        name="PlanogramAgent",
        description="Expert in planogram compliance, shelf execution, merchandising, and visual presentation. Call for questions about planogram violations, shelf display issues, product placement, or store layout."
    )
    
    # Extract and flatten tool definitions from each ConnectedAgentTool
    tools = [
        *storeops_tool.definitions,
        *inventory_tool.definitions,
        *planogram_tool.definitions
    ]
    
    return tools


# === Orchestrator Instructions ===

def get_orchestrator_instructions():
    """Get routing instructions for the RetailOrchestrator."""
    return """You are the RetailOrchestrator - an intelligent agent that routes retail challenges to specialist agents.

YOUR PRIMARY RESPONSIBILITY:
You MUST route ALL user questions to the appropriate specialist agent(s) and then synthesize their responses.

MANDATORY ROUTING RULES - EXECUTE THESE IMMEDIATELY:

PLANOGRAM ROUTING (CALL PlanogramAgent):
When you see ANY of these keywords/topics, call PlanogramAgent FIRST:
  • "planogram" (any form: compliance, violation, execution, adherence)
  • "shelf" (execution, compliance, state, condition, layout)
  • "display" (product display, merchandising, visual presentation)
  • "shelf-set" or "reset" (planogram-related shelf changes)
  • "merchandising" or "visual" (store layout, presentation standards)
  • Any question about HOW products should be positioned or arranged

INVENTORY ROUTING (CALL InventoryAgent):
When you see ANY of these keywords/topics, call InventoryAgent FIRST:
  • "out-of-stock" or "OOS" (availability issues, gaps)
  • "inventory" (levels, health, stock position, supply)
  • "replenishment" or "stock" (supply, refill, ordering)
  • "SKU" (when discussing specific products, availability, or supply)
  • "sales" (when correlated with inventory or stock levels)
  • Any question about product availability or quantity on hand

STORE OPS ROUTING (CALL StoreOpsAgent):
When you see ANY of these keywords/topics, call StoreOpsAgent FIRST:
  • "store operations" or "ops" (processes, procedures, execution)
  • "SOP" or "standard operating procedure" (compliance, execution)
  • "escalation" or "management" (need to escalate, staffing actions)
  • "process" or "procedure" (how store should execute something)
  • "compliance" (operational compliance, adherence to standards)
  • Any question about WHAT ACTIONS the store should take

STRICT EXECUTION PROTOCOL:
1. Read the user's question carefully
2. IDENTIFY which agent(s) apply using the keywords above
3. CALL the agent(s) immediately using their tools
4. WAIT for all agent responses
5. Synthesize responses into business-friendly recommendations
6. NEVER provide an answer without first calling a specialist agent (unless it's a pure greeting)

IF MULTIPLE AGENTS APPLY: Call all relevant agents and combine their insights.

RESPONSE SYNTHESIS TEMPLATE:
After calling specialist agent(s), structure your final response:

(1) SITUATION SUMMARY - What the specialist agent(s) found
(2) KEY FINDINGS - Important points from specialist agent(s)
(3) RECOMMENDED ACTIONS - Specific, prioritized steps
(4) FOLLOW-UP QUESTION - Clarifying question for next steps
"""


def print_tool_details(tool):
    """Print details of a tool with safe attribute access."""
    def safe_get(obj, *attrs, default='unknown'):
        for attr in attrs:
            if hasattr(obj, attr):
                val = getattr(obj, attr)
                if val is not None:
                    return val
            elif isinstance(obj, dict) and attr in obj:
                val = obj[attr]
                if val is not None:
                    return val
        return default
    
    tool_type = safe_get(tool, 'type')
    connected_agent = safe_get(tool, 'connected_agent', default=None)
    
    if connected_agent:
        ca_name = safe_get(connected_agent, 'name')
        ca_id = safe_get(connected_agent, 'id')
        print(f"      - {ca_name} (connected_agent, id={ca_id})")
    else:
        print(f"      - {tool_type}")


# === Main Update Function ===

def update_orchestrator_agent():
    """
    Update the existing RetailOrchestrator agent.
    
    This function DOES NOT create any new agents. It:
    1. Validates all required agent IDs exist in Foundry
    2. Builds connected agent tool definitions
    3. Updates the orchestrator with new model, instructions, and tools
    
    Returns:
        str: The orchestrator agent ID
    
    Raises:
        SystemExit: If any agent doesn't exist or update fails
    """
    debug = _debug_enabled()
    
    # Initialize project client (env vars already validated by validate_all_env_vars)
    project_client = get_project_client()
    
    # Get agent IDs from environment
    orchestrator_id = os.getenv("ORCHESTRATOR_AGENT_ID")
    storeops_id = os.getenv("STOREOPS_AGENT_ID")
    inventory_id = os.getenv("INVENTORY_AGENT_ID")
    planogram_id = os.getenv("PLANOGRAM_AGENT_ID")
    model = os.getenv("ORCHESTRATOR_MODEL_DEPLOYMENT")
    
    # Validate all agents exist in Foundry
    print()
    print("Validating agent IDs exist in Foundry...")
    all_valid = True
    
    if not validate_agent_exists(project_client, orchestrator_id, "RetailOrchestrator"):
        all_valid = False
    if not validate_agent_exists(project_client, storeops_id, "StoreOpsAgent"):
        all_valid = False
    if not validate_agent_exists(project_client, inventory_id, "InventoryAgent"):
        all_valid = False
    if not validate_agent_exists(project_client, planogram_id, "PlanogramAgent"):
        all_valid = False
    
    if not all_valid:
        print()
        print("❌ One or more agents not found in Foundry.")
        print("   Check your .env file and ensure agents were created in the Foundry portal.")
        sys.exit(1)
    
    print()
    print("All agents validated ✓")
    
    # Build connected agent tools
    print()
    print("Building connected agent tools...")
    tools = build_connected_agent_tools()
    print(f"  ✓ {len(tools)} connected agent tools configured")
    
    # Get instructions
    instructions = get_orchestrator_instructions()
    
    # Update the orchestrator agent using compatibility layer
    print()
    print(f"Updating RetailOrchestrator agent ({orchestrator_id})...")
    
    try:
        updated_agent = update_agent_by_id(
            project_client=project_client,
            agent_id=orchestrator_id,
            model=model,
            name="RetailOrchestrator",
            instructions=instructions,
            tools=tools
        )
        
        if debug:
            print(f"  [DEBUG] Update response: {updated_agent}")
        
        print(f"  ✓ RetailOrchestrator updated successfully")
        
        # Fetch and verify the updated agent
        print()
        print("Verifying connected agent tools...")
        try:
            verified_agent = get_agent_by_id(project_client, orchestrator_id)
            
            agent_tools = getattr(verified_agent, 'tools', None)
            if agent_tools is None and isinstance(verified_agent, dict):
                agent_tools = verified_agent.get('tools', [])
            
            if agent_tools:
                print(f"  ✓ Agent has {len(agent_tools)} tool(s) attached:")
                for tool in agent_tools:
                    print_tool_details(tool)
            else:
                print("  ⚠ No tools found on agent after update")
        except Exception as verify_err:
            print(f"  ⚠ Could not verify agent tools: {verify_err}")
        
        return orchestrator_id
        
    except Exception as e:
        print(f"  ❌ Failed to update orchestrator: {e}")
        if debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def main():
    """Main function to update orchestrator agent."""
    print("=" * 70)
    print("Foundry Orchestrator Agent UPDATE")
    print("=" * 70)
    print()
    print("NOTE: This script updates an EXISTING orchestrator agent.")
    print("      No new agents will be created.")
    print()
    
    # Validate all required env vars are set
    validate_all_env_vars()
    
    # Update the orchestrator
    agent_id = update_orchestrator_agent()
    
    # Summary
    print()
    print("=" * 70)
    print("Orchestrator Update Summary")
    print("=" * 70)
    print(f"Agent Name: RetailOrchestrator")
    print(f"Agent ID: {agent_id}")
    print(f"Model: {os.getenv('ORCHESTRATOR_MODEL_DEPLOYMENT')}")
    print()
    print("Connected Specialist Agents:")
    print(f"  • StoreOpsAgent: {os.getenv('STOREOPS_AGENT_ID')}")
    print(f"  • InventoryAgent: {os.getenv('INVENTORY_AGENT_ID')}")
    print(f"  • PlanogramAgent: {os.getenv('PLANOGRAM_AGENT_ID')}")
    print()
    print("=" * 70)
    print(f"ORCHESTRATOR_UPDATED={agent_id}")
    print("=" * 70)


if __name__ == "__main__":
    main()