"""Ollama reasoning with local console speech models."""

import os

from livekit.agents import AgentSession
from livekit.agents import stt as agents_stt
from livekit.plugins import openai, silero


def create_ollama_session():
    model = os.getenv("OLLAMA_MODEL", "qwen3-vl:4b").strip()
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    if not model:
        raise ValueError("OLLAMA_MODEL must name an installed, tool-capable model.")
    if not base_url.endswith("/v1"):
        base_url += "/v1"

    vad = silero.VAD.load()
    voice_backend = os.getenv("VOICE_BACKEND", "local").strip().lower()
    if voice_backend == "cloud":
        from livekit.plugins import cartesia, deepgram

        missing = [
            name for name in ("DEEPGRAM_API_KEY", "CARTESIA_API_KEY")
            if not os.getenv(name, "").strip()
        ]
        if missing:
            raise ValueError(
                "Cloud voice backend requires these keys in .env.local: "
                + ", ".join(missing)
            )

        stt = deepgram.STT(model="nova-3", language="multi")
        tts = cartesia.TTS(
            voice=os.getenv("CARTESIA_VOICE", "e7651bee-f073-4b79-9156-eff1f8ae4fd9"),
            model="sonic-3",
        )
    elif voice_backend == "local":
        from local_voice import LocalPiperTTS, LocalWhisperSTT

        stt_backend = os.getenv("STT_BACKEND", "local").strip().lower()
        if stt_backend == "local":
            recognizer = LocalWhisperSTT(
                model_name=os.getenv("LOCAL_STT_MODEL", "tiny.en").strip(),
                language=os.getenv("LOCAL_STT_LANGUAGE", "en").strip(),
            )
        elif stt_backend == "remote":
            from remote_voice import RemoteWhisperSTT

            recognizer = RemoteWhisperSTT(
                base_url=os.getenv("REMOTE_STT_URL", "").strip(),
                language=os.getenv("REMOTE_STT_LANGUAGE", "en").strip(),
                timeout=float(os.getenv("REMOTE_STT_TIMEOUT", "30")),
                token=os.getenv("REMOTE_STT_TOKEN", "").strip(),
                discovery_name=os.getenv("REMOTE_STT_DISCOVERY_NAME", "pupper-whisper").strip(),
                discovery_port=int(os.getenv("REMOTE_STT_DISCOVERY_PORT", "8009")),
                discovery_timeout=float(os.getenv("REMOTE_STT_DISCOVERY_TIMEOUT", "3")),
            )
        else:
            raise ValueError("STT_BACKEND must be 'local' or 'remote'.")
        stt = agents_stt.StreamAdapter(stt=recognizer, vad=vad)
        tts = LocalPiperTTS(
            os.getenv("LOCAL_TTS_MODEL", "models/en_US-lessac-low.onnx").strip()
        )
    else:
        raise ValueError("VOICE_BACKEND must be 'local' or 'cloud'.")

    return AgentSession(
        llm=openai.LLM.with_ollama(model=model, base_url=base_url, temperature=0.2),
        stt=stt,
        tts=tts,
        vad=vad,
        turn_detection="vad",
        max_tool_steps=20,
    )
