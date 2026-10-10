import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch


PROJECT_DIR = Path(__file__).resolve().parents[1]
SOURCE_PATH = PROJECT_DIR / "src" / "ollama_session.py"


class OllamaSessionTests(unittest.TestCase):
    def setUp(self):
        self.livekit = ModuleType("livekit")
        self.livekit_agents = MagicMock(name="livekit.agents")
        self.livekit_plugins = MagicMock(name="livekit.plugins")
        self.local_voice = MagicMock(name="local_voice")

        self.livekit.agents = self.livekit_agents
        self.livekit.plugins = self.livekit_plugins

        modules = {
            "livekit": self.livekit,
            "livekit.agents": self.livekit_agents,
            "livekit.plugins": self.livekit_plugins,
            "local_voice": self.local_voice,
        }
        self.module_patcher = patch.dict(sys.modules, modules)
        self.module_patcher.start()

        spec = importlib.util.spec_from_file_location("ollama_session_under_test", SOURCE_PATH)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def tearDown(self):
        self.module_patcher.stop()

    def test_local_backend_uses_local_stt_and_tts(self):
        env = {
            "OLLAMA_MODEL": "local-tool-model",
            "OLLAMA_BASE_URL": "http://192.168.1.5:11434/",
            "LOCAL_STT_MODEL": "tiny.en",
            "LOCAL_STT_LANGUAGE": "en",
            "LOCAL_TTS_MODEL": "voice.onnx",
        }

        with patch.dict(os.environ, env, clear=True):
            self.module.create_ollama_session()

        self.livekit_plugins.silero.VAD.load.assert_called_once_with()
        self.local_voice.LocalWhisperSTT.assert_called_once_with(
            model_name="tiny.en", language="en"
        )
        self.local_voice.LocalPiperTTS.assert_called_once_with("voice.onnx")
        self.livekit_agents.stt.StreamAdapter.assert_called_once()
        self.livekit_plugins.openai.LLM.with_ollama.assert_called_once_with(
            model="local-tool-model",
            base_url="http://192.168.1.5:11434/v1",
            temperature=0.2,
        )

        options = self.livekit_agents.AgentSession.call_args.kwargs
        self.assertEqual(options["turn_detection"], "vad")
        self.assertIs(options["vad"], self.livekit_plugins.silero.VAD.load.return_value)
        self.assertIs(options["tts"], self.local_voice.LocalPiperTTS.return_value)

    def test_existing_v1_path_is_preserved(self):
        with patch.dict(
            os.environ,
            {
                "OLLAMA_BASE_URL": "http://localhost:11434/v1/",
                "VOICE_BACKEND": "local",
            },
            clear=True,
        ):
            self.module.create_ollama_session()

        kwargs = self.livekit_plugins.openai.LLM.with_ollama.call_args.kwargs
        self.assertEqual(kwargs["base_url"], "http://localhost:11434/v1")


if __name__ == "__main__":
    unittest.main()
