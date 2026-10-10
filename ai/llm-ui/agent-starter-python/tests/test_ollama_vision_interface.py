import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_DIR = Path(__file__).resolve().parents[1]
SOURCE_PATH = PROJECT_DIR / "src" / "ollama_vision_interface.py"


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class FakeImage:
    def convert(self, mode):
        return self

    def save(self, buffer, format, quality):
        buffer.write(b"fake-jpeg")


class OllamaVisionInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake_pil = types.ModuleType("PIL")
        fake_image_module = types.ModuleType("PIL.Image")
        fake_image_module.Image = FakeImage
        fake_pil.Image = fake_image_module
        fake_dotenv = types.ModuleType("dotenv")
        fake_dotenv.load_dotenv = lambda *args, **kwargs: None
        spec = importlib.util.spec_from_file_location(
            "ollama_vision_interface_under_test", SOURCE_PATH
        )
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        with patch.dict(
            sys.modules,
            {
                "PIL": fake_pil,
                "PIL.Image": fake_image_module,
                "dotenv": fake_dotenv,
            },
        ):
            spec.loader.exec_module(cls.module)

    def test_posts_image_and_prompt_to_ollama(self):
        image = FakeImage()
        response = FakeResponse(
            {"choices": [{"message": {"content": '[{"point": [10, 20]}]'}}]}
        )

        with patch.dict(
            os.environ,
            {
                "OLLAMA_BASE_URL": "http://ollama.example:11434/v1",
                "OLLAMA_MODEL": "qwen3-vl:4b",
            },
            clear=True,
        ), patch.object(self.module, "urlopen", return_value=response) as urlopen:
            result = self.module.analyze_camera_image("Find the red object", image)

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "http://ollama.example:11434/v1/chat/completions")
        self.assertEqual(payload["model"], "qwen3-vl:4b")
        self.assertEqual(payload["messages"][1]["content"][0]["text"], "Find the red object")
        self.assertTrue(
            payload["messages"][1]["content"][1]["image_url"]["url"].startswith(
                "data:image/jpeg;base64,"
            )
        )
        self.assertEqual(result, '[{"point": [10, 20]}]')

    def test_base_url_without_v1_is_normalized(self):
        image = FakeImage()
        response = FakeResponse({"choices": [{"message": {"content": "[]"}}]})

        with patch.dict(
            os.environ,
            {"OLLAMA_BASE_URL": "http://localhost:11434"},
            clear=True,
        ), patch.object(self.module, "urlopen", return_value=response) as urlopen:
            self.module.analyze_camera_image("Find a cup", image)

        self.assertEqual(
            urlopen.call_args.args[0].full_url,
            "http://localhost:11434/v1/chat/completions",
        )


if __name__ == "__main__":
    unittest.main()
