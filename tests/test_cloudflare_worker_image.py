import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from config import MEDIA_TIMEOUT_SECONDS
from multimedia.providers.cloudflare_worker_image import CloudflareWorkerImageProvider
from multimedia.providers.image_factory import configured_image_provider


class CloudflareWorkerImageProviderTests(unittest.TestCase):
    def test_generate_posts_prompt_and_saves_png(self):
        response = Mock()
        response.headers = {"Content-Type": "image/png"}
        response.content = b"\x89PNG\r\n\x1a\nimage-bytes"
        response.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "scene.webp"
            with patch("multimedia.providers.cloudflare_worker_image.CF_WORKER_URL", "https://images.example.workers.dev/"), patch(
                "multimedia.providers.cloudflare_worker_image.requests.post", return_value=response
            ) as post:
                result = CloudflareWorkerImageProvider().generate("A bright landscape", output)

            post.assert_called_once_with(
                "https://images.example.workers.dev/generate",
                json={"prompt": "A bright landscape"},
                timeout=MEDIA_TIMEOUT_SECONDS,
            )
            self.assertEqual(Path(result["path"]).suffix, ".png")
            self.assertEqual(Path(result["path"]).read_bytes(), response.content)

    def test_generate_rejects_non_image_response(self):
        response = Mock()
        response.headers = {"Content-Type": "application/json"}
        response.content = b'{"error":"not an image"}'
        response.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as directory, patch(
            "multimedia.providers.cloudflare_worker_image.CF_WORKER_URL", "https://images.example.workers.dev"
        ), patch("multimedia.providers.cloudflare_worker_image.requests.post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "unsupported content type"):
                CloudflareWorkerImageProvider().generate("prompt", Path(directory) / "scene.png")

    def test_generate_propagates_worker_http_errors(self):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("worker returned an error")

        with tempfile.TemporaryDirectory() as directory, patch(
            "multimedia.providers.cloudflare_worker_image.CF_WORKER_URL", "https://images.example.workers.dev"
        ), patch("multimedia.providers.cloudflare_worker_image.requests.post", return_value=response):
            with self.assertRaisesRegex(requests.HTTPError, "worker returned an error"):
                CloudflareWorkerImageProvider().generate("prompt", Path(directory) / "scene.png")

    def test_factory_prefers_pollinations_then_worker_then_gemini(self):
        from multimedia.providers.pollinations_image import PollinationsImageProvider

        # Pollinations takes priority when configured
        with patch("multimedia.providers.image_factory.POLLINATIONS_API_KEY", "sk_test"), \
             patch("multimedia.providers.image_factory.CF_WORKER_URL", "https://images.example.workers.dev"):
            provider = configured_image_provider()
            self.assertIsInstance(provider, PollinationsImageProvider)

        # Without Pollinations, Cloudflare takes priority
        with patch("multimedia.providers.image_factory.POLLINATIONS_API_KEY", ""), \
             patch("multimedia.providers.image_factory.CF_WORKER_URL", "https://images.example.workers.dev"):
            provider = configured_image_provider()
            self.assertIsInstance(provider, CloudflareWorkerImageProvider)

        # Without both, Gemini is fallback
        with patch("multimedia.providers.image_factory.POLLINATIONS_API_KEY", ""), \
             patch("multimedia.providers.image_factory.CF_WORKER_URL", ""), \
             patch("multimedia.providers.image_factory.GeminiImageProvider") as gemini_provider:
            self.assertIs(configured_image_provider(), gemini_provider.return_value)


if __name__ == "__main__":
    unittest.main()
