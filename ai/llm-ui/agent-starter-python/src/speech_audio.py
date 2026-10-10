"""Shared PCM conversion for local and remote utterance recognition."""

from __future__ import annotations

import io
import wave

import numpy as np
from livekit import rtc
from livekit.agents.utils import AudioBuffer

LOCAL_SAMPLE_RATE = 16_000


def merge_audio(buffer: AudioBuffer) -> tuple[np.ndarray, int]:
    """Convert LiveKit frames to mono float32 at Whisper's sample rate."""
    frame = rtc.combine_audio_frames(buffer)
    samples = np.frombuffer(frame.data, dtype=np.int16)
    if frame.num_channels > 1:
        samples = samples.reshape(-1, frame.num_channels).mean(axis=1)
    audio = samples.astype(np.float32) / 32768.0
    if not len(audio) or frame.sample_rate == LOCAL_SAMPLE_RATE:
        return audio, LOCAL_SAMPLE_RATE
    target_length = max(1, round(len(audio) * LOCAL_SAMPLE_RATE / frame.sample_rate))
    source_positions = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    target_positions = np.linspace(0.0, 1.0, num=target_length, endpoint=False)
    return (
        np.interp(target_positions, source_positions, audio).astype(np.float32),
        LOCAL_SAMPLE_RATE,
    )


def encode_wav(audio: np.ndarray) -> bytes:
    """Encode a mono 16 kHz utterance as little-endian PCM16 WAV."""
    pcm = np.clip(np.rint(audio * 32768.0), -32768, 32767).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(LOCAL_SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())
    return output.getvalue()
