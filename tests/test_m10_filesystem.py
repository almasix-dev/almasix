"""M10 filesystem tests — Storage, local/memory disks, storage:link."""

from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from almasix.console.kernel import ConsoleKernel
from almasix.filesystem import Storage, storage
from almasix.filesystem.adapter import normalize_path
from almasix.filesystem.drivers.local import LocalAdapter
from almasix.filesystem.drivers.memory import MemoryAdapter
from almasix.filesystem.helpers import default_filesystems_config
from almasix.filesystem.manager import StorageManager
from almasix.filesystem.provider import FilesystemServiceProvider
from almasix.framework import Application
from tests.support import purge_generated_app_modules


def test_normalize_path() -> None:
    assert normalize_path("/a/../b/./c") == "b/c"
    assert normalize_path("\\\\x\\\\y") == "x/y"


def test_memory_disk_crud() -> None:
    disk = MemoryAdapter()
    disk.put("notes/hello.txt", "hi")
    assert disk.exists("notes/hello.txt")
    assert disk.get("notes/hello.txt") == b"hi"
    assert disk.get_visibility("notes/hello.txt") == "private"
    disk.set_visibility("notes/hello.txt", "public")
    assert disk.get_visibility("notes/hello.txt") == "public"
    assert "notes/hello.txt" in disk.files("notes")
    disk.copy("notes/hello.txt", "notes/copy.txt")
    assert disk.exists("notes/copy.txt")
    disk.move("notes/copy.txt", "notes/moved.txt")
    assert disk.exists("notes/moved.txt")
    assert not disk.exists("notes/copy.txt")
    assert disk.url("notes/hello.txt").startswith("/memory/")
    with pytest.raises(RuntimeError, match="temporary URLs"):
        disk.temporary_url("notes/hello.txt", timedelta(minutes=5))
    assert disk.delete("notes/hello.txt")
    assert not disk.exists("notes/hello.txt")


def test_local_disk(tmp_path: Path) -> None:
    adapter = LocalAdapter(tmp_path / "app", url_prefix="/storage")
    adapter.put("a.txt", b"one")
    assert adapter.get("a.txt") == b"one"
    assert adapter.size("a.txt") == 3
    assert adapter.path("a.txt").endswith("a.txt")
    stream = adapter.read_stream("a.txt")
    assert stream.read() == b"one"
    adapter.put("nested/b.txt", BytesIO(b"two"), visibility="public")
    assert adapter.files("", recursive=True) == ["a.txt", "nested/b.txt"]
    assert "nested" in adapter.directories()
    adapter.make_directory("empty")
    assert adapter.exists("empty") or "empty" in adapter.directories()
    assert adapter.url("a.txt") == "/storage/a.txt"
    adapter.copy("a.txt", "c.txt")
    adapter.move("c.txt", "d.txt")
    assert adapter.exists("d.txt")
    adapter.delete("d.txt")
    adapter.delete_directory("nested")
    assert not adapter.exists("nested/b.txt")


def test_storage_facade_and_helper(tmp_path: Path) -> None:
    manager = StorageManager(
        config={
            "default": "memory",
            "disks": {"memory": {"driver": "memory"}},
        }
    )
    Storage.set_manager(manager)
    Storage.put("x.txt", "data")
    assert Storage.exists("x.txt")
    assert Storage.get("x.txt") == b"data"
    assert storage().exists("x.txt")
    Storage.copy("x.txt", "y.txt")
    Storage.move("y.txt", "z.txt")
    assert Storage.exists("z.txt")
    Storage.delete("x.txt", "z.txt")
    assert Storage.missing("x.txt")
    Storage.set_manager(None)


def test_storage_manager_local_and_public(tmp_path: Path) -> None:
    app = Application(tmp_path)
    manager = StorageManager(
        app,
        {
            "default": "local",
            "disks": {
                "local": {"driver": "local", "root": str(tmp_path / "local")},
                "public": {
                    "driver": "local",
                    "root": str(tmp_path / "public"),
                    "url": "/storage",
                    "visibility": "public",
                },
            },
        },
    )
    local = manager.disk("local")
    local.put("f.txt", "ok")
    assert local.get_string("f.txt") == "ok"
    assert local.path("f.txt").startswith(str(tmp_path))
    public = manager.disk("public")
    public.put("p.txt", "pub")
    assert public.url("p.txt") == "/storage/p.txt"


def test_s3_adapter_with_mock_client() -> None:
    from almasix.filesystem.drivers.s3 import S3Adapter

    client = MagicMock()
    client.get_object.return_value = {"Body": BytesIO(b"s3")}
    client.head_object.return_value = {"ContentLength": 2}
    client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "root/a.txt"}]}
    ]
    client.list_objects_v2.return_value = {"CommonPrefixes": [{"Prefix": "root/dir/"}]}
    client.generate_presigned_url.return_value = "https://signed.example/a"
    client.get_object_acl.return_value = {"Grants": [{"Permission": "READ"}]}

    adapter = S3Adapter(bucket="bucket", client=client, root="root", url="https://cdn.example")
    adapter.put("a.txt", b"s3", visibility="public")
    assert adapter.get("a.txt") == b"s3"
    assert adapter.exists("a.txt")
    assert adapter.size("a.txt") == 2
    assert adapter.url("a.txt").startswith("https://cdn.example/")
    assert adapter.temporary_url("a.txt", 60) == "https://signed.example/a"
    assert adapter.get_visibility("a.txt") == "public"
    adapter.copy("a.txt", "b.txt")
    adapter.move("b.txt", "c.txt")
    adapter.make_directory("dir")
    adapter.files("", recursive=True)
    adapter.directories()
    adapter.delete("c.txt")
    adapter.delete_directory("dir")


def test_s3_requires_boto3_without_client() -> None:
    from almasix.filesystem.drivers.s3 import S3Adapter

    # If boto3 is installed this still constructs; force ImportError path via monkeypatch.
    import almasix.filesystem.drivers.s3 as s3_mod
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "boto3":
            raise ImportError("no boto3")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import  # type: ignore[assignment]
    try:
        with pytest.raises(RuntimeError, match="boto3"):
            S3Adapter(bucket="b")
    finally:
        builtins.__import__ = real_import  # type: ignore[assignment]
    del s3_mod


def test_filesystem_provider_and_storage_link(tmp_path: Path) -> None:
    purge_generated_app_modules()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "FS", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "filesystems.py").write_text(
        "config = "
        + repr(
            {
                **default_filesystems_config(str(tmp_path)),
                "disks": {
                    "local": {
                        "driver": "local",
                        "root": str(tmp_path / "storage" / "app"),
                    },
                    "public": {
                        "driver": "local",
                        "root": str(tmp_path / "storage" / "app" / "public"),
                        "url": "/storage",
                    },
                    "memory": {"driver": "memory"},
                },
                "links": {"public/storage": "storage/app/public"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    app = Application(tmp_path)
    app.load_configuration()
    FilesystemServiceProvider(app).register()
    FilesystemServiceProvider(app).boot()
    Storage.disk("local").put("hello.txt", "world")
    assert Storage.exists("hello.txt")

    kernel = ConsoleKernel(app)
    kernel.discover()
    assert "storage:link" in kernel.commands
    code = kernel.run_command("storage:link", options={"relative": False, "force": False})
    assert code == 0
    link = tmp_path / "public" / "storage"
    assert link.is_symlink() or link.exists()


def test_put_file_sync(tmp_path: Path) -> None:
    manager = StorageManager(
        config={"default": "local", "disks": {"local": {"driver": "local", "root": str(tmp_path)}}}
    )
    disk = manager.disk()
    path = tmp_path / "upload.bin"
    path.write_bytes(b"abc")
    stored = disk.put_file("uploads", path)
    assert stored.endswith("upload.bin")
    assert disk.get(stored) == b"abc"
