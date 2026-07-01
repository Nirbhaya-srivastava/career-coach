# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Serve the reasoning_engine ``{class_method, input}`` contract over HTTP.

Exists to guarantee support for the Vertex AI Console Playground and Gemini
Enterprise (via ADK registration), which both invoke the engine through this
contract. Agent Engine forwards calls to ``/api/reasoning_engine`` (sync) and
``/api/stream_reasoning_engine`` (streaming); dispatch is limited to the
``async_stream_query`` / ``stream_query`` operations matching the AdkApp wire
contract.

This implementation uses the ADK runner directly to avoid requiring Vertex AI /
GCP credentials when running with a Gemini API key (GOOGLE_GENAI_USE_VERTEXAI=False).
"""

import json
import uuid

from fastapi import FastAPI, HTTPException, Request, responses
from google.adk.runners import Runner
from google.genai import types

from app.app_utils import services


def _event_to_dict(event) -> dict:
    """Convert an ADK Event to a JSON-serializable dict."""
    try:
        return event.model_dump(mode="json", exclude_none=True)
    except Exception:
        return {"content": str(event)}


def attach_reasoning_engine_routes(app: FastAPI) -> None:
    """Register reasoning_engine routes that dispatch to the ADK runner directly."""
    runner: Runner | None = None

    def get_runner() -> Runner:
        nonlocal runner
        if runner is None:
            from app.agent import app as adk_app

            runner = Runner(
                app=adk_app,
                session_service=services.get_session_service(),
                artifact_service=services.get_artifact_service(),
                auto_create_session=True,
            )
        return runner

    # Methods registered to satisfy the reasoning_engine contract
    STREAMING_METHODS = {"async_stream_query", "streaming_agent_run_with_events"}
    SYNC_METHODS: set[str] = set()

    async def _async_stream_query(
        *,
        message: str | dict,
        user_id: str,
        session_id: str | None = None,
        **kwargs,
    ):
        """Run the agent and yield events as dicts — same contract as AdkApp.async_stream_query."""
        rt = get_runner()
        session_svc = services.get_session_service()

        # Build the Content from the message
        if isinstance(message, dict):
            content = types.Content.model_validate(message)
        elif isinstance(message, str):
            content = types.Content(role="user", parts=[types.Part(text=message)])
        else:
            raise TypeError("message must be a str or dict")

        # Create a session if not provided
        if not session_id:
            session = session_svc.create_session_sync(
                app_name=rt.app_name,
                user_id=user_id,
            )
            session_id = session.id

        async for event in rt.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            yield _event_to_dict(event)

    @app.post("/api/stream_reasoning_engine")
    async def stream_query(request: Request) -> responses.StreamingResponse:
        body = await request.json()
        class_method = body.get("class_method", "")
        if class_method not in STREAMING_METHODS:
            raise HTTPException(
                status_code=404,
                detail=f"Unsupported reasoning_engine method: {class_method!r}",
            )

        input_kwargs = body.get("input") or {}

        async def generator():
            async for event_dict in _async_stream_query(**input_kwargs):
                yield json.dumps(event_dict) + "\n"

        return responses.StreamingResponse(
            content=generator(), media_type="application/json"
        )

    @app.post("/api/reasoning_engine")
    async def query(request: Request) -> responses.StreamingResponse:
        """Sync reasoning engine calls are not supported; return 405."""
        body = await request.json()
        class_method = body.get("class_method", "")
        if class_method not in SYNC_METHODS:
            raise HTTPException(
                status_code=405,
                detail=f"Sync method {class_method!r} not supported. Use /api/stream_reasoning_engine.",
            )
