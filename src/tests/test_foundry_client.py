"""Tests for foundry_client module."""

import os
import pytest
import sys
from unittest.mock import patch, MagicMock

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.foundry_client import (
    get_project_endpoint,
    get_project_client,
    validate_config,
    MissingConfigurationError,
)


class TestGetProjectEndpoint:
    """Tests for get_project_endpoint function."""

    def test_returns_endpoint_when_set(self):
        """Test that function returns endpoint when PROJECT_ENDPOINT is set."""
        test_endpoint = "https://test.services.ai.azure.com/api/projects/test-project"
        with patch.dict(os.environ, {"PROJECT_ENDPOINT": test_endpoint}):
            result = get_project_endpoint()
            assert result == test_endpoint

    def test_raises_error_when_missing(self):
        """Test that function raises MissingConfigurationError when PROJECT_ENDPOINT is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(MissingConfigurationError) as exc_info:
                get_project_endpoint()
            assert "PROJECT_ENDPOINT" in str(exc_info.value)
            assert "https://" in str(exc_info.value)


class TestValidateConfig:
    """Tests for validate_config function."""

    def test_passes_when_endpoint_set(self):
        """Test that validation passes when PROJECT_ENDPOINT is set."""
        test_endpoint = "https://test.services.ai.azure.com/api/projects/test-project"
        with patch.dict(os.environ, {"PROJECT_ENDPOINT": test_endpoint}):
            # Should not raise
            validate_config()

    def test_raises_error_when_endpoint_missing(self):
        """Test that validation fails when PROJECT_ENDPOINT is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(MissingConfigurationError):
                validate_config()


class TestGetProjectClient:
    """Tests for get_project_client function."""

    def test_raises_error_when_endpoint_missing(self):
        """Test that get_project_client raises error when PROJECT_ENDPOINT is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(MissingConfigurationError):
                get_project_client()

    @patch("agents.foundry_client.DefaultAzureCredential")
    @patch("agents.foundry_client.AIProjectClient")
    def test_creates_client_with_correct_params(self, mock_client_class, mock_credential_class):
        """Test that AIProjectClient is created with correct parameters."""
        test_endpoint = "https://test.services.ai.azure.com/api/projects/test-project"
        mock_credential_instance = MagicMock()
        mock_credential_class.return_value = mock_credential_instance
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance

        with patch.dict(os.environ, {"PROJECT_ENDPOINT": test_endpoint}):
            result = get_project_client()

            # Verify DefaultAzureCredential was created
            mock_credential_class.assert_called_once()

            # Verify AIProjectClient was created with correct parameters
            mock_client_class.assert_called_once_with(
                endpoint=test_endpoint, credential=mock_credential_instance
            )

            # Verify the client instance is returned
            assert result == mock_client_instance

    @patch("agents.foundry_client.DefaultAzureCredential")
    def test_raises_helpful_error_on_auth_failure(self, mock_credential_class):
        """Test that helpful error is raised when authentication fails."""
        test_endpoint = "https://test.services.ai.azure.com/api/projects/test-project"
        mock_credential_class.side_effect = RuntimeError("No credentials found")

        with patch.dict(os.environ, {"PROJECT_ENDPOINT": test_endpoint}):
            with pytest.raises(Exception) as exc_info:
                get_project_client()
            error_msg = str(exc_info.value)
            assert "az login" in error_msg or "Failed to initialize" in error_msg
