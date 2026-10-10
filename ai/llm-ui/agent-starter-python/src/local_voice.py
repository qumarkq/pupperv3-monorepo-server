"""Local English speech models for the Pupper console.

The STT model is intentionally batch-per-utterance: Silero VAD detects the end
of speech and LiveKit's StreamAdapter passes one utterance to faster-whisper.
Piper synthesizes PCM audio locally and returns it to the console audio output.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path

import numpy as np
from livekit.agents import stt, tts
from livekit.agents.types import (
    APIConnectOptions,
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    NotGivenOr,
)
from livekit.agents.utils import AudioBuffer, is_given
from piper import PiperVoice

from speech_audio import LOCAL_SAMPLE_RATE, merge_audio as _merge_audio

logger = logging.getLogger(__name__)


class LocalWhisperSTT(stt.STT):
    """Offline English STT using faster-whisper."""

    def __init__(self, model_name: str = "tiny.en", language: str = "en") -> None:
        # Remote STT still uses Piper from this module, without importing Whisper.
        from faster_whisper import WhisperModel

        super().__init__(
            capabilities=stt.STTCapabilities(
                streaming=False,
                interim_results=False,
            )
        )
        self._model_name = model_name
        self._language = language
        self._utterance_count = 0
        load_started = time.perf_counter()
        self._model = WhisperModel(model_name, device="cpu", compute_type="int8")
        logger.info(
            "Local STT loaded model=%s language=%s device=cpu compute_type=int8 load_seconds=%.3f",
            model_name, language, time.perf_counter() - load_started,
        )

    @property
    def model(self) -> str:
        return self._model_name

    @property
    def provider(self) -> str:
        return "local-faster-whisper"

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.SpeechEvent:
        del conn_options
        request_id = uuid.uuid4().hex
        self._utterance_count += 1
        utterance_number = self._utterance_count
        started = time.perf_counter()
        audio, _ = _merge_audio(buffer)
        audio_seconds = len(audio) / LOCAL_SAMPLE_RATE
        rms = float(np.sqrt(np.mean(audio * audio))) if len(audio) else 0.0
        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        clipped_fraction = float(np.mean(np.abs(audio) >= 0.999)) if len(audio) else 0.0
        requested_language = str(language) if is_given(language) else self._language
        submitted = time.perf_counter()

        def transcribe() -> tuple[str, str]:
            worker_started = time.perf_counter()
            segments, info = self._model.transcribe(
                audio,
                language=requested_language or None,
                beam_size=1,
                best_of=1,
                temperature=0.0,
                vad_filter=False,
            )
            segments = list(segments)
            text = " ".join(segment.text.strip() for segment in segments).strip()
            inference_seconds = time.perf_counter() - worker_started
            # Numerical diagnostics only: do not retain audio or log its transcript.
            avg_logprob = (
                sum(segment.avg_logprob for segment in segments) / len(segments)
                if segments else float("nan")
            )
            no_speech_prob = (
                sum(segment.no_speech_prob for segment in segments) / len(segments)
                if segments else float("nan")
            )
            logger.info(
                "Local STT request=%s utterance=%d model=%s language=%s "
                "audio_seconds=%.3f merge_seconds=%.3f worker_wait_seconds=%.3f "
                "inference_seconds=%.3f realtime_factor=%.3f rms=%.5f peak=%.5f "
                "clipped_fraction=%.5f segments=%d avg_logprob=%.3f no_speech_prob=%.3f",
                request_id, utterance_number, self._model_name, requested_language,
                audio_seconds, submitted - started, worker_started - submitted,
                inference_seconds,
                inference_seconds / audio_seconds if audio_seconds else 0.0,
                rms, peak, clipped_fraction, len(segments), avg_logprob, no_speech_prob,
            )
            if audio_seconds > 0 and inference_seconds > audio_seconds:
                logger.warning(
                    "Local STT request=%s recognition took longer than the audio; "
                    "compare this with capture/VAD timing to investigate accumulated delay.",
                    request_id,
                )
            return text, info.language

        text, detected_language = await asyncio.to_thread(transcribe)
        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            request_id=request_id,
            alternatives=[
                stt.SpeechData(
                    language=detected_language or requested_language or "en",
                    text=text,
                )
            ],
        )


class _PiperChunkedStream(tts.ChunkedStream):
    def __init__(
        self,
        *,
        tts_instance: "LocalPiperTTS",
        input_text: str,
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(tts=tts_instance, input_text=input_text, conn_options=conn_options)
        self._voice = tts_instance.voice

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        output_emitter.initialize(
            request_id=uuid.uuid4().hex,
            sample_rate=self._voice.config.sample_rate,
            num_channels=1,
            mime_type="audio/pcm",
            stream=False,
        )

        def synthesize() -> bytes:
            chunks = []
            for chunk in self._voice.synthesize(self._input_text):
                pcm = np.clip(chunk.audio_float_array * 32767.0, -32768, 32767).astype(np.int16)
                chunks.append(pcm.tobytes())
            return b"".join(chunks)

        audio = await asyncio.to_thread(synthesize)
        if audio:
            output_emitter.push(audio)
        output_emitter.flush()


class LocalPiperTTS(tts.TTS):
    """Offline English TTS using a local Piper voice model."""

    def __init__(self, model_path: str | Path) -> None:
        self._model_path = Path(model_path).expanduser()
        if not self._model_path.exists():
            raise FileNotFoundError(
                f"Piper voice model not found: {self._model_path}. "
                "Set LOCAL_TTS_MODEL to the .onnx voice path."
            )

        self.voice = PiperVoice.load(str(self._model_path), use_cuda=False)
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=self.voice.config.sample_rate,
            num_channels=1,
        )

    @property
    def model(self) -> str:
        return self._model_path.stem

    @property
    def provider(self) -> str:
        return "local-piper"

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> tts.ChunkedStream:
        return _PiperChunkedStream(
            tts_instance=self,
            input_text=text,
            conn_options=conn_options,
        )
