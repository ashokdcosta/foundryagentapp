"""
Idempotent Agent Deployment Script for Azure AI Foundry.

This script creates/reuses Azure AI Foundry Agents for the RetailOrchestrator system.
Safe to run repeatedly - will not create duplicate agents. Uses state file to track
agent IDs and verifies existence before creating new ones.

Required Environment Variables:
    AZURE_AI_PROJECT_ENDPOINT      - Azure AI Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME - Model deployment name (e.g., gpt-4o-mini)

Optional Environment Variables:
    AZURE_ENV_NAME                 - Environment name (default: dev)

Authentication:
    Uses DefaultAzureCredential (Entra ID / AAD). No API keys required.
    Ensure you are logged in via `az login` or have appropriate managed identity.

State File:
    Agent IDs are persisted in: .azure/<AZURE_ENV_NAME>/agent_state.json

Usage:
    python src/bootstrap/deploy_agents.py

Exit codes:
    0 - Success (all agents exist or were created)
    1 - Error (missing env vars, authentication failure, creation failure)
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential


# === Agent Definitions ===

AGENT_DEFINITIONS = {
    "InventoryAgent": {
        "instructions_file": "inventory_instructions.txt",
        "description": "Expert in inventory management, stock levels, out-of-stock risks, and replenishment planning."
    },
    "StoreOpsAgent": {
        "instructions_file": "storeops_instructions.txt",
        "description": "Expert in store operations, SOPs, compliance, and operational processes."
    },
    "PlanogramAgent": {
        "instructions_file": "planogram_instructions.txt",
        "description": "Expert in planogram compliance, shelf execution, merchandising, and visual presentation."
    },
    "RetailOrchestrator": {
        "instructions_file": "orchestrator_instructions.txt",
        "description": "Intelligent orchestrator that routes retail challenges to specialist agents."
    },
}

# Order matters: create specialists first, then orchestrator
AGENT_ORDER = ["InventoryAgent", "StoreOpsAgent", "PlanogramAgent", "RetailOrchestrator"]


# === Configuration ===

def get_repo_root() -> Path:
    """Get the repository root directory."""
    # This script is at src/bootstrap/deploy_agents.py
    return Path(__file__).parent.parent.parent


def get_prompts_dir() -> Path:
    """Get the prompts directory path."""
    return get_repo_root() / "src" / "agents" / "prompts"


def get_state_dir(env_name: str) -> Path:
    """Get the state directory for the given environment."""
    return get_repo_root() / ".azure" / env_name


def get_state_file(env_name: str) -> Path:
    """Get the state file path for the given environment."""
    return get_state_dir(env_name) / "agent_state.json"


# === Environment Validation ===

def validate_env() -> Dict[str, str]:
    """
    Validate required environment variables and return configuration dict.
    
    Returns:
        dict: Configuration values from environment
        
    Raises:
        SystemExit: If required variables are missing
    """
    required_vars = [
        "AZURE_AI_PROJECT_ENDPOINT",
        "AZURE_AI_MODEL_DEPLOYMENT_NAME",
    ]
    
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        print("❌ Missing required environment variables:")
        for var in missing:
            print(f"   - {var}")
        print("\nSet these in your .env file or environment before running.")
        sys.exit(1)
    
    config = {
        "project_endpoint": os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        "model_deployment": os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        "env_name": os.getenv("AZURE_ENV_NAME", "dev"),
    }
    
    print("Configuration:")
    print(f"  Environment: {config['env_name']}")
    print(f"  Project Endpoint: {config['project_endpoint']}")
    print(f"  Model Deployment: {config['model_deployment']}")
    print()
    
    return config


# === State Management ===

def load_state(env_name: str) -> Dict[str, Any]:
    """
    Load agent state from the state file.
    
    Args:
        env_name: Environment name (e.g., "dev", "qa", "prod")
        
    Returns:
        dict: State dictionary with agent IDs
    """
    state_file = get_state_file(env_name)
    
    if not state_file.exists():
        print(f"  No existing state file found at {state_file}")
        return {env_name: {"agents": {}}}
    
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        
        # Ensure structure exists
        if env_name not in state:
            state[env_name] = {"agents": {}}
        elif "agents" not in state[env_name]:
            state[env_name]["agents"] = {}
        
        print(f"  Loaded state from {state_file}")
        return state
    except Exception as e:
        print(f"  ⚠ Failed to load state file: {e}")
        return {env_name: {"agents": {}}}


def save_state(env_name: str, state: Dict[str, Any]) -> None:
    """
    Save agent state to the state file.
    
    Args:
        env_name: Environment name
        state: State dictionary to save
    """
    state_dir = get_state_dir(env_name)
    state_file = get_state_file(env_name)
    
    # Create directory if missing
    state_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        print(f"  State saved to {state_file}")
    except Exception as e:
        print(f"  ⚠ Failed to save state file: {e}")


# === Instructions Loading ===

def read_instructions(instructions_file: str) -> str:
    """
    Read agent instructions from a text file.
    
    Args:
        instructions_file: Filename in the prompts directory
        
    Returns:
        str: Instructions text
        
    Raises:
        FileNotFoundError: If instructions file doesn't exist
    """
    prompts_dir = get_prompts_dir()
    file_path = prompts_dir / instructions_file
    
    if not file_path.exists():
        raise FileNotFoundError(f"Instructions file not found: {file_path}")
    
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read().strip()


# === Foundry Client ===

def create_client(endpoint: str) -> AIProjectClient:
    """
    Create an AIProjectClient instance.
    
    The returned client should be used as a context manager to ensure
    proper cleanup of underlying connections:
    
        with create_client(endpoint) as client:
            # use client
    
    Args:
        endpoint: Azure AI Foundry project endpoint
        
    Returns:
        AIProjectClient: Authenticated client (use as context manager)
        
    Raises:
        SystemExit: If client initialization fails
    """
    try:
        credential = DefaultAzureCredential()
        return AIProjectClient(endpoint=endpoint, credential=credential)
    except Exception as e:
        print(f"❌ Failed to initialize AIProjectClient: {e}")
        print("\nDefaultAzureCredential attempts authentication in order:")
        print("  1. EnvironmentCredential (AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_SECRET)")
        print("  2. WorkloadIdentityCredential (Kubernetes workload identity)")
        print("  3. ManagedIdentityCredential (Azure VM/App Service managed identity)")
        print("  4. AzureCliCredential - Run `az login` to authenticate")
        print("  5. AzurePowerShellCredential - Run `Connect-AzAccount`")
        print("  6. AzureDeveloperCliCredential - Run `azd auth login`")
        print("\nFor local development, run: az login")
        sys.exit(1)


# === Agent Verification ===

def _call_if_exists(obj, method_names, *args, **kwargs):
    """Try method names on obj; call the first that exists."""
    for name in method_names:
        fn = getattr(obj, name, None)
        if callable(fn):
            return fn(*args, **kwargs)
    return None


def _normalize_agent_list(result) -> list:
    """
    Normalize agent list results from various SDK return types.
    
    Handles:
    - dict with 'data' or 'value' key (REST-style responses)
    - Pageable objects with iteration support
    - Plain lists or iterables
    - Generator/iterator objects
    
    Args:
        result: Raw result from list_agents/get_agents/list
        
    Returns:
        list: Normalized list of agent objects
    """
    if result is None:
        return []
    
    # Case 1: Dict with 'data' or 'value' key (common REST response pattern)
    if isinstance(result, dict):
        if "data" in result:
            return list(result["data"])
        if "value" in result:
            return list(result["value"])
        # Fallback: return empty if dict but no recognized key
        return []
    
    # Case 2: Already a list
    if isinstance(result, list):
        return result
    
    # Case 3: Pageable/ItemPaged - has 'by_page' method or is iterable
    # Try to detect Azure SDK paged objects
    if hasattr(result, "by_page"):
        # ItemPaged from azure-core - iterate all pages
        try:
            agents = []
            for item in result:
                agents.append(item)
            return agents
        except Exception:
            pass
    
    # Case 4: Generic iterable/iterator/generator
    try:
        return list(result)
    except (TypeError, Exception):
        pass
    
    return []


def agent_exists(client: AIProjectClient, agent_id: str) -> bool:
    """
    Check if an agent exists in Foundry by ID.
    
    Implements robust verification with multiple fallback strategies:
    1. Try direct get-by-id methods (cleanest if supported)
    2. Fall back to listing agents and matching by ID
    
    The list fallback normalizes various SDK return types:
    - dict with 'data'/'value' keys
    - Pageable/ItemPaged objects
    - Plain lists or iterators
    
    Args:
        client: AIProjectClient instance
        agent_id: Agent ID to verify
        
    Returns:
        bool: True if agent exists, False otherwise
    """
    agents_client = client.agents
    
    # Strategy 1: Try direct get methods (preferred if SDK supports it)
    try:
        agent = _call_if_exists(agents_client, ["get_agent", "get", "retrieve"], agent_id)
        if agent is not None:
            return True
    except Exception as e:
        # 404 or not found is expected for missing agents
        error_str = str(e).lower()
        if "404" in error_str or "not found" in error_str:
            return False
        # Log other errors but continue to fallback
        print(f"    ⚠ Direct lookup failed: {e}")
    
    # Strategy 2: List agents and match by ID
    # Normalize the result to handle different SDK return types
    try:
        raw_result = _call_if_exists(agents_client, ["list_agents", "get_agents", "list"])
        agents = _normalize_agent_list(raw_result)
        
        for agent in agents:
            # Support both object attribute and dict key access
            agent_id_value = None
            if hasattr(agent, "id"):
                agent_id_value = agent.id
            elif isinstance(agent, dict) and "id" in agent:
                agent_id_value = agent["id"]
            
            if agent_id_value == agent_id:
                return True
    except Exception as e:
        print(f"    ⚠ List lookup failed: {e}")
    
    return False


# === Agent Creation ===

def create_agent(client: AIProjectClient, name: str, instructions: str, 
                 model: str, description: str = "") -> str:
    """
    Create a new agent in Foundry.
    
    Args:
        client: AIProjectClient instance
        name: Agent name
        instructions: Agent instructions/system prompt
        model: Model deployment name
        description: Optional agent description
        
    Returns:
        str: Created agent ID
        
    Raises:
        Exception: If agent creation fails
    """
    agents_client = client.agents
    
    # Try different creation method signatures
    try:
        # Method 1: create_agent with keyword args
        agent = _call_if_exists(
            agents_client,
            ["create_agent", "create"],
            model=model,
            name=name,
            instructions=instructions,
        )
        if agent is not None:
            return agent.id
    except TypeError:
        pass  # Method signature didn't match
    except Exception as e:
        # Re-raise if it's a real error
        if "already exists" not in str(e).lower():
            raise
    
    # Method 2: Try with positional model arg
    try:
        agent = agents_client.create_agent(
            model,
            name=name,
            instructions=instructions,
        )
        return agent.id
    except Exception as e:
        raise Exception(f"Failed to create agent '{name}': {e}")


# === Main Logic ===

def ensure_agent(client: AIProjectClient, agent_name: str, config: Dict[str, str],
                 state: Dict[str, Any], env_name: str) -> tuple:
    """
    Ensure an agent exists, creating it if necessary.
    
    Args:
        client: AIProjectClient instance
        agent_name: Name of the agent to ensure
        config: Configuration dictionary
        state: Current state dictionary
        env_name: Environment name
        
    Returns:
        tuple: (agent_id, action) where action is "REUSED" or "CREATED"
    """
    agent_def = AGENT_DEFINITIONS[agent_name]
    agents_state = state[env_name]["agents"]
    
    print(f"\n  Processing {agent_name}...")
    
    # Check if we have a saved ID
    saved_info = agents_state.get(agent_name, {})
    saved_id = saved_info.get("id") if isinstance(saved_info, dict) else None
    
    if saved_id:
        print(f"    Found saved ID: {saved_id}")
        
        # Verify agent still exists
        if agent_exists(client, saved_id):
            print(f"    ✓ Agent verified in Foundry")
            return saved_id, "REUSED"
        else:
            print(f"    ⚠ Agent no longer exists in Foundry, will recreate")
    
    # Need to create the agent
    print(f"    Creating new agent...")
    
    # Read instructions
    try:
        instructions = read_instructions(agent_def["instructions_file"])
        print(f"    Loaded instructions from {agent_def['instructions_file']}")
    except FileNotFoundError as e:
        print(f"    ❌ {e}")
        raise
    
    # Create agent with environment-suffixed display name
    # Display name: "InventoryAgent-dev", but state key remains "InventoryAgent"
    display_name = f"{agent_name}-{env_name}"
    agent_id = create_agent(
        client=client,
        name=display_name,
        instructions=instructions,
        model=config["model_deployment"],
        description=agent_def.get("description", ""),
    )
    print(f"    Display name: {display_name}")
    
    # Update state
    agents_state[agent_name] = {"id": agent_id}
    print(f"    ✓ Created agent with ID: {agent_id}")
    
    return agent_id, "CREATED"


def main():
    """Main function to ensure all agents exist."""
    print("=" * 70)
    print("Azure AI Foundry Agent Deployment (Idempotent)")
    print("=" * 70)
    print()
    
    # Validate environment
    config = validate_env()
    env_name = config["env_name"]
    
    # Load existing state
    print("Loading state...")
    state = load_state(env_name)
    
    # Ensure prompts directory exists before initializing client
    prompts_dir = get_prompts_dir()
    if not prompts_dir.exists():
        print(f"\n❌ Prompts directory not found: {prompts_dir}")
        print("   Please create the prompts directory and add instruction files:")
        for agent_name, agent_def in AGENT_DEFINITIONS.items():
            print(f"     - {agent_def['instructions_file']}")
        sys.exit(1)
    
    # Initialize client as context manager for proper connection cleanup
    print("\nInitializing Foundry client...")
    with create_client(config["project_endpoint"]) as client:
        print("  ✓ Client initialized (context manager)")
        
        # Process each agent
        print("\nProcessing agents...")
        results = {}
        
        for agent_name in AGENT_ORDER:
            try:
                agent_id, action = ensure_agent(client, agent_name, config, state, env_name)
                results[agent_name] = {"id": agent_id, "action": action}
            except Exception as e:
                print(f"\n❌ Failed to ensure {agent_name}: {e}")
                sys.exit(1)
    
    # Client is now closed - save state outside the context manager
    print("\nSaving state...")
    save_state(env_name, state)
    
    # Print summary
    print()
    print("=" * 70)
    print("Agent Deployment Summary")
    print("=" * 70)
    print(f"Environment: {env_name}")
    print(f"Project Endpoint: {config['project_endpoint']}")
    print(f"Model Deployment: {config['model_deployment']}")
    print()
    print("Agents:")
    for agent_name, info in results.items():
        status = "✓ REUSED" if info["action"] == "REUSED" else "✓ CREATED"
        print(f"  {status}: {agent_name}")
        print(f"           ID: {info['id']}")
    print()
    print("=" * 70)
    
    # Also output environment variable format for easy copy
    print("\nEnvironment variables (for .env file):")
    for agent_name, info in results.items():
        env_var = agent_name.upper().replace("ORCHESTRATOR", "ORCHESTRATOR_AGENT")
        if agent_name == "RetailOrchestrator":
            env_var = "ORCHESTRATOR_AGENT_ID"
        elif agent_name == "InventoryAgent":
            env_var = "INVENTORY_AGENT_ID"
        elif agent_name == "StoreOpsAgent":
            env_var = "STOREOPS_AGENT_ID"
        elif agent_name == "PlanogramAgent":
            env_var = "PLANOGRAM_AGENT_ID"
        print(f"  {env_var}={info['id']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
