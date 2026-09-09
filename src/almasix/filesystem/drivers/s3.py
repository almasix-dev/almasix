"""S3-compatible disk driver (optional ``almasix[s3]`` / boto3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any, BinaryIO
from urllib.parse import quote

from almasix.filesystem.adapter import Visibility, coerce_bytes, normalize_path


class S3Adapter:
    """Thin boto3 wrapper. Requires ``boto3`` (``pip install 'almasix[s3]'``)."""

    def __init__(
        self,
        *,
        bucket: str,
        client: Any | None = None,
        root: str = "",
        url: str | None = None,
        visibility: Visibility = "private",
        region: str | None = None,
        endpoint: str | None = None,
        key: str | None = None,
        secret: str | None = None,
        **options: Any,
    ) -> None:
        del options
        if client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - exercised when boto3 absent
                raise RuntimeError(
                    "S3 disk requires boto3. Install with: pip install 'almasix[s3]'"
                ) from exc
            session_kwargs: dict[str, Any] = {}
            if key and secret:
                session_kwargs["aws_access_key_id"] = key
                session_kwargs["aws_secret_access_key"] = secret
            if region:
                session_kwargs["region_name"] = region
            session = boto3.session.Session(**session_kwargs)
            client_kwargs: dict[str, Any] = {}
            if endpoint:
                client_kwargs["endpoint_url"] = endpoint
            client = session.client("s3", **client_kwargs)
        self.client = client
        self.bucket = bucket
        self.root = normalize_path(root)
        self.base_url = (url or "").rstrip("/")
        self.default_visibility = visibility

    def _key(self, path: str) -> str:
        relative = normalize_path(path)
        if self.root:
            return f"{self.root}/{relative}" if relative else self.root
        return relative

    def put(
        self,
        path: str,
        contents: bytes | str | BinaryIO,
        *,
        visibility: Visibility | None = None,
    ) -> str:
        key = self._key(path)
        extra: dict[str, Any] = {}
        vis = visibility or self.default_visibility
        if vis == "public":
            extra["ACL"] = "public-read"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=coerce_bytes(contents), **extra)
        return normalize_path(path)

    def get(self, path: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=self._key(path))
        return response["Body"].read()

    def read_stream(self, path: str) -> BinaryIO:
        return BytesIO(self.get(path))

    def exists(self, path: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(path))
            return True
        except Exception:
            return False

    def delete(self, path: str) -> bool:
        self.client.delete_object(Bucket=self.bucket, Key=self._key(path))
        return True

    def copy(self, source: str, destination: str) -> bool:
        self.client.copy_object(
            Bucket=self.bucket,
            CopySource={"Bucket": self.bucket, "Key": self._key(source)},
            Key=self._key(destination),
        )
        return True

    def move(self, source: str, destination: str) -> bool:
        self.copy(source, destination)
        self.delete(source)
        return True

    def size(self, path: str) -> int:
        response = self.client.head_object(Bucket=self.bucket, Key=self._key(path))
        return int(response["ContentLength"])

    def files(self, directory: str = "", *, recursive: bool = False) -> list[str]:
        prefix = self._key(directory)
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        paginator = self.client.get_paginator("list_objects_v2")
        results: list[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents") or []:
                key = item["Key"]
                relative = key[len(self.root) + 1 :] if self.root else key
                if not recursive and "/" in relative[len(normalize_path(directory)) + 1 :]:
                    continue
                results.append(normalize_path(relative))
        return results

    def directories(self, directory: str = "", *, recursive: bool = False) -> list[str]:
        del recursive
        prefix = self._key(directory)
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix, Delimiter="/")
        results: list[str] = []
        for item in response.get("CommonPrefixes") or []:
            key = item["Prefix"].rstrip("/")
            relative = key[len(self.root) + 1 :] if self.root else key
            results.append(normalize_path(relative))
        return results

    def make_directory(self, path: str) -> bool:
        key = self._key(path).rstrip("/") + "/"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=b"")
        return True

    def delete_directory(self, path: str) -> bool:
        for file_path in self.files(path, recursive=True):
            self.delete(file_path)
        return True

    def url(self, path: str) -> str:
        key = self._key(path)
        encoded = quote(key, safe="/")
        if self.base_url:
            return f"{self.base_url}/{encoded}"
        return f"https://{self.bucket}.s3.amazonaws.com/{encoded}"

    def temporary_url(self, path: str, expiration: Any, **options: Any) -> str:
        if isinstance(expiration, timedelta):
            seconds = int(expiration.total_seconds())
        elif isinstance(expiration, datetime):
            now = datetime.now(UTC)
            target = expiration if expiration.tzinfo else expiration.replace(tzinfo=UTC)
            seconds = max(1, int((target - now).total_seconds()))
        else:
            seconds = int(expiration)
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": self._key(path), **options},
            ExpiresIn=seconds,
        )

    def set_visibility(self, path: str, visibility: Visibility) -> bool:
        acl = "public-read" if visibility == "public" else "private"
        self.client.put_object_acl(Bucket=self.bucket, Key=self._key(path), ACL=acl)
        return True

    def get_visibility(self, path: str) -> Visibility:
        try:
            acl = self.client.get_object_acl(Bucket=self.bucket, Key=self._key(path))
            for grant in acl.get("Grants") or []:
                if grant.get("Permission") == "READ":
                    return "public"
        except Exception:
            pass
        return self.default_visibility
