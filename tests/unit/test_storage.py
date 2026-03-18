"""Tests for S3 raw HTML + manifest storage."""

import json
from unittest.mock import MagicMock, patch

from rag.storage import S3Storage


class TestS3Storage:
    @patch("rag.storage.boto3")
    def test_store_page_uploads_html(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        storage = S3Storage(bucket_name="test-bucket", region="us-east-1")
        storage.store_page(
            workspace_id="W456",
            url="https://example.com/about",
            raw_html="<html>content</html>",
        )

        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "test-bucket"
        assert "W456" in call_kwargs["Key"]
        assert call_kwargs["ContentType"] == "text/html"

    @patch("rag.storage.boto3")
    def test_store_page_generates_safe_key(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        storage = S3Storage(bucket_name="test-bucket", region="us-east-1")
        storage.store_page(
            workspace_id="W456",
            url="https://example.com/about?q=test#frag",
            raw_html="<html></html>",
        )

        call_kwargs = mock_client.put_object.call_args[1]
        key = call_kwargs["Key"]
        # Key should not contain query params or fragments
        assert "?" not in key
        assert "#" not in key
        assert key.endswith(".html")

    @patch("rag.storage.boto3")
    def test_update_manifest(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        # Simulate no existing manifest
        mock_client.get_object.side_effect = Exception("NoSuchKey")

        storage = S3Storage(bucket_name="test-bucket", region="us-east-1")
        storage.update_manifest(
            workspace_id="W456",
            url="https://example.com/about",
            s3_key="W456/pages/about.html",
            content_hash="abc123",
        )

        put_calls = [
            c
            for c in mock_client.put_object.call_args_list
            if "manifest.json" in str(c)
        ]
        assert len(put_calls) == 1

    @patch("rag.storage.boto3")
    def test_get_manifest_returns_dict(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        manifest_data = {"pages": [{"url": "https://example.com", "s3_key": "k"}]}
        mock_client.get_object.return_value = {
            "Body": MagicMock(
                read=MagicMock(return_value=json.dumps(manifest_data).encode())
            )
        }

        storage = S3Storage(bucket_name="test-bucket", region="us-east-1")
        manifest = storage.get_manifest(workspace_id="W456")
        assert "pages" in manifest
        assert len(manifest["pages"]) == 1

    @patch("rag.storage.boto3")
    def test_client_created_once(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        S3Storage(bucket_name="test-bucket", region="us-east-1")
        mock_boto3.client.assert_called_once()
