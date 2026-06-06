"""Tests for utils/media_utils.py"""
import pytest
from lumio.utils.media_utils import infer_media_type


class TestInferMediaTypeFromPath:
    def test_empty_path(self):
        assert infer_media_type("", "youtube") == ""

    def test_nonexistent_path_instagram_fallback(self):
        assert infer_media_type("/nonexistent/path.mp4", "instagram") == "mixed"

    def test_nonexistent_path_other(self):
        assert infer_media_type("/nonexistent/path.mp4", "youtube") == ""
