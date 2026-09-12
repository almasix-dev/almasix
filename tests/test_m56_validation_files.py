"""M56 — file / image / mimes rules against UploadedFile duck types."""

from __future__ import annotations

from almasix.validation import validator


class _FakeUpload:
    def __init__(self, filename: str, content_type: str, size: int = 10) -> None:
        self.filename = filename
        self.content_type = content_type
        self.size = size


def test_file_image_mimes_extensions() -> None:
    upload = _FakeUpload("photo.png", "image/png", size=2048)
    assert validator({"f": upload}, {"f": "file"}).passes()
    assert validator({"f": upload}, {"f": "image"}).passes()
    assert validator({"f": upload}, {"f": "mimes:png,jpg"}).passes()
    assert validator({"f": upload}, {"f": "mimes:pdf"}).fails()
    assert validator({"f": upload}, {"f": "extensions:png"}).passes()
    assert validator({"f": upload}, {"f": "mimetypes:image/png"}).passes()
    assert validator({"f": "not-a-file"}, {"f": "file"}).fails()
