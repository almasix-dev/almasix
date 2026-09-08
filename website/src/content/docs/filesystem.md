---
title: File Storage
description: FlySystem-shaped Storage disks — local, memory, and S3-compatible.
---

## Storage

```python
from almasix.filesystem import Storage, storage

Storage.put("avatars/ada.png", contents)
Storage.disk("public").put("logo.svg", svg, visibility="public")
storage("local").get("avatars/ada.png")
Storage.url("avatars/ada.png")
Storage.exists("avatars/ada.png")
```

Config lives in `config/filesystems.py`. Default disks: `local`, `public`, `s3` (optional `almasix[s3]` / boto3), plus `memory` for tests.

## Public disk

```bash
python smith storage:link
```

Creates `public/storage` → `storage/app/public` (configurable via `filesystems.links`).

`temporary_url()` is supported on **S3-compatible** disks (presigned). Local and memory disks raise `RuntimeError` — generate your own signed URLs if needed.

## Uploads

```python
await Storage.disk("public").put_file_async("uploads", request.file("avatar"))
```

## Related

- [Cache](/cache/) — file cache under `storage/framework/cache`
- [Mail](/mail/) — attachments from Storage disks
- [Queues](/queues/) — job artifacts
