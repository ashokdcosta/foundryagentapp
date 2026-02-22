"""Foundry AI Project Client initialization and management."""

import os
from typing import Optional
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential


class MissingConfigurationError(Exception):
    """Raised when required environment variables are missing."""

    pass


def get_project_endpoint() -> str:
    """
    Retrieve the PROJECT_ENDPOINT from environment variables.

    Returns:
        str: The Foundry project endpoint URL

    Raises:
        MissingConfigurationError: If PROJECT_ENDPOINT is not set
    """
    endpoint = os.getenv("PROJECT_ENDPOINT")
    if not endpoint:
        raise MissingConfigurationError(
            "PROJECT_ENDPOINT environment variable is not set. "
            "Expected format: https://<resource>.services.ai.azure.com/api/projects/<project>"
        )
    return endpoint


def get_project_client() -> AIProjectClient:
    """
    Create and return an authenticated AIProjectClient for Foundry.

    This function initializes the client with the PROJECT_ENDPOINT from
    environment variables and uses DefaultAzureCredential for authentication.

    Returns:
        AIProjectClient: Authenticated client ready for agent operations

    Raises:
        MissingConfigurationError: If PROJECT_ENDPOINT is not set
        Exception: If Azure authentication fails
    """
    endpoint = get_project_endpoint()

    try:
        credential = DefaultAzureCredential()
        client = AIProjectClient(endpoint=endpoint, credential=credential)
        return client
    except Exception as e:
        raise Exception(
            f"Failed to initialize AIProjectClient. "
            f"Ensure you are authenticated with Azure CLI (az login) "
            f"or have valid credentials configured. Error: {str(e)}"
        )


def validate_config() -> None:
    """
    Validate that all required environment variables are set.

    Raises:
        MissingConfigurationError: If any required variable is missing
    """
    endpoint = os.getenv("PROJECT_ENDPOINT")
    if not endpoint:
        raise MissingConfigurationError(
            "PROJECT_ENDPOINT environment variable is not set. "
            "Expected format: https://<resource>.services.ai.azure.com/api/projects/<project>"
        )
