"""Tests for utils/media_utils.py"""
import pytest
from getvp.utils.media_utils import infer_media_type, infer_media_type_from_format


class TestInferMediaTypeFromFormat:
    def test_video_format(self):
        assert infer_media_type_from_format("video", "youtube") == "video"

    def test_combined_format(self):
        assert infer_media_type_from_format("combined", "youtube") == "video"

    def test_audio_format(self):
        assert infer_media_type_from_format("audio", "youtube") == "audio"

    def test_instagram_default(self):
        assert infer_media_type_from_format("", "instagram") == "image"

    def test_unknown_format_defaults_video(self):
        assert infer_media_type_from_format("something", "twitter") == "video"


class TestInferMediaTypeFromPath:
    def test_empty_path(self):
        assert infer_media_type("", "youtube") == ""

    def test_nonexistent_path_instagram_fallback(self):
        assert infer_media_type("/nonexistent/path.mp4", "instagram") == "mixed"

    def test_nonexistent_path_other(self):
        assert infer_media_type("/nonexistent/path.mp4", "youtube") == ""
