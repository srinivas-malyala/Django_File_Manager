"""Phase 5 owner-scoped search, filtering, sorting, and pagination tests."""

from datetime import datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from files.models import FileRecord

User = get_user_model()
PASSWORD = "Search-Passphrase-42"


@pytest.fixture
def search_users(db):
    owner = User.objects.create_user(
        username="search-owner",
        email="search-owner@example.com",
        password=PASSWORD,
    )
    other = User.objects.create_user(
        username="search-other",
        email="search-other@example.com",
        password=PASSWORD,
    )
    return owner, other


@pytest.fixture
def search_records(search_users):
    owner, other = search_users

    def create_record(
        name: str,
        *,
        size: int,
        mime_type: str,
        description: str,
        day: int,
        uploaded_by=owner,
    ) -> FileRecord:
        return FileRecord.objects.create(
            filename=f"generated-{name.lower()}",
            original_filename=name,
            file_path=f"files/generated-{name.lower()}",
            file_size=size,
            mime_type=mime_type,
            description=description,
            upload_date=timezone.make_aware(datetime(2026, 1, day, 12, 0)),
            uploaded_by=uploaded_by,
        )

    records = [
        create_record(
            "Alpha.PDF",
            size=100,
            mime_type="application/pdf",
            description="Quarterly financial document",
            day=1,
        ),
        create_record(
            "beta.txt",
            size=200,
            mime_type="text/plain",
            description="Meeting document notes",
            day=2,
        ),
        create_record(
            "gamma.csv",
            size=300,
            mime_type="text/csv",
            description="Exported inventory",
            day=3,
        ),
        create_record(
            "delta.JPG",
            size=400,
            mime_type="image/jpeg",
            description="Office photograph",
            day=4,
        ),
        create_record(
            "epsilon.docx",
            size=500,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            description="Policy draft",
            day=5,
        ),
    ]
    foreign_record = create_record(
        "secret-document.pdf",
        size=150,
        mime_type="application/pdf",
        description="Another user's document",
        day=3,
        uploaded_by=other,
    )
    return records, foreign_record


@pytest.fixture
def search_client(search_users) -> APIClient:
    owner, _ = search_users
    client = APIClient()
    client.force_authenticate(user=owner)
    return client


def result_names(response) -> list[str]:
    return [item["original_filename"] for item in response.json()["data"]["results"]]


@pytest.mark.django_db
def test_filename_search_is_case_insensitive(search_client, search_records) -> None:
    response = search_client.get(
        reverse("file_api:my_files"),
        {"search": "ALPHA"},
    )

    assert response.status_code == 200
    assert result_names(response) == ["Alpha.PDF"]


@pytest.mark.django_db
def test_description_search_is_owner_scoped(search_client, search_records) -> None:
    response = search_client.get(
        reverse("file_api:my_files"),
        {"search": "document", "sort": "name"},
    )

    assert response.status_code == 200
    assert result_names(response) == ["Alpha.PDF", "beta.txt"]
    assert "secret-document.pdf" not in result_names(response)


@pytest.mark.django_db
def test_file_type_filter_normalizes_dot_and_case(
    search_client, search_records
) -> None:
    response = search_client.get(
        reverse("file_api:my_files"),
        {"file_type": ".PDF"},
    )

    assert response.status_code == 200
    assert result_names(response) == ["Alpha.PDF"]


@pytest.mark.django_db
def test_mime_type_filter_is_case_insensitive(search_client, search_records) -> None:
    response = search_client.get(
        reverse("file_api:my_files"),
        {"mime_type": "TEXT/CSV"},
    )

    assert response.status_code == 200
    assert result_names(response) == ["gamma.csv"]


@pytest.mark.django_db
def test_date_range_filter_is_inclusive(search_client, search_records) -> None:
    response = search_client.get(
        reverse("file_api:my_files"),
        {"date_from": "2026-01-02", "date_to": "2026-01-04", "sort": "name"},
    )

    assert response.status_code == 200
    assert result_names(response) == ["beta.txt", "delta.JPG", "gamma.csv"]


@pytest.mark.django_db
def test_size_range_filter_is_inclusive(search_client, search_records) -> None:
    response = search_client.get(
        reverse("file_api:my_files"),
        {"min_size": "200", "max_size": "400", "sort": "file_size"},
    )

    assert response.status_code == 200
    assert result_names(response) == ["beta.txt", "gamma.csv", "delta.JPG"]


@pytest.mark.django_db
def test_combined_search_and_type_filter(search_client, search_records) -> None:
    response = search_client.get(
        reverse("file_api:my_files"),
        {"search": "document", "file_type": "txt"},
    )

    assert response.status_code == 200
    assert result_names(response) == ["beta.txt"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("name", ["Alpha.PDF", "beta.txt", "delta.JPG", "epsilon.docx", "gamma.csv"]),
        ("-name", ["gamma.csv", "epsilon.docx", "delta.JPG", "beta.txt", "Alpha.PDF"]),
        (
            "upload_date",
            ["Alpha.PDF", "beta.txt", "gamma.csv", "delta.JPG", "epsilon.docx"],
        ),
        (
            "-file_size",
            ["epsilon.docx", "delta.JPG", "gamma.csv", "beta.txt", "Alpha.PDF"],
        ),
        (
            "file_type",
            ["gamma.csv", "epsilon.docx", "delta.JPG", "Alpha.PDF", "beta.txt"],
        ),
    ],
)
def test_allowlisted_sorting(search_client, search_records, sort, expected) -> None:
    response = search_client.get(
        reverse("file_api:my_files"),
        {"sort": sort},
    )

    assert response.status_code == 200
    assert result_names(response) == expected


@pytest.mark.django_db
def test_default_sort_is_newest_first(search_client, search_records) -> None:
    response = search_client.get(reverse("file_api:my_files"))

    assert response.status_code == 200
    assert result_names(response) == [
        "epsilon.docx",
        "delta.JPG",
        "gamma.csv",
        "beta.txt",
        "Alpha.PDF",
    ]


@pytest.mark.django_db
def test_pagination_returns_bounded_metadata_and_links(
    search_client, search_records
) -> None:
    response = search_client.get(
        reverse("file_api:my_files"),
        {"sort": "name", "page": 2, "page_size": 2},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["count"] == 5
    assert data["page"] == 2
    assert data["page_size"] == 2
    assert data["total_pages"] == 3
    assert data["next"].endswith("sort=name&page=3&page_size=2")
    assert data["previous"].endswith("sort=name&page=1&page_size=2")
    assert result_names(response) == ["delta.JPG", "epsilon.docx"]


@pytest.mark.django_db
def test_page_size_is_capped_at_one_hundred(search_client, search_users) -> None:
    owner, _ = search_users
    FileRecord.objects.bulk_create(
        [
            FileRecord(
                filename=f"generated-{index}.txt",
                original_filename=f"record-{index:03}.txt",
                file_path=f"files/generated-{index}.txt",
                file_size=index,
                mime_type="text/plain",
                uploaded_by=owner,
            )
            for index in range(105)
        ]
    )

    response = search_client.get(
        reverse("file_api:my_files"),
        {"page_size": 500, "sort": "name"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["page_size"] == 100
    assert len(response.json()["data"]["results"]) == 100


@pytest.mark.django_db
def test_page_past_available_results_returns_404(search_client, search_records) -> None:
    response = search_client.get(
        reverse("file_api:my_files"),
        {"page": 99},
    )

    assert response.status_code == 404
    assert response.json()["errors"] == {"page": ["Page does not exist."]}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("query", "error_field"),
    [
        ({"sort": "uploaded_by"}, "sort"),
        ({"sort": "-file_path"}, "sort"),
        ({"page": "zero"}, "page"),
        ({"page": "0"}, "page"),
        ({"page_size": "-1"}, "page_size"),
        ({"file_type": "exe"}, "file_type"),
        ({"date_from": "not-a-date"}, "date_from"),
        ({"date_from": "2026-02-02", "date_to": "2026-01-01"}, "date_to"),
        ({"min_size": "-1"}, "min_size"),
        ({"min_size": "20", "max_size": "10"}, "max_size"),
        ({"search": "x" * 201}, "search"),
        ({"mime_type": "x" * 101}, "mime_type"),
        ({"uploaded_by": "1"}, "uploaded_by"),
    ],
)
def test_invalid_query_parameters_return_structured_error(
    search_client,
    query,
    error_field,
) -> None:
    response = search_client.get(reverse("file_api:my_files"), query)

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["message"] == "Invalid file query"
    assert error_field in payload["errors"]


@pytest.mark.django_db
def test_my_files_requires_authentication() -> None:
    response = APIClient().get(reverse("file_api:my_files"))

    assert response.status_code == 401
