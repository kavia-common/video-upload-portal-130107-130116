import os
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Constants
UPLOAD_DIR = Path("./upload").resolve()
MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500MB


class UploadResponse(BaseModel):
    """Response model for successful upload."""
    filename: str = Field(..., description="Stored file name")
    size_bytes: int = Field(..., description="Size of the uploaded file in bytes")
    message: str = Field(..., description="Informational message about the upload result")


class ErrorResponse(BaseModel):
    """Error response model."""
    detail: str = Field(..., description="Description of the error that occurred")


# Configure FastAPI application with OpenAPI metadata and tags
app = FastAPI(
    title="Video Upload Backend",
    description=(
        "A FastAPI service exposing REST endpoints for uploading videos.\n"
        "- Accepts multipart/form-data uploads via POST /upload\n"
        "- Enforces a maximum file size of 500MB\n"
        "- Saves uploaded files to the ./upload directory"
    ),
    version="1.0.0",
    contact={"name": "Video Upload Service"},
    openapi_tags=[
        {"name": "health", "description": "Service health and diagnostics"},
        {"name": "upload", "description": "Endpoints for uploading video files"},
    ],
)

# CORS configuration (no auth required, allow all origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ensure_upload_dir_exists() -> None:
    """
    Ensure the upload directory exists; create it if missing.
    Raises HTTPException if directory cannot be created.
    """
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to prepare upload directory: {exc}",
        ) from exc


def _safe_filename(filename: str) -> str:
    """
    Sanitize the provided filename to avoid directory traversal and unsupported chars.
    """
    # Keep only the name component and strip problematic characters
    name = os.path.basename(filename)
    # Replace path separators and control characters
    name = name.replace("/", "_").replace("\\", "_")
    # Avoid empty names
    return name or "uploaded_file"


def _compute_stream_size_and_save(upload_file: UploadFile, target_path: Path) -> int:
    """
    Stream the incoming file to disk while tracking size to enforce the limit.
    Returns the final size in bytes or raises HTTPException on violations or IO errors.
    """
    total = 0
    # Write in chunks to avoid loading entire file into memory
    try:
        with target_path.open("wb") as out_file:
            while True:
                chunk = upload_file.file.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_FILE_SIZE_BYTES:
                    # Stop writing and remove partial file
                    out_file.close()
                    try:
                        target_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File too large. Maximum allowed size is 500MB.",
                    )
                out_file.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        # Clean up partial file on unexpected errors
        try:
            target_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store the uploaded file: {exc}",
        ) from exc
    finally:
        # Reset the file pointer for safety (though we are done with it)
        try:
            upload_file.file.seek(0)
        except Exception:
            pass

    return total


# PUBLIC_INTERFACE
@app.get(
    "/",
    summary="Health Check",
    description="Verify the API is running and responsive.",
    tags=["health"],
    response_model=dict,
)
def health_check():
    """Simple health check endpoint returning a message."""
    return {"message": "Healthy"}


# PUBLIC_INTERFACE
@app.post(
    "/upload",
    summary="Upload a video file",
    description=(
        "Accepts a video upload via multipart/form-data. The file must be at most 500MB.\n"
        "On success, the file is saved under the ./upload directory on the server."
    ),
    tags=["upload"],
    response_model=UploadResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        413: {"model": ErrorResponse, "description": "Payload too large"},
        500: {"model": ErrorResponse, "description": "Server/storage error"},
    },
)
async def upload_video(file: UploadFile = File(..., description="Video file to upload")) -> UploadResponse:
    """
    Uploads a video file with a maximum size of 500MB and stores it in the ./upload directory.

    Parameters:
    - file (UploadFile): The uploaded video file via multipart/form-data.

    Returns:
    - UploadResponse: Information about the stored file including name and size.

    Errors:
    - 413 if the file exceeds 500MB
    - 500 if the server cannot persist the file
    """
    _ensure_upload_dir_exists()

    # Basic filename validation and sanitization
    original_name = file.filename or "uploaded_file"
    safe_name = _safe_filename(original_name)
    target_path = UPLOAD_DIR / safe_name

    # If a file with same name exists, create a unique name to prevent overwrite
    if target_path.exists():
        stem = target_path.stem
        suffix = target_path.suffix
        counter = 1
        while True:
            candidate = UPLOAD_DIR / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                target_path = candidate
                break
            counter += 1

    # Stream save with size enforcement
    size_bytes = _compute_stream_size_and_save(file, target_path)

    return UploadResponse(
        filename=target_path.name,
        size_bytes=size_bytes,
        message="Upload successful",
    )
