"""LiveKit batch STT client for tools/remote_stt/server.py."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
import uuid
from dataclasses import replace
from urllib.parse import urlsplit

import aiohttp
import numpy as np
from livekit.agents import APIConnectionError, APIStatusError, APITimeoutError, stt
from livekit.agents.types import (
    APIConnectOptions,
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    NotGivenOr,
)
from livekit.agents.utils import AudioBuffer, http_context, is_given

from speech_audio import LOCAL_SAMPLE_RATE, encode_wav, merge_audio
from stt_discovery import discover_service, validate_settings

logger = logging.getLogger(__name__)


class RemoteWhisperSTT(stt.STT):
    """Send each VAD-delimited utterance to a remote faster-whisper model."""

    def __init__(
        self,
        base_url: str,
        *,
        language: str = "en",
        timeout: float = 30.0,
        token: str = "",
        discovery_name: str = "pupper-whisper",
        discovery_port: int = 8009,
        discovery_timeout: float = 3.0,
    ) -> None:
        self._auto_discovery = base_url.strip().lower() == "auto"
        parts = urlsplit(base_url)
        if not self._auto_discovery and (
            parts.scheme not in ("http", "https") or not parts.hostname
            or parts.username or parts.password or parts.query or parts.fragment
        ):
            raise ValueError("REMOTE_STT_URL must be 'auto' or an HTTP(S) base URL without credentials, query or fragment.")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("REMOTE_STT_TIMEOUT must be a positive number of seconds.")
        super().__init__(capabilities=stt.STTCapabilities(streaming=False, interim_results=False))
        validate_settings(discovery_name, discovery_port, discovery_timeout)
        self._url = "" if self._auto_discovery else base_url.rstrip("/") + "/transcribe"
        self._discovery_name = discovery_name
        self._discovery_port = discovery_port
        self._discovery_timeout = discovery_timeout
        self._discovery_lock = asyncio.Lock()
        self._language = language
        self._timeout = timeout
        self._token = token
        self._model = "remote-faster-whisper"
        self._session: aiohttp.ClientSession | None = None

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "remote-faster-whisper"

    async def _discover_once(self) -> None:
        """Cache one successful discovery for this STT instance's lifetime."""
        async with self._discovery_lock:
            if self._url:
                return
            base_url = await discover_service(
                name=self._discovery_name, port=self._discovery_port,
                timeout=self._discovery_timeout, token=self._token,
            )
            self._url = base_url + "/transcribe"
            logger.info("Remote STT discovered name=%s url=%s", self._discovery_name, base_url)

    async def recognize(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.SpeechEvent:
        # Do not replay stale robot speech on a failed or slow connection.
        return await super().recognize(
            buffer, language=language,
            conn_options=replace(conn_options, max_retry=0, timeout=self._timeout),
        )

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.SpeechEvent:
        started = time.perf_counter()
        audio, _ = merge_audio(buffer)
        duration = len(audio) / LOCAL_SAMPLE_RATE
        requested_language = str(language) if is_given(language) else self._language
        request_id = uuid.uuid4().hex
        if not len(audio):
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT, request_id=request_id,
                alternatives=[stt.SpeechData(language=requested_language or "en", text="")],
            )
        payload = encode_wav(audio)
        headers = {"Content-Type": "audio/wav", "X-Request-ID": request_id}
        if self._token:
            headers["Authorization"] = "Bearer " + self._token
        if self._session is None or self._session.closed:
            # The agent worker owns and closes this shared HTTP connection pool.
            self._session = http_context.http_session()
        submitted = time.perf_counter()
        try:
            discovery_started = time.perf_counter()
            if self._auto_discovery and not self._url:
                await asyncio.wait_for(
                    self._discover_once(), timeout=conn_options.timeout,
                )
            url = self._url
            discovery_seconds = time.perf_counter() - discovery_started
            remaining = conn_options.timeout - (time.perf_counter() - submitted)
            if remaining <= 0:
                raise asyncio.TimeoutError("Remote STT discovery exhausted the request timeout.")
            async with self._session.post(
                url, params={"language": requested_language},
                headers=headers, data=payload, allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=remaining),
            ) as response:
                if response.status != 200:
                    # Do not include arbitrary response bodies (or transcripts) in logs.
                    raise APIStatusError(
                        "Remote STT returned an HTTP error; check the server log.",
                        status_code=response.status, request_id=request_id, retryable=False,
                    )
                raw = bytearray()
                async for chunk in response.content.iter_chunked(16_384):
                    raw.extend(chunk)
                    if len(raw) > 131_072:
                        raise ValueError("Remote STT response exceeds the size limit.")
                result = json.loads(raw)
                if not isinstance(result, dict) or result.get("request_id") != request_id:
                    raise ValueError("Remote STT response has a missing or mismatched request ID.")
                text = result.get("text")
                detected_language = result.get("language")
                model = result.get("model")
                inference = float(result["inference_seconds"])
                if (
                    not isinstance(text, str) or not isinstance(detected_language, str)
                    or not isinstance(model, str) or not math.isfinite(inference) or inference < 0
                ):
                    raise ValueError("Remote STT response has invalid transcript metadata.")
        except asyncio.TimeoutError as exc:
            raise APITimeoutError(
                "Remote STT timed out; the utterance was not automatically retried.", retryable=False,
            ) from exc
        except aiohttp.ClientError as exc:
            raise APIConnectionError("Could not reach remote STT.", retryable=False) from exc
        except (OSError, RuntimeError) as exc:
            raise APIConnectionError(f"Remote STT discovery failed: {exc}", retryable=False) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise APIConnectionError("Invalid remote STT response.", retryable=False) from exc
        self._model = model
        elapsed = time.perf_counter() - submitted
        logger.info(
            "Remote STT request=%s model=%s language=%s audio_seconds=%.3f "
            "prepare_seconds=%.3f request_seconds=%.3f discovery_seconds=%.3f inference_seconds=%.3f "
            "request_overhead_seconds=%.3f rms=%.5f peak=%.5f clipped_fraction=%.5f",
            request_id, model, detected_language, duration, submitted - started,
            elapsed, discovery_seconds, inference, max(0.0, elapsed - inference),
            float(np.sqrt(np.mean(audio * audio))), float(np.max(np.abs(audio))),
            float(np.mean(np.abs(audio) >= 0.999)),
        )
        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT, request_id=request_id,
            alternatives=[stt.SpeechData(language=detected_language or requested_language or "en", text=text)],
        )
