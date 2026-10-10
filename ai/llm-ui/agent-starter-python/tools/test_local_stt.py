"""Test a small local speech-to-text model with a file or local microphone.

Install the optional test dependencies first:
    python -m pip install faster-whisper sounddevice

Examples:
    python tools/test_local_stt.py --audio ../moonshine-test/test_audio.m4a
    python tools/test_local_stt.py --language zh --seconds 5
"""

import argparse
import wave
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel


SAMPLE_RATE = 16_000


def record_microphone(path: Path, seconds: float, device: int | None) -> None:
    import sounddevice as sd

    print(f"Recording {seconds:g}s from microphone device {device or 'default'}...")
    audio = sd.rec(
        int(seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=device,
    )
    sd.wait()

    pcm = np.clip(audio[:, 0] * 32767, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm.tobytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="tiny", help="Whisper model size, e.g. tiny or base")
    parser.add_argument("--audio", type=Path, help="Audio file; omit to record from the default microphone")
    parser.add_argument("--language", default=None, help="Language code such as zh; omit for auto-detection")
    parser.add_argument("--seconds", type=float, default=5.0, help="Microphone recording duration")
    parser.add_argument("--device", type=int, help="Input device index for microphone recording")
    args = parser.parse_args()

    audio_path = args.audio
    if audio_path is None:
        audio_path = Path("local_stt_mic_test.wav")
        record_microphone(audio_path, args.seconds, args.device)
    elif not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    print(f"Loading faster-whisper model '{args.model}' on CPU (int8)...")
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(audio_path),
        language=args.language,
        beam_size=1,
        vad_filter=True,
    )

    text = " ".join(segment.text.strip() for segment in segments).strip()
    print(f"Detected language: {info.language} ({info.language_probability:.3f})")
    print(f"Transcript: {text or '[no speech detected]'}")


if __name__ == "__main__":
    main()
