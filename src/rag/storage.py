"""S3 storage for raw HTML pages and manifests.

Stores scraped pages organized by workspace_id for re-indexing capability.
Manifest tracks URLs, scrape dates, and content hashes.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import boto3

logger = logging.getLogger(__name__)


class S3Storage:
    """S3 client for raw HTML and manifest storage.

    Bucket layout:
        {workspace_id}/pages/{sanitized_path}.html
        {workspace_id}/manifest.json
    """

    def __init__(self, *, bucket_name: str, region: str = "us-east-1") -> None:
        self._bucket = bucket_name
        self._client = boto3.client("s3", region_name=region)

    def store_page(self, *, workspace_id: str, url: str, raw_html: str) -> str:
        """Store raw HTML in S3 and return the S3 key.

        Args:
            workspace_id: Workspace identifier for namespace isolation.
            url: Original page URL.
            raw_html: Raw HTML content.

        Returns:
            The S3 key where the page was stored.
        """
        s3_key = _url_to_s3_key(workspace_id, url)

        self._client.put_object(
            Bucket=self._bucket,
            Key=s3_key,
            Body=raw_html.encode("utf-8"),
            ContentType="text/html",
        )

        logger.info("Stored page %s at s3://%s/%s", url, self._bucket, s3_key)
        return s3_key

    def update_manifest(
        self,
        *,
        workspace_id: str,
        url: str,
        s3_key: str,
        content_hash: str,
    ) -> None:
        """Add or update a page entry in the workspace manifest."""
        manifest = self.get_manifest(workspace_id=workspace_id)

        entry = {
            "url": url,
            "s3_key": s3_key,
            "content_hash": content_hash,
            "scraped_at": datetime.now(UTC).isoformat(),
        }

        # Update existing or append new
        existing = next((p for p in manifest.get("pages", []) if p["url"] == url), None)
        if existing:
            existing.update(entry)
        else:
            manifest.setdefault("pages", []).append(entry)

        manifest_key = f"{workspace_id}/manifest.json"
        self._client.put_object(
            Bucket=self._bucket,
            Key=manifest_key,
            Body=json.dumps(manifest, indent=2).encode("utf-8"),
            ContentType="application/json",
        )

    def get_manifest(self, *, workspace_id: str) -> dict[str, Any]:
        """Retrieve the workspace manifest. Returns empty dict if not found."""
        manifest_key = f"{workspace_id}/manifest.json"
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=manifest_key)
            result: dict[str, Any] = json.loads(response["Body"].read().decode("utf-8"))
            return result
        except Exception:
            return {"pages": []}


def _url_to_s3_key(workspace_id: str, url: str) -> str:
    """Convert a URL to a safe S3 key path."""
    parsed = urlparse(url)
    path = parsed.path.strip("/") or "index"
    # Remove query/fragment, replace special chars
    safe_path = path.replace("/", "_").replace(".", "_")
    # Add hash suffix for uniqueness
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{workspace_id}/pages/{safe_path}_{url_hash}.html"
