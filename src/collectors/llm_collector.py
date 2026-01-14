"""LLM model availability checker."""

import asyncio
import json
from typing import List
import logging

try:
    import boto3
except ImportError:
    boto3 = None

try:
    import httpx
except ImportError:
    httpx = None

from ..config.models import LLMModelConfig
from ..utils.status import HealthStatus
from ..utils.metrics import CollectorResult
from .base import BaseCollector, safe_collect


class LLMCollector(BaseCollector):
    """Collector for LLM model availability checks."""

    def __init__(
        self,
        config: List[LLMModelConfig],
        thresholds: dict,
        logger: logging.Logger
    ):
        """
        Initialize LLM collector.

        Args:
            config: List of LLM model configurations
            thresholds: System thresholds (not used for LLM checks)
            logger: Logger instance
        """
        super().__init__(config, thresholds, logger)

    @safe_collect
    async def collect(self) -> List[CollectorResult]:
        """
        Check all configured LLM models.

        Returns:
            List[CollectorResult]: LLM availability check results
        """
        if not self.config:
            self.logger.info("No LLM models configured")
            return []

        self.logger.info(f"Checking {len(self.config)} LLM model(s)")

        # Run all checks concurrently
        tasks = [self._check_model(model_config) for model_config in self.config]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions from gather
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                model_name = f"{self.config[i].provider}/{self.config[i].model_id or 'unknown'}" if i < len(self.config) else "unknown"
                self.logger.error(f"LLM check failed for {model_name}: {result}")
                final_results.append(CollectorResult(
                    collector_name="llm",
                    target_name=model_name,
                    status=HealthStatus.UNKNOWN,
                    metrics={},
                    message=f"Check failed: {str(result)}",
                    error=str(result)
                ))
            else:
                final_results.append(result)

        return final_results

    async def _check_model(self, config: LLMModelConfig) -> CollectorResult:
        """
        Check single LLM model availability.

        Args:
            config: LLM model configuration

        Returns:
            CollectorResult: Model availability result
        """
        if config.provider.lower() == "bedrock":
            return await self._check_bedrock(config)
        elif config.provider.lower() == "azure":
            return await self._check_azure(config)
        else:
            return CollectorResult(
                collector_name="llm",
                target_name=f"{config.provider}/unknown",
                status=HealthStatus.UNKNOWN,
                metrics={},
                message=f"Unknown provider: {config.provider}",
                error=f"Unsupported provider: {config.provider}"
            )

    async def _check_bedrock(self, config: LLMModelConfig) -> CollectorResult:
        """
        Check Amazon Bedrock model availability.

        Args:
            config: LLM model configuration

        Returns:
            CollectorResult: Bedrock model availability result
        """
        if boto3 is None:
            return CollectorResult(
                collector_name="llm",
                target_name=f"Bedrock/{config.model_id}",
                status=HealthStatus.UNKNOWN,
                metrics={},
                message="boto3 library not installed",
                error="ImportError: boto3"
            )

        target_name = f"Bedrock/{config.model_id or 'unknown'}"

        try:
            # Run blocking boto3 call in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._invoke_bedrock,
                config.model_id
            )

            return result

        except Exception as e:
            return CollectorResult(
                collector_name="llm",
                target_name=target_name,
                status=HealthStatus.RED,
                metrics={},
                message=f"Unavailable: {str(e)}",
                error=str(e)
            )

    def _invoke_bedrock(self, model_id: str) -> CollectorResult:
        """
        Invoke Bedrock model (blocking call).

        Args:
            model_id: Bedrock model ID

        Returns:
            CollectorResult: Check result
        """
        target_name = f"Bedrock/{model_id}"

        try:
            client = boto3.client('bedrock-runtime', region_name='us-east-1')

            # Minimal test request (10 tokens max)
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "test"}]
            }

            response = client.invoke_model(
                modelId=model_id,
                body=json.dumps(request_body)
            )

            response_body = json.loads(response['body'].read())

            # Extract token usage
            usage = response_body.get('usage', {})
            total_tokens = usage.get('input_tokens', 0) + usage.get('output_tokens', 0)

            return CollectorResult(
                collector_name="llm",
                target_name=target_name,
                status=HealthStatus.GREEN,
                metrics={
                    "model_id": model_id,
                    "tokens_used": total_tokens,
                    "provider": "bedrock"
                },
                message=f"Model accessible ({total_tokens} tokens)"
            )

        except client.exceptions.ResourceNotFoundException:
            return CollectorResult(
                collector_name="llm",
                target_name=target_name,
                status=HealthStatus.RED,
                metrics={"model_id": model_id},
                message="Model not found",
                error="ResourceNotFoundException"
            )

        except client.exceptions.ThrottlingException:
            return CollectorResult(
                collector_name="llm",
                target_name=target_name,
                status=HealthStatus.YELLOW,
                metrics={"model_id": model_id},
                message="API throttled",
                error="ThrottlingException"
            )

        except Exception as e:
            return CollectorResult(
                collector_name="llm",
                target_name=target_name,
                status=HealthStatus.RED,
                metrics={"model_id": model_id},
                message=f"Unavailable: {str(e)}",
                error=str(e)
            )

    async def _check_azure(self, config: LLMModelConfig) -> CollectorResult:
        """
        Check Azure OpenAI model availability.

        Args:
            config: LLM model configuration

        Returns:
            CollectorResult: Azure model availability result
        """
        if httpx is None:
            return CollectorResult(
                collector_name="llm",
                target_name=f"Azure/{config.endpoint or 'unknown'}",
                status=HealthStatus.UNKNOWN,
                metrics={},
                message="httpx library not installed",
                error="ImportError: httpx"
            )

        if not config.endpoint:
            return CollectorResult(
                collector_name="llm",
                target_name="Azure/unknown",
                status=HealthStatus.UNKNOWN,
                metrics={},
                message="No Azure endpoint configured",
                error="Missing endpoint"
            )

        target_name = f"Azure/{config.endpoint.split('//')[1].split('.')[0] if '//' in config.endpoint else 'unknown'}"

        try:
            import os
            api_key = os.getenv('AZURE_OPENAI_KEY')

            if not api_key:
                return CollectorResult(
                    collector_name="llm",
                    target_name=target_name,
                    status=HealthStatus.UNKNOWN,
                    metrics={},
                    message="AZURE_OPENAI_KEY environment variable not set",
                    error="Missing API key"
                )

            # Simple health check to Azure endpoint
            async with httpx.AsyncClient() as client:
                # Azure OpenAI typically has a models endpoint we can check
                models_url = f"{config.endpoint.rstrip('/')}/openai/models?api-version=2023-05-15"

                response = await client.get(
                    models_url,
                    headers={"api-key": api_key},
                    timeout=10.0
                )

                if response.status_code == 200:
                    models_data = response.json()
                    model_count = len(models_data.get('data', []))

                    return CollectorResult(
                        collector_name="llm",
                        target_name=target_name,
                        status=HealthStatus.GREEN,
                        metrics={
                            "endpoint": config.endpoint,
                            "model_count": model_count,
                            "provider": "azure"
                        },
                        message=f"Endpoint accessible ({model_count} models)"
                    )
                else:
                    return CollectorResult(
                        collector_name="llm",
                        target_name=target_name,
                        status=HealthStatus.RED,
                        metrics={"endpoint": config.endpoint},
                        message=f"HTTP {response.status_code}",
                        error=f"Unexpected status code: {response.status_code}"
                    )

        except httpx.TimeoutException:
            return CollectorResult(
                collector_name="llm",
                target_name=target_name,
                status=HealthStatus.RED,
                metrics={"endpoint": config.endpoint},
                message="Request timeout",
                error="TimeoutException"
            )

        except Exception as e:
            return CollectorResult(
                collector_name="llm",
                target_name=target_name,
                status=HealthStatus.RED,
                metrics={"endpoint": config.endpoint},
                message=f"Unavailable: {str(e)}",
                error=str(e)
            )
