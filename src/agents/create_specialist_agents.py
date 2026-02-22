"""Create specialized agents for Foundry Agent Service."""

import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    # Try alternative location
    load_dotenv()

from foundry_client import get_project_client, validate_config


def save_agent_ids_to_env(agent_ids):
    """
    Save agent IDs to .env file for use by orchestrator and tests.
    
    Args:
        agent_ids: Dictionary of agent names and IDs
    """
    try:
        env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        
        # Read current .env file
        env_content = {}
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_content[key.strip()] = value.strip()
        
        # Update with new agent IDs
        env_content['STOREOPS_AGENT_ID'] = agent_ids.get('StoreOpsAgent', '')
        env_content['INVENTORY_AGENT_ID'] = agent_ids.get('InventoryAgent', '')
        env_content['PLANOGRAM_AGENT_ID'] = agent_ids.get('PlanogramAgent', '')
        
        # Write back to .env file
        with open(env_path, 'w') as f:
            for key, value in env_content.items():
                f.write(f"{key}={value}\n")
        
        print(f"✓ Agent IDs saved to .env file")
    except Exception as e:
        print(f"⚠ Warning: Could not save agent IDs to .env: {e}")


def create_specialist_agents():
    """
    Create three specialized agents for store operations, inventory, and planograms.

    Returns:
        dict: Dictionary with agent names as keys and agent IDs as values

    Raises:
        MissingConfigurationError: If required environment variables are not set
        Exception: If agent creation fails
    """
    # Validate configuration before proceeding
    validate_config()

    # Initialize the Foundry project client
    project_client = get_project_client()

    agents = {}

    # Agent 1: Store Operations Agent
    try:
        print("Creating StoreOpsAgent...")
        store_ops_agent = project_client.agents.create_agent(
            model=os.getenv("StoreOps_MODEL_DEPLOYMENT"),
            name="StoreOpsAgent",
            instructions="""You are an expert Store Operations Assistant. Your role is to:
- Provide SOP (Standard Operating Procedure) remediation steps for store operational issues
- Guide through store operations playbooks and processes
- Recommend specific actions to resolve operational challenges
- Provide escalation guidance when issues require management intervention
- Help ensure consistent store performance and compliance with operations standards""",
        )
        agents["StoreOpsAgent"] = store_ops_agent.id
        print(f"✓ StoreOpsAgent created with ID: {store_ops_agent.id}")
    except Exception as e:
        print(f"✗ Failed to create StoreOpsAgent: {e}")
        raise

    # Agent 2: Inventory Agent
    try:
        print("Creating InventoryAgent...")
        inventory_agent = project_client.agents.create_agent(
            model=os.getenv("Inventory_MODEL_DEPLOYMENT"),
            name="InventoryAgent",
            instructions="""You are an expert Inventory Management Assistant. Your role is to:
- Monitor and analyze inventory health metrics and trends
- Assess out-of-stock (OOS) risks and identify at-risk SKUs
- Provide replenishment recommendations based on demand forecasts
- Help optimize inventory levels to balance availability and carrying costs
- Support inventory planning and allocation decisions""",
        )
        agents["InventoryAgent"] = inventory_agent.id
        print(f"✓ InventoryAgent created with ID: {inventory_agent.id}")
    except Exception as e:
        print(f"✗ Failed to create InventoryAgent: {e}")
        raise

    # Agent 3: Planogram Agent
    try:
        print("Creating PlanogramAgent...")
        planogram_agent = project_client.agents.create_agent(
            model=os.getenv("Planogram_MODEL_DEPLOYMENT"),
            name="PlanogramAgent",
            instructions="""You are an expert Planogram & Visual Merchandising Assistant. Your role is to:
- Verify planogram compliance and adherence to shelf-set guidelines
- Assess shelf execution quality and product placement correctness
- Provide guidance on proper merchandise display and visual presentation
- Recommend corrective actions for display issues
- Support planogram compliance audits and performance tracking""",
        )
        agents["PlanogramAgent"] = planogram_agent.id
        print(f"✓ PlanogramAgent created with ID: {planogram_agent.id}")
    except Exception as e:
        print(f"✗ Failed to create PlanogramAgent: {e}")
        raise

    return agents


def main():
    """Main function to create agents and display results."""
    try:
        print("=" * 60)
        print("Foundry Specialist Agents Creation")
        print("=" * 60)
        print()

        agents = create_specialist_agents()
        
        # Save agent IDs to .env for orchestrator and tests
        save_agent_ids_to_env(agents)

        print()
        print("=" * 60)
        print("Agent Creation Summary")
        print("=" * 60)
        for agent_name, agent_id in agents.items():
            print(f"{agent_name}: {agent_id}")
        print("=" * 60)

        return agents

    except Exception as e:
        print()
        print("=" * 60)
        print(f"ERROR: Failed to create agents: {e}")
        print("=" * 60)
        raise


if __name__ == "__main__":
    main()
