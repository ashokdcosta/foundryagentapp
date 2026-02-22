"""Foundry Agent Service client."""

import os
from azure.identity import DefaultAzureCredential


class FoundryAgent:
    """Client for interacting with Microsoft Foundry Agent Service."""

    def __init__(self):
        self.project_endpoint = os.getenv("PROJECT_ENDPOINT")
        self.credential = DefaultAzureCredential()

        if not self.project_endpoint:
            raise ValueError(
                "PROJECT_ENDPOINT must be set"
            )

    def chat(self, message: str) -> str:
        """Send a message to the agent and get a response."""
        # TODO: Implement agent API call
        return f"Agent response to: {message}"
