"""Validated, owner-scoped file searching and ordering."""

from dataclasses import dataclass
from datetime import date
from typing import Mapping

from django.contrib.auth.base_user import AbstractBaseUser
from django.db.models import Case, CharField, Q, QuerySet, Value, When
from django.db.models.functions import Lower, Reverse, StrIndex, Substr
from django.utils.dateparse import parse_date

from .models import FileRecord
from .validators import FileValidator


class FileQueryValidationError(ValueError):
    """Describe one query parameter that cannot be safely applied."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.errors = {field: [message]}


@dataclass(frozen=True)
class FileQueryParameters:
    """Normalized collection query parameters."""

    search: str | None = None
    file_type: str | None = None
    mime_type: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    min_size: int | None = None
    max_size: int | None = None
    sort: str = "-upload_date"
    page: int = 1
    page_size: int = 20

    MAX_PAGE_SIZE = 100
    MAX_SEARCH_LENGTH = 200
    SORT_FIELDS = {"name", "upload_date", "file_size", "file_type"}
    QUERY_FIELDS = {
        "search",
        "file_type",
        "mime_type",
        "date_from",
        "date_to",
        "min_size",
        "max_size",
        "sort",
        "page",
        "page_size",
    }

    @classmethod
    def from_query_params(
        cls, query_params: Mapping[str, str]
    ) -> "FileQueryParameters":
        unknown_fields = set(query_params) - cls.QUERY_FIELDS
        if unknown_fields:
            field = sorted(unknown_fields)[0]
            raise FileQueryValidationError(field, "Unsupported query parameter.")

        search = cls._optional_text(query_params, "search")
        if search and len(search) > cls.MAX_SEARCH_LENGTH:
            raise FileQueryValidationError(
                "search",
                f"Search must not exceed {cls.MAX_SEARCH_LENGTH} characters.",
            )

        file_type = cls._optional_text(query_params, "file_type")
        if file_type:
            file_type = file_type.removeprefix(".").lower()
            if file_type not in FileValidator.ALLOWED_EXTENSIONS:
                raise FileQueryValidationError("file_type", "Unsupported file type.")

        mime_type = cls._optional_text(query_params, "mime_type")
        if mime_type and len(mime_type) > 100:
            raise FileQueryValidationError(
                "mime_type",
                "MIME type must not exceed 100 characters.",
            )

        date_from = cls._optional_date(query_params, "date_from")
        date_to = cls._optional_date(query_params, "date_to")
        if date_from and date_to and date_from > date_to:
            raise FileQueryValidationError(
                "date_to",
                "date_to must be on or after date_from.",
            )

        min_size = cls._optional_nonnegative_int(query_params, "min_size")
        max_size = cls._optional_nonnegative_int(query_params, "max_size")
        if min_size is not None and max_size is not None and min_size > max_size:
            raise FileQueryValidationError(
                "max_size",
                "max_size must be greater than or equal to min_size.",
            )

        sort = cls._optional_text(query_params, "sort") or "-upload_date"
        sort_field = sort.removeprefix("-")
        if sort_field not in cls.SORT_FIELDS:
            raise FileQueryValidationError("sort", "Unsupported sort field.")

        page = cls._positive_int(query_params, "page", default=1)
        requested_page_size = cls._positive_int(
            query_params,
            "page_size",
            default=20,
        )

        return cls(
            search=search,
            file_type=file_type,
            mime_type=mime_type,
            date_from=date_from,
            date_to=date_to,
            min_size=min_size,
            max_size=max_size,
            sort=sort,
            page=page,
            page_size=min(requested_page_size, cls.MAX_PAGE_SIZE),
        )

    @staticmethod
    def _optional_text(query_params: Mapping[str, str], field: str) -> str | None:
        value = query_params.get(field)
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @classmethod
    def _positive_int(
        cls,
        query_params: Mapping[str, str],
        field: str,
        *,
        default: int,
    ) -> int:
        value = cls._optional_text(query_params, field)
        if value is None:
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise FileQueryValidationError(
                field, "A positive integer is required."
            ) from exc
        if parsed <= 0:
            raise FileQueryValidationError(field, "A positive integer is required.")
        return parsed

    @classmethod
    def _optional_nonnegative_int(
        cls,
        query_params: Mapping[str, str],
        field: str,
    ) -> int | None:
        value = cls._optional_text(query_params, field)
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise FileQueryValidationError(
                field,
                "A non-negative integer is required.",
            ) from exc
        if parsed < 0:
            raise FileQueryValidationError(
                field,
                "A non-negative integer is required.",
            )
        return parsed

    @classmethod
    def _optional_date(
        cls,
        query_params: Mapping[str, str],
        field: str,
    ) -> date | None:
        value = cls._optional_text(query_params, field)
        if value is None:
            return None
        parsed = parse_date(value)
        if parsed is None:
            raise FileQueryValidationError(
                field, "Use a valid date in YYYY-MM-DD format."
            )
        return parsed


class FileQueryService:
    """Build a safe queryset with ownership applied before client filters."""

    @staticmethod
    def build_queryset(
        user: AbstractBaseUser,
        parameters: FileQueryParameters,
    ) -> QuerySet[FileRecord]:
        queryset = FileRecord.objects.filter(uploaded_by=user)

        if parameters.search:
            queryset = queryset.filter(
                Q(filename__icontains=parameters.search)
                | Q(original_filename__icontains=parameters.search)
                | Q(description__icontains=parameters.search)
            )
        if parameters.file_type:
            queryset = queryset.filter(
                original_filename__iendswith=f".{parameters.file_type}"
            )
        if parameters.mime_type:
            queryset = queryset.filter(mime_type__iexact=parameters.mime_type)
        if parameters.date_from:
            queryset = queryset.filter(upload_date__date__gte=parameters.date_from)
        if parameters.date_to:
            queryset = queryset.filter(upload_date__date__lte=parameters.date_to)
        if parameters.min_size is not None:
            queryset = queryset.filter(file_size__gte=parameters.min_size)
        if parameters.max_size is not None:
            queryset = queryset.filter(file_size__lte=parameters.max_size)

        descending = parameters.sort.startswith("-")
        sort_field = parameters.sort.removeprefix("-")
        order_prefix = "-" if descending else ""

        if sort_field == "name":
            queryset = queryset.annotate(_name_sort=Lower("original_filename"))
            ordering_field = "_name_sort"
        elif sort_field == "file_type":
            reverse_name = Reverse("original_filename")
            suffix = Lower(
                Reverse(
                    Substr(
                        reverse_name,
                        1,
                        StrIndex(reverse_name, Value(".")) - 1,
                    )
                )
            )
            queryset = queryset.annotate(
                _file_type_sort=Case(
                    When(original_filename__contains=".", then=suffix),
                    default=Value(""),
                    output_field=CharField(),
                )
            )
            ordering_field = "_file_type_sort"
        else:
            ordering_field = sort_field

        return queryset.order_by(
            f"{order_prefix}{ordering_field}",
            f"{order_prefix}id",
        )
