"""Phase 3 FileRecord model tests."""

import pytest
from django.contrib.auth import get_user_model

from files.models import FileRecord

User = get_user_model()


@pytest.fixture
def file_owner(db):
    return User.objects.create_user(
        username="file-owner",
        email="file-owner@example.com",
        password="File-Owner-Passphrase-42",
    )


@pytest.mark.django_db
def test_file_record_creation_and_owner_relationship(file_owner) -> None:
    record = FileRecord.objects.create(
        filename="generated.pdf",
        original_filename="Report.PDF",
        file_path="files/generated.pdf",
        file_size=2048,
        mime_type="application/pdf",
        description="Quarterly report",
        uploaded_by=file_owner,
    )

    assert record.pk is not None
    assert record.uploaded_by == file_owner
    assert list(file_owner.uploaded_files.all()) == [record]
    assert str(record) == "Report.PDF"


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("archive.tar.ZIP", "zip"),
        ("notes", "unknown"),
        ("photo.JpG", "jpg"),
    ],
)
def test_file_type_uses_normalized_extension(filename: str, expected: str) -> None:
    record = FileRecord(original_filename=filename)

    assert record.file_type == expected


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (0, "0 bytes"),
        (1, "1 byte"),
        (1023, "1023 bytes"),
        (1024, "1.0 KB"),
        (1024 * 1024, "1.0 MB"),
        (1024 * 1024 * 1024, "1.0 GB"),
        (1024**4, "1.0 TB"),
    ],
)
def test_human_readable_file_size(size: int, expected: str) -> None:
    record = FileRecord(file_size=size)

    assert record.get_file_size_display() == expected
