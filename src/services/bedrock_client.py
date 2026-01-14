"""Amazon Bedrock client for Claude model invocation."""

import json
from typing import Tuple, Dict
import logging

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = None

from ..config.models import LLMConfig


class BedrockClient:
    """
    Wrapper for Amazon Bedrock API with token tracking.

    Invokes Claude Haiku 3.5 for analysis and reporting tasks.
    Returns both response text and detailed token usage.
    """

    def __init__(self, llm_config: LLMConfig, logger: logging.Logger = None):
        """
        Initialize Bedrock client.

        Args:
            llm_config: LLM configuration (model, region, max_tokens)
            logger: Optional logger instance

        Raises:
            ImportError: If boto3 not installed
        """
        if boto3 is None:
            raise ImportError("boto3 library not installed. Install with: pip install boto3>=1.34.0")

        self.config = llm_config
        self.logger = logger or logging.getLogger(__name__)

        # Create Bedrock runtime client
        try:
            self.client = boto3.client(
                'bedrock-runtime',
                region_name=llm_config.region
            )
        except Exception as e:
            self.logger.error(f"Failed to create Bedrock client: {e}")
            raise

        # Model ID should be full ID (e.g., "us.anthropic.claude-3-5-haiku-20241022-v1:0")
        self.model_id = llm_config.model

        self.logger.info(f"Bedrock client initialized with model: {self.model_id}")

    def invoke(self, prompt: str, system_prompt: str = None) -> Tuple[str, Dict[str, int]]:
        """
        Invoke Claude and return response with token usage.

        Args:
            prompt: User prompt/question
            system_prompt: Optional system prompt for Claude

        Returns:
            Tuple of (response_text, usage_dict)
            - response_text: Claude's response as string
            - usage_dict: {"input_tokens": int, "output_tokens": int, "total_tokens": int}

        Raises:
            ClientError: If Bedrock API call fails
            ValueError: If response format is unexpected
        """
        # Build request body
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self.config.max_tokens,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        # Add system prompt if provided
        if system_prompt:
            request_body["system"] = system_prompt

        try:
            # Call Bedrock
            self.logger.debug(f"Invoking Bedrock model: {self.model_id}")
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )

            # Parse response
            response_body = json.loads(response['body'].read())

            # Extract token usage
            usage = response_body.get('usage', {})
            input_tokens = usage.get('input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)
            total_tokens = input_tokens + output_tokens

            # Extract text content
            content = response_body.get('content', [])
            if not content:
                raise ValueError("No content in Bedrock response")

            # Get first content block (text)
            text = content[0].get('text', '')

            usage_dict = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens
            }

            self.logger.debug(f"Bedrock response: {total_tokens} tokens ({input_tokens} in, {output_tokens} out)")

            return text, usage_dict

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']

            self.logger.error(f"Bedrock API error [{error_code}]: {error_message}")

            # Handle specific error cases
            if error_code == 'ThrottlingException':
                raise Exception(f"Bedrock throttling: {error_message}") from e
            elif error_code == 'ValidationException':
                raise ValueError(f"Invalid request: {error_message}") from e
            elif error_code == 'AccessDeniedException':
                raise PermissionError(f"Access denied: {error_message}") from e
            else:
                raise

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse Bedrock response: {e}")
            raise ValueError("Invalid JSON in Bedrock response") from e

        except Exception as e:
            self.logger.error(f"Unexpected error invoking Bedrock: {e}")
            raise

    async def ainvoke(self, prompt: str, system_prompt: str = None) -> Tuple[str, Dict[str, int]]:
        """
        Async wrapper for invoke() method.

        Runs blocking boto3 call in thread pool to avoid blocking event loop.

        Args:
            prompt: User prompt/question
            system_prompt: Optional system prompt

        Returns:
            Tuple of (response_text, usage_dict)
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.invoke, prompt, system_prompt)
