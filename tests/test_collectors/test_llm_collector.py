"""Tests for LLM collector."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from src.collectors.llm_collector import LLMCollector
from src.utils.status import HealthStatus

# Fixtures imported from conftest.py: llm_configs, thresholds, logger


@pytest.mark.asyncio
async def test_llm_collector_bedrock_success(llm_configs, thresholds, logger):
    """Test successful Bedrock model check."""
    collector = LLMCollector([llm_configs[0]], thresholds, logger)

    with patch('src.collectors.llm_collector.boto3') as mock_boto3:
        # Mock Bedrock client
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        # Mock successful invoke_model response
        mock_response = {
            'body': MagicMock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'content': [{'text': 'test'}],
            'usage': {'input_tokens': 10, 'output_tokens': 5}
        }).encode()

        mock_client.invoke_model.return_value = mock_response

        # Execute
        results = await collector.collect()

        # Verify
        assert len(results) == 1
        assert results[0].collector_name == "llm"
        assert results[0].status == HealthStatus.GREEN
        assert "bedrock" in results[0].target_name.lower()
        assert results[0].metrics["model_id"] == llm_configs[0].model_id


@pytest.mark.asyncio
async def test_llm_collector_azure_success(llm_configs, thresholds, logger):
    """Test successful Azure model check."""
    collector = LLMCollector([llm_configs[1]], thresholds, logger)

    with patch('src.collectors.llm_collector.httpx') as mock_httpx:
        # Mock Azure OpenAI endpoint
        mock_client = MagicMock()
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{'message': {'content': 'test'}}],
            'usage': {'total_tokens': 15}
        }

        mock_client.post.return_value = mock_response

        with patch('os.getenv') as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: {
                'AZURE_OPENAI_KEY': 'test_key',
                'AZURE_OPENAI_ENDPOINT': 'https://test.openai.azure.com'
            }.get(key, default)

            # Execute
            results = await collector.collect()

            # Verify
            assert len(results) == 1
            assert results[0].status == HealthStatus.GREEN
            assert "azure" in results[0].target_name.lower()


@pytest.mark.asyncio
async def test_llm_collector_bedrock_throttling(llm_configs, thresholds, logger):
    """Test Bedrock throttling error (RED)."""
    collector = LLMCollector([llm_configs[0]], thresholds, logger)

    with patch('src.collectors.llm_collector.boto3') as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        # Mock throttling exception
        from botocore.exceptions import ClientError
        error_response = {
            'Error': {
                'Code': 'ThrottlingException',
                'Message': 'Rate exceeded'
            }
        }
        mock_client.invoke_model.side_effect = ClientError(error_response, 'invoke_model')

        # Execute
        results = await collector.collect()

        # Verify RED status
        assert len(results) == 1
        assert results[0].status == HealthStatus.RED
        assert "throttl" in results[0].message.lower() or "rate" in results[0].message.lower()


@pytest.mark.asyncio
async def test_llm_collector_azure_missing_credentials(llm_configs, thresholds, logger):
    """Test Azure with missing credentials (RED)."""
    collector = LLMCollector([llm_configs[1]], thresholds, logger)

    with patch('src.collectors.llm_collector.httpx'):
        with patch('os.getenv') as mock_getenv:
            mock_getenv.return_value = None  # No credentials

            # Execute
            results = await collector.collect()

            # Verify RED status
            assert len(results) == 1
            assert results[0].status == HealthStatus.RED


@pytest.mark.asyncio
async def test_llm_collector_no_boto3(llm_configs, thresholds, logger):
    """Test graceful handling when boto3 not installed."""
    collector = LLMCollector(llm_configs, thresholds, logger)

    # Mock boto3 as unavailable
    with patch('src.collectors.llm_collector.boto3', None):
        results = await collector.collect()

        # Should return UNKNOWN result for each config
        assert len(results) >= 1
        assert any(r.status == HealthStatus.UNKNOWN for r in results)


@pytest.mark.asyncio
async def test_llm_collector_empty_config(thresholds, logger):
    """Test collector with no models configured."""
    collector = LLMCollector([], thresholds, logger)

    results = await collector.collect()

    # Should return empty list
    assert len(results) == 0


@pytest.mark.asyncio
async def test_llm_collector_mixed_providers(llm_configs, thresholds, logger):
    """Test collector with both Bedrock and Azure models."""
    collector = LLMCollector(llm_configs, thresholds, logger)

    with patch('src.collectors.llm_collector.boto3') as mock_boto3, \
         patch('src.collectors.llm_collector.httpx') as mock_httpx:

        # Mock Bedrock
        mock_bedrock_client = MagicMock()
        mock_boto3.client.return_value = mock_bedrock_client

        mock_bedrock_response = {
            'body': MagicMock()
        }
        mock_bedrock_response['body'].read.return_value = json.dumps({
            'content': [{'text': 'test'}],
            'usage': {'input_tokens': 10, 'output_tokens': 5}
        }).encode()

        mock_bedrock_client.invoke_model.return_value = mock_bedrock_response

        # Mock Azure
        mock_azure_client = MagicMock()
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_azure_client

        mock_azure_response = Mock()
        mock_azure_response.status_code = 200
        mock_azure_response.json.return_value = {
            'choices': [{'message': {'content': 'test'}}],
            'usage': {'total_tokens': 15}
        }

        mock_azure_client.post.return_value = mock_azure_response

        with patch('os.getenv') as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: {
                'AZURE_OPENAI_KEY': 'test_key',
                'AZURE_OPENAI_ENDPOINT': 'https://test.openai.azure.com'
            }.get(key, default)

            # Execute
            results = await collector.collect()

            # Verify both providers checked
            assert len(results) == 2
            assert any("bedrock" in r.target_name.lower() for r in results)
            assert any("azure" in r.target_name.lower() for r in results)


@pytest.mark.asyncio
async def test_llm_collector_minimal_tokens(llm_configs, thresholds, logger):
    """Test that collector uses minimal tokens for checks."""
    collector = LLMCollector([llm_configs[0]], thresholds, logger)

    with patch('src.collectors.llm_collector.boto3') as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        mock_response = {
            'body': MagicMock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'content': [{'text': 'test'}],
            'usage': {'input_tokens': 10, 'output_tokens': 5}
        }).encode()

        mock_client.invoke_model.return_value = mock_response

        # Execute
        results = await collector.collect()

        # Verify minimal token request was made
        call_args = mock_client.invoke_model.call_args
        body = json.loads(call_args[1]['body'])

        # Check max_tokens is low (e.g., <= 50)
        assert body['max_tokens'] <= 50
        assert len(body['messages'][0]['content']) < 20  # Short prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
