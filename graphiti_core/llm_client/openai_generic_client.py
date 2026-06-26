"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import json
import logging
import os
import typing
from typing import Any, ClassVar

import httpx
import openai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from ..prompts.models import Message
from .client import LLMClient, get_extraction_language_instruction
from .config import DEFAULT_MAX_TOKENS, LLMConfig, ModelSize
from .errors import RateLimitError, RefusalError

logger = logging.getLogger(__name__)

DEFAULT_MODEL = 'gpt-4.1-mini'


class OpenAIGenericClient(LLMClient):
    """
    OpenAIClient is a client class for interacting with OpenAI's language models.

    This class extends the LLMClient and provides methods to initialize the client,
    get an embedder, and generate responses from the language model.

    Attributes:
        client (AsyncOpenAI): The OpenAI client used to interact with the API.
        model (str): The model name to use for generating responses.
        temperature (float): The temperature to use for generating responses.
        max_tokens (int): The maximum number of tokens to generate in a response.

    Methods:
        __init__(config: LLMConfig | None = None, cache: bool = False, client: typing.Any = None):
            Initializes the OpenAIClient with the provided configuration, cache setting, and client.

        _generate_response(messages: list[Message]) -> dict[str, typing.Any]:
            Generates a response from the language model based on the provided messages.
    """

    # Class-level constants
    MAX_RETRIES: ClassVar[int] = 2

    def __init__(
        self,
        config: LLMConfig | None = None,
        cache: bool = False,
        client: typing.Any = None,
        max_tokens: int | None = None,
    ):
        """
        Initialize the OpenAIGenericClient with the provided configuration, cache setting, and client.

        Args:
            config (LLMConfig | None): The configuration for the LLM client, including API key, model, base URL, temperature, and max tokens.
            cache (bool): Whether to use caching for responses. Defaults to False.
            client (Any | None): An optional async client instance to use. If not provided, a new AsyncOpenAI client is created.
            max_tokens (int | None): The maximum number of tokens to generate. When None, falls back to config.max_tokens.

        """
        # removed caching to simplify the `generate_response` override
        if cache:
            raise NotImplementedError('Caching is not implemented for OpenAI')

        if config is None:
            config = LLMConfig()

        super().__init__(config, cache)

        # Use config.max_tokens unless explicitly overridden via parameter
        self.max_tokens = max_tokens if max_tokens is not None else config.max_tokens

        if client is None:
            # Reasoning models (e.g. MiniMax-M2.7) can take much longer than
            # the SDK default (600s read).  Allow override via LLM_TIMEOUT env var.
            timeout_seconds = float(os.environ.get('LLM_TIMEOUT', '600'))
            self.client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            )
        else:
            self.client = client

    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, typing.Any]:
        openai_messages: list[ChatCompletionMessageParam] = []
        for m in messages:
            m.content = self._clean_input(m.content)
            if m.role == 'user':
                openai_messages.append({'role': 'user', 'content': m.content})
            elif m.role == 'system':
                openai_messages.append({'role': 'system', 'content': m.content})
        try:
            # Prepare response format
            response_format: dict[str, Any] = {'type': 'json_object'}
            if response_model is not None:
                schema_name = getattr(response_model, '__name__', 'structured_response')
                json_schema = response_model.model_json_schema()

                # For providers that don't support OpenAI's json_schema response_format
                # (e.g. MiniMax), inject the schema into the system prompt and fall back
                # to json_object. This ensures structured output across all providers.
                schema_instruction = (
                    f'\n\nYou MUST respond with a JSON object that strictly matches '
                    f'the following JSON Schema:\n```json\n{json.dumps(json_schema, indent=2)}\n```\n'
                    f'Return ONLY the JSON object, no additional text or markdown formatting.'
                )
                # Inject schema into the first system message
                injected = False
                for m in openai_messages:
                    if m.get('role') == 'system':
                        m['content'] = (m.get('content') or '') + schema_instruction
                        injected = True
                        break
                if not injected:
                    openai_messages.insert(0, {
                        'role': 'system',
                        'content': schema_instruction.strip(),
                    })
                # Use json_object instead of json_schema for broader compatibility
                response_format = {'type': 'json_object'}

            # Build request kwargs
            request_kwargs: dict[str, Any] = dict(
                model=self.model or DEFAULT_MODEL,
                messages=openai_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format=response_format,  # type: ignore[arg-type]
            )

            # For thinking/reasoning models (e.g. MiniMax M2.7), request reasoning
            # in a separate field so it doesn't pollute the JSON content
            request_kwargs['extra_body'] = {'reasoning_split': True}

            response = await self.client.chat.completions.create(**request_kwargs)
            msg = response.choices[0].message

            import re as _re

            # Primary content from the LLM
            result = msg.content or ''

            # If content is empty, some reasoning models (vLLM with reasoning_split)
            # put the full response (including JSON) in reasoning_content.
            # Try to extract JSON from there as a fallback.
            if not result:
                reasoning = getattr(msg, 'reasoning_content', None) or ''
                if reasoning:
                    result = reasoning

            # Strip closed <think>...</think> blocks (reasoning process)
            result = _re.sub(r'<think>.*?</think>', '', result, flags=_re.DOTALL).strip()

            # Handle unclosed <think> tag: model exhausted max_tokens mid-thinking
            if result.startswith('<think>') and '</think>' not in result:
                raise ValueError(
                    'LLM response contains only an unclosed <think> tag — the model '
                    f'exhausted max_tokens ({self.max_tokens}) on reasoning before '
                    'producing any content. Consider increasing max_tokens in config.'
                )

            # Strip markdown code blocks (```json ... ``` or ``` ... ```)
            code_block = _re.search(r'```(?:json)?\s*\n?(.*?)```', result, _re.DOTALL)
            if code_block:
                result = code_block.group(1).strip()

            # Validate non-empty after cleanup
            if not result:
                raise ValueError(
                    'LLM returned empty content (content=null and no usable '
                    'reasoning_content). This may indicate the model exhausted '
                    f'max_tokens ({self.max_tokens}) on reasoning. '
                    'Consider increasing max_tokens in config.'
                )

            parsed = json.loads(result)

            # Detect empty JSON object — model failed to produce valid output
            if isinstance(parsed, dict) and len(parsed) == 0:
                raise ValueError(
                    'LLM returned empty JSON object {}. The model may have '
                    'exhausted tokens on reasoning or failed to understand the prompt. '
                    f'max_tokens={self.max_tokens}.'
                )

            return parsed
        except openai.RateLimitError as e:
            raise RateLimitError from e
        except Exception as e:
            logger.error(f'Error in generating LLM response: {e}')
            raise

    async def generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int | None = None,
        model_size: ModelSize = ModelSize.medium,
        group_id: str | None = None,
        prompt_name: str | None = None,
        *,
        attribute_extraction: bool = False,
    ) -> dict[str, typing.Any]:
        self._apply_attribute_extraction_preamble(messages, attribute_extraction)
        if max_tokens is None:
            max_tokens = self.max_tokens

        # Add multilingual extraction instructions
        messages[0].content += get_extraction_language_instruction(group_id)

        # Wrap entire operation in tracing span
        with self.tracer.start_span('llm.generate') as span:
            attributes = {
                'llm.provider': 'openai',
                'model.size': model_size.value,
                'max_tokens': max_tokens,
            }
            if prompt_name:
                attributes['prompt.name'] = prompt_name
            span.add_attributes(attributes)

            retry_count = 0
            last_error = None

            while retry_count <= self.MAX_RETRIES:
                try:
                    response = await self._generate_response(
                        messages, response_model, max_tokens=max_tokens, model_size=model_size
                    )
                    return response
                except (RateLimitError, RefusalError):
                    # These errors should not trigger retries
                    span.set_status('error', str(last_error))
                    raise
                except (
                    openai.APITimeoutError,
                    openai.APIConnectionError,
                ) as e:
                    # Transient network errors — retry at application level for
                    # reasoning models that occasionally exceed server-side or
                    # client-side timeouts.
                    last_error = e
                    if retry_count >= self.MAX_RETRIES:
                        logger.error(f'Max retries ({self.MAX_RETRIES}) exceeded on timeout/connection error: {e}')
                        span.set_status('error', str(e))
                        span.record_exception(e)
                        raise
                    retry_count += 1
                    logger.warning(
                        f'Retrying after timeout/connection error (attempt {retry_count}/{self.MAX_RETRIES}): {e}'
                    )
                except openai.InternalServerError:
                    # Let OpenAI's client handle 5xx retries
                    span.set_status('error', str(last_error))
                    raise
                except Exception as e:
                    last_error = e

                    # Don't retry if we've hit the max retries
                    if retry_count >= self.MAX_RETRIES:
                        logger.error(f'Max retries ({self.MAX_RETRIES}) exceeded. Last error: {e}')
                        span.set_status('error', str(e))
                        span.record_exception(e)
                        raise

                    retry_count += 1

                    # Construct a detailed error message for the LLM
                    error_context = (
                        f'The previous response attempt was invalid. '
                        f'Error type: {e.__class__.__name__}. '
                        f'Error details: {str(e)}. '
                        f'Please try again with a valid response, ensuring the output matches '
                        f'the expected format and constraints.'
                    )

                    error_message = Message(role='user', content=error_context)
                    messages.append(error_message)
                    logger.warning(
                        f'Retrying after application error (attempt {retry_count}/{self.MAX_RETRIES}): {e}'
                    )

            # If we somehow get here, raise the last error
            span.set_status('error', str(last_error))
            raise last_error or Exception('Max retries exceeded with no specific error')
