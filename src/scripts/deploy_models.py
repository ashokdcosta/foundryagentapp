"""
Idempotent Model Deployment Script for Azure AI Foundry / Azure OpenAI.

This script ensures a model deployment exists in your Azure AI Foundry project
or Azure OpenAI/Cognitive Services account. Safe to run repeatedly - will not
create duplicate deployments.

Required Environment Variables:
    AZURE_SUBSCRIPTION_ID          - Azure subscription ID
    AZURE_RESOURCE_GROUP           - Resource group containing the OpenAI/Foundry resource
    AZURE_OPENAI_ACCOUNT_NAME      - Cognitive Services/OpenAI/Foundry resource name

Optional Environment Variables:
    AZURE_AI_PROJECT_ENDPOINT      - AI Foundry project endpoint (if set, verifies deployment via data-plane)
    AZURE_AI_MODEL_DEPLOYMENT_NAME - Deployment name to ensure (default: gpt-4o-mini)
    MODEL_NAME                     - Model name (default: gpt-4o-mini)
    MODEL_FORMAT                   - Model format (default: OpenAI)
    MODEL_VERSION                  - Model version (optional)
    MODEL_SKU_NAME                 - SKU name (default: Standard)
    MODEL_SKU_CAPACITY             - SKU capacity (default: 1)

Authentication:
    Uses DefaultAzureCredential (Entra ID / AAD). No API keys required.
    Ensure you are logged in via `az login` or have appropriate managed identity.

Usage:
    python src/scripts/deploy_models.py

Exit codes:
    0 - Success (deployment exists or was created)
    1 - Error (missing env vars, authentication failure, deployment failure)
"""

import os
import sys
import time
import requests
from typing import Optional, Tuple

from azure.identity import DefaultAzureCredential


# === Configuration Defaults ===

DEFAULT_DEPLOYMENT_NAME = "gpt-4o-mini"
DEFAULT_MODEL_NAME = "gpt-4o-mini"
DEFAULT_MODEL_FORMAT = "OpenAI"
DEFAULT_SKU_NAME = "Standard"
DEFAULT_SKU_CAPACITY = 1

# Azure Resource Manager API version for Cognitive Services deployments
ARM_API_VERSION = "2025-06-01"

# Azure AI Foundry data-plane API version
FOUNDRY_API_VERSION = "v1"

# Polling configuration
POLL_INTERVAL_SECONDS = 10
MAX_POLL_ATTEMPTS = 60  # 10 minutes max


# === Environment Validation ===

def validate_env() -> dict:
    """
    Validate required environment variables and return configuration dict.
    
    Returns:
        dict: Configuration values from environment
        
    Raises:
        SystemExit: If required variables are missing
    """
    required_vars = [
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_RESOURCE_GROUP",
        "AZURE_OPENAI_ACCOUNT_NAME",
    ]
    
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        print("❌ Missing required environment variables:")
        for var in missing:
            print(f"   - {var}")
        print("\nSet these in your .env file or environment before running.")
        sys.exit(1)
    
    config = {
        "subscription_id": os.environ["AZURE_SUBSCRIPTION_ID"],
        "resource_group": os.environ["AZURE_RESOURCE_GROUP"],
        "account_name": os.environ["AZURE_OPENAI_ACCOUNT_NAME"],
        "project_endpoint": os.getenv("AZURE_AI_PROJECT_ENDPOINT"),
        "deployment_name": os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", DEFAULT_DEPLOYMENT_NAME),
        "model_name": os.getenv("MODEL_NAME", DEFAULT_MODEL_NAME),
        "model_format": os.getenv("MODEL_FORMAT", DEFAULT_MODEL_FORMAT),
        "model_version": os.getenv("MODEL_VERSION"),
        "sku_name": os.getenv("MODEL_SKU_NAME", DEFAULT_SKU_NAME),
        "sku_capacity": int(os.getenv("MODEL_SKU_CAPACITY", DEFAULT_SKU_CAPACITY)),
    }
    
    print("Configuration:")
    print(f"  Subscription: {config['subscription_id']}")
    print(f"  Resource Group: {config['resource_group']}")
    print(f"  Account Name: {config['account_name']}")
    print(f"  Deployment Name: {config['deployment_name']}")
    print(f"  Model: {config['model_name']} ({config['model_format']})")
    if config['model_version']:
        print(f"  Model Version: {config['model_version']}")
    print(f"  SKU: {config['sku_name']} (capacity: {config['sku_capacity']})")
    if config['project_endpoint']:
        print(f"  Project Endpoint: {config['project_endpoint']}")
    print()
    
    return config


# === Authentication ===

_credential: Optional[DefaultAzureCredential] = None


def get_token(scope: str) -> str:
    """
    Get an access token for the specified scope using DefaultAzureCredential.
    
    Args:
        scope: The OAuth scope to request (e.g., "https://management.azure.com/.default")
        
    Returns:
        str: Access token
        
    Raises:
        SystemExit: If authentication fails
    """
    global _credential
    
    if _credential is None:
        _credential = DefaultAzureCredential()
    
    try:
        token = _credential.get_token(scope)
        return token.token
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        print("\nDefaultAzureCredential attempts authentication in order:")
        print("  1. EnvironmentCredential (AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_SECRET)")
        print("  2. WorkloadIdentityCredential (Kubernetes workload identity)")
        print("  3. ManagedIdentityCredential (Azure VM/App Service managed identity)")
        print("  4. AzureCliCredential - Run `az login` to authenticate")
        print("  5. AzurePowerShellCredential - Run `Connect-AzAccount`")
        print("  6. AzureDeveloperCliCredential - Run `azd auth login`")
        print("\nFor local development, run: az login")
        sys.exit(1)


def get_arm_token() -> str:
    """Get token for Azure Resource Manager API."""
    return get_token("https://management.azure.com/.default")


def get_foundry_token() -> str:
    """Get token for Azure AI Foundry data-plane API."""
    return get_token("https://ai.azure.com/.default")


# === Deployment Check ===

def deployment_exists_via_foundry(config: dict) -> Tuple[bool, Optional[dict]]:
    """
    Check if deployment exists using AI Foundry data-plane API.
    
    Args:
        config: Configuration dict with project_endpoint and deployment_name
        
    Returns:
        Tuple[bool, Optional[dict]]: (exists, deployment_info)
    """
    endpoint = config["project_endpoint"].rstrip("/")
    deployment_name = config["deployment_name"]
    
    url = f"{endpoint}/deployments?api-version={FOUNDRY_API_VERSION}"
    
    token = get_foundry_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        
        if resp.status_code == 200:
            data = resp.json()
            deployments = data.get("value", data.get("data", []))
            
            for d in deployments:
                name = d.get("name") or d.get("id")
                if name and name.lower() == deployment_name.lower():
                    print(f"  ✓ Found deployment '{name}' via Foundry data-plane")
                    return True, d
            
            return False, None
        elif resp.status_code == 404:
            # Endpoint may not support deployments list
            return False, None
        else:
            print(f"  ⚠ Foundry deployments list returned {resp.status_code}: {resp.text[:200]}")
            return False, None
            
    except Exception as e:
        print(f"  ⚠ Foundry deployments list failed: {e}")
        return False, None


def deployment_exists_via_arm(config: dict) -> Tuple[bool, Optional[dict]]:
    """
    Check if deployment exists using Azure Resource Manager API.
    
    Args:
        config: Configuration dict with subscription, resource group, account, deployment name
        
    Returns:
        Tuple[bool, Optional[dict]]: (exists, deployment_info)
    """
    subscription_id = config["subscription_id"]
    resource_group = config["resource_group"]
    account_name = config["account_name"]
    deployment_name = config["deployment_name"]
    
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
        f"/deployments/{deployment_name}"
        f"?api-version={ARM_API_VERSION}"
    )
    
    token = get_arm_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        
        if resp.status_code == 200:
            data = resp.json()
            provisioning_state = data.get("properties", {}).get("provisioningState", "Unknown")
            print(f"  ✓ Found deployment '{deployment_name}' via ARM (state: {provisioning_state})")
            return True, data
        elif resp.status_code == 404:
            return False, None
        else:
            print(f"  ⚠ ARM deployment check returned {resp.status_code}: {resp.text[:200]}")
            return False, None
            
    except Exception as e:
        print(f"  ⚠ ARM deployment check failed: {e}")
        return False, None


def deployment_exists(config: dict) -> Tuple[bool, Optional[dict]]:
    """
    Check if deployment exists using the best available method.
    
    Prefers Foundry data-plane API if project endpoint is configured,
    falls back to ARM API.
    
    Args:
        config: Configuration dict
        
    Returns:
        Tuple[bool, Optional[dict]]: (exists, deployment_info)
    """
    print("Checking if deployment exists...")
    
    # Try Foundry data-plane first if project endpoint is configured
    if config.get("project_endpoint"):
        exists, info = deployment_exists_via_foundry(config)
        if exists:
            return True, info
        # Fall through to ARM check
    
    # Check via ARM
    return deployment_exists_via_arm(config)


# === Deployment Creation ===

def create_or_update_deployment(config: dict) -> dict:
    """
    Create or update deployment using ARM PUT (idempotent).
    
    Args:
        config: Configuration dict
        
    Returns:
        dict: API response
        
    Raises:
        SystemExit: If creation fails
    """
    subscription_id = config["subscription_id"]
    resource_group = config["resource_group"]
    account_name = config["account_name"]
    deployment_name = config["deployment_name"]
    
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
        f"/deployments/{deployment_name}"
        f"?api-version={ARM_API_VERSION}"
    )
    
    # Build deployment body
    model_spec = {
        "format": config["model_format"],
        "name": config["model_name"],
    }
    if config.get("model_version"):
        model_spec["version"] = config["model_version"]
    
    body = {
        "sku": {
            "name": config["sku_name"],
            "capacity": config["sku_capacity"],
        },
        "properties": {
            "model": model_spec,
        },
    }
    
    print(f"Creating/updating deployment '{deployment_name}'...")
    print(f"  Model: {config['model_name']}")
    print(f"  SKU: {config['sku_name']} (capacity: {config['sku_capacity']})")
    
    token = get_arm_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    try:
        resp = requests.put(url, headers=headers, json=body, timeout=60)
        
        if resp.status_code in (200, 201, 202):
            # Handle 202 Accepted with potentially empty body
            try:
                data = resp.json() if resp.text.strip() else {}
            except Exception:
                data = {}
            provisioning_state = data.get("properties", {}).get("provisioningState", "Accepted")
            print(f"  ✓ Deployment request accepted (state: {provisioning_state})")
            return data
        else:
            error_msg = resp.text[:500]
            print(f"❌ Deployment creation failed: HTTP {resp.status_code}")
            print(f"   Response: {error_msg}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Deployment creation failed: {e}")
        sys.exit(1)


# === Polling for Completion ===

def wait_for_succeeded(config: dict) -> dict:
    """
    Poll deployment status until provisioningState is Succeeded.
    
    Args:
        config: Configuration dict
        
    Returns:
        dict: Final deployment info
        
    Raises:
        SystemExit: If deployment fails or times out
    """
    subscription_id = config["subscription_id"]
    resource_group = config["resource_group"]
    account_name = config["account_name"]
    deployment_name = config["deployment_name"]
    
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
        f"/deployments/{deployment_name}"
        f"?api-version={ARM_API_VERSION}"
    )
    
    print("Waiting for deployment to complete...")
    
    for attempt in range(MAX_POLL_ATTEMPTS):
        token = get_arm_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            
            if resp.status_code == 200:
                data = resp.json()
                provisioning_state = data.get("properties", {}).get("provisioningState", "Unknown")
                
                if provisioning_state == "Succeeded":
                    print(f"  ✓ Deployment succeeded!")
                    return data
                elif provisioning_state in ("Failed", "Canceled", "Deleted"):
                    error = data.get("properties", {}).get("error", {})
                    print(f"❌ Deployment failed with state: {provisioning_state}")
                    if error:
                        print(f"   Error: {error}")
                    sys.exit(1)
                else:
                    # Still in progress
                    print(f"  ... {provisioning_state} (attempt {attempt + 1}/{MAX_POLL_ATTEMPTS})")
                    
            elif resp.status_code == 404:
                print(f"  ⚠ Deployment not found (attempt {attempt + 1}), waiting...")
            else:
                print(f"  ⚠ Poll returned {resp.status_code}: {resp.text[:100]}")
                
        except Exception as e:
            print(f"  ⚠ Poll failed: {e}")
        
        time.sleep(POLL_INTERVAL_SECONDS)
    
    print(f"❌ Deployment timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL_SECONDS} seconds")
    sys.exit(1)


# === Main ===

def main():
    """Main function to ensure model deployment exists."""
    print("=" * 70)
    print("Azure AI Model Deployment (Idempotent)")
    print("=" * 70)
    print()
    
    # Validate environment
    config = validate_env()
    
    # Check if deployment already exists
    exists, info = deployment_exists(config)
    
    if exists:
        provisioning_state = "Unknown"
        if info:
            provisioning_state = info.get("properties", {}).get("provisioningState", "Unknown")
            if isinstance(info, dict) and "provisioningState" not in info.get("properties", {}):
                # Foundry data-plane response format may differ
                provisioning_state = info.get("status", "Unknown")
        
        print()
        print(f"REUSED: Deployment '{config['deployment_name']}' already exists (state: {provisioning_state})")
        print()
        print("=" * 70)
        print(f"AZURE_AI_MODEL_DEPLOYMENT_NAME={config['deployment_name']}")
        print("=" * 70)
        return
    
    print()
    print(f"Deployment '{config['deployment_name']}' not found. Creating...")
    print()
    
    # Create deployment
    create_or_update_deployment(config)
    
    # Wait for completion
    wait_for_succeeded(config)
    
    # Final output
    print()
    print("=" * 70)
    print(f"CREATED: Deployment '{config['deployment_name']}' is now available")
    print("=" * 70)
    print(f"AZURE_AI_MODEL_DEPLOYMENT_NAME={config['deployment_name']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
