"""Orchestrator skeleton — Phase 1.

Phase 1 is a minimal Redis-stream consumer. It reads `job.created` events
from `QUEUE_TOPIC_ORCHESTRATOR`, parses the small reference payload, and
hands it to a `handler` callback that owns the actual policy-gate logic.

This is deliberately not LangGraph yet. Phase 2 will lift the loop into a
LangGraph StateGraph over the full DAG once there is more than one decision
node. The current state machine has exactly one node (policy_gate) so a
graph would be more ceremony than value.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis

log = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class OrchestratorConfig:
    queue_topic_orchestrator: str
    consumer_group: str = "orchestrator"
    consumer_name: str = "orchestrator-1"
    block_ms: int = 5000          # how long XREADGROUP blocks per call
    backoff_seconds: float = 2.0  # on unexpected error


class Orchestrator:
    """Reads from one Redis Stream, dispatches to a handler, acks on success.

    Phase 1 boundary: the orchestrator does *not* know how to talk to the
    backend DB. It just delivers a parsed event to its handler. The handler
    (see agents/orchestrator/handlers.py) is the layer that imports backend
    models and writes status updates.
    """

    def __init__(
        self,
        client: redis.Redis,
        config: OrchestratorConfig,
        handler: Handler,
    ) -> None:
        self._client = client
        self._config = config
        self._handler = handler
        self._stopping = asyncio.Event()

    async def ensure_group(self) -> None:
        """Create the consumer group if it doesn't exist."""
        try:
            await self._client.xgroup_create(
                name=self._config.queue_topic_orchestrator,
                groupname=self._config.consumer_group,
                id="0",
                mkstream=True,
            )
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def run_once(self) -> int:
        """Process one batch. Returns the number of events handled.

        Intended for tests and one-shot invocations. The Phase 1 integration
        test calls this directly after publishing an event.
        """
        await self.ensure_group()
        response = await self._client.xreadgroup(
            groupname=self._config.consumer_group,
            consumername=self._config.consumer_name,
            streams={self._config.queue_topic_orchestrator: ">"},
            count=16,
            block=self._config.block_ms,
        )
        if not response:
            return 0
        count = 0
        for _, messages in response:
            for msg_id, fields in messages:
                raw = fields.get("data") if isinstance(fields, dict) else None
                if raw is None:
                    log.warning("orchestrator: message %s has no `data` field", msg_id)
                    payload: dict[str, Any] = {}
                else:
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        log.warning("orchestrator: bad JSON in message %s", msg_id)
                        payload = {}
                if payload:
                    try:
                        await self._handler(payload)
                    except Exception:
                        # Phase 1 keeps error handling minimal — log and move on.
                        # Phase 2 introduces retries + dead-letter routing.
                        log.exception("orchestrator: handler raised for %s", msg_id)
                await self._client.xack(
                    self._config.queue_topic_orchestrator,
                    self._config.consumer_group,
                    msg_id,
                )
                count += 1
        return count

    async def run_forever(self) -> None:
        """Long-running loop. Not exercised by the Phase 1 test."""
        while not self._stopping.is_set():
            try:
                await self.run_once()
            except Exception:
                log.exception("orchestrator: unexpected error; backing off")
                await asyncio.sleep(self._config.backoff_seconds)

    def stop(self) -> None:
        self._stopping.set()
