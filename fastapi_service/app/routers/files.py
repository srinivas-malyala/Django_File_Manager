"""Owner-scoped file upload, search, metadata, download, and delete routes."""

from pathlib import Path
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse as DownloadResponse
from sqlalchemy import asc, desc, or_

from ..config import Settings
from ..dependencies import CurrentUser, Database, get_settings
from ..file_service import UploadValidationError, store_upload
from ..models import FileRecord
from ..responses import envelope
from ..schemas import FileResponse, FileUpdateRequest

router = APIRouter(prefix="/api/files", tags=["files"])


def serialize(record: FileRecord) -> dict:
    return FileResponse.model_validate(record).model_dump(mode="json")


def owned_file(db: Database, user: CurrentUser, file_id: str) -> FileRecord:
    record = (
        db.query(FileRecord)
        .filter(FileRecord.id == file_id, FileRecord.owner_id == user.id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="File not found.")
    return record


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: Annotated[UploadFile, File(description="Validated private file")],
    user: CurrentUser,
    db: Database,
    settings: Annotated[Settings, Depends(get_settings)],
    description: Annotated[str | None, Form(max_length=10_000)] = None,
):
    try:
        values = await store_upload(file, settings.upload_dir, settings.max_file_size)
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    file_id, stored_filename, original_filename, size, mime_type, final_path = values
    record = FileRecord(
        id=file_id,
        stored_filename=stored_filename,
        original_filename=original_filename,
        file_size=size,
        mime_type=mime_type,
        description=description,
        owner_id=user.id,
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        final_path.unlink(missing_ok=True)
        raise
    return envelope(serialize(record), "File uploaded successfully")


@router.get("")
@router.get("/my-files")
def list_files(
    user: CurrentUser,
    db: Database,
    search: Annotated[str | None, Query(max_length=200)] = None,
    file_type: Annotated[str | None, Query(max_length=20)] = None,
    mime_type: Annotated[str | None, Query(max_length=100)] = None,
    min_size: Annotated[int | None, Query(ge=0)] = None,
    max_size: Annotated[int | None, Query(ge=0)] = None,
    sort: Literal[
        "name",
        "-name",
        "upload_date",
        "-upload_date",
        "file_size",
        "-file_size",
        "file_type",
        "-file_type",
    ] = "-upload_date",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    if min_size is not None and max_size is not None and min_size > max_size:
        raise HTTPException(status_code=422, detail="min_size cannot exceed max_size.")
    query = db.query(FileRecord).filter(FileRecord.owner_id == user.id)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                FileRecord.original_filename.ilike(pattern),
                FileRecord.description.ilike(pattern),
            )
        )
    if file_type:
        extension = file_type.lower().lstrip(".")
        query = query.filter(FileRecord.original_filename.ilike(f"%.{extension}"))
    if mime_type:
        query = query.filter(FileRecord.mime_type.ilike(mime_type))
    if min_size is not None:
        query = query.filter(FileRecord.file_size >= min_size)
    if max_size is not None:
        query = query.filter(FileRecord.file_size <= max_size)
    sort_field = {
        "name": FileRecord.original_filename,
        "upload_date": FileRecord.upload_date,
        "file_size": FileRecord.file_size,
        "file_type": FileRecord.original_filename,
    }[sort.lstrip("-")]
    query = query.order_by(
        desc(sort_field) if sort.startswith("-") else asc(sort_field)
    )
    total = query.count()
    records = query.offset((page - 1) * page_size).limit(page_size).all()
    total_pages = max(1, (total + page_size - 1) // page_size)
    if page > total_pages and total:
        raise HTTPException(status_code=404, detail="Page does not exist.")
    return envelope(
        {
            "count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "results": [serialize(record) for record in records],
        },
        "Files retrieved successfully",
    )


@router.get("/{file_id}")
def get_file(file_id: str, user: CurrentUser, db: Database):
    return envelope(
        serialize(owned_file(db, user, file_id)), "File retrieved successfully"
    )


@router.put("/{file_id}")
def update_file(
    file_id: str, payload: FileUpdateRequest, user: CurrentUser, db: Database
):
    record = owned_file(db, user, file_id)
    record.description = payload.description
    db.commit()
    db.refresh(record)
    return envelope(serialize(record), "File metadata updated successfully")


@router.get("/{file_id}/download")
def download_file(
    file_id: str,
    user: CurrentUser,
    db: Database,
    settings: Annotated[Settings, Depends(get_settings)],
):
    record = owned_file(db, user, file_id)
    path = settings.upload_dir / record.stored_filename
    if not path.is_file():
        raise HTTPException(
            status_code=404, detail="Stored file content was not found."
        )
    return DownloadResponse(
        path,
        filename=record.original_filename,
        media_type=record.mime_type or "application/octet-stream",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{file_id}")
def delete_file(
    file_id: str,
    user: CurrentUser,
    db: Database,
    settings: Annotated[Settings, Depends(get_settings)],
):
    record = owned_file(db, user, file_id)
    path = settings.upload_dir / record.stored_filename
    if not path.is_file():
        raise HTTPException(
            status_code=404, detail="Stored file content was not found."
        )
    path.unlink()
    db.delete(record)
    db.commit()
    return envelope(None, "File deleted successfully")
