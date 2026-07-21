"""File Serving Router

Serves generated analysis files (Excel, PowerPoint, etc.) for download.

Author: Utku Gulbardak
Date: 2025-12-03
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException  # type: ignore[import-untyped]
from fastapi.responses import FileResponse  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)
router = APIRouter()

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent


def _normalize_file_path(file_path: str) -> Path:
    """Normalize file path to relative path from project root.

    Handles both absolute and relative paths.
    """
    path = Path(file_path)

    # If absolute path, convert to relative
    if path.is_absolute():
        try:
            # Try to make it relative to project root
            relative_path = path.relative_to(PROJECT_ROOT)
            return PROJECT_ROOT / relative_path
        except ValueError:
            # If not under project root, return as-is (security risk, but handle gracefully)
            logger.warning(f"File path outside project root: {file_path}")
            return path
    else:
        # Already relative, resolve from project root
        return PROJECT_ROOT / path


def _is_safe_path(file_path: Path) -> bool:
    """Check if file path is safe to serve.

    Only allows files under output/ directory.
    """
    try:
        resolved = file_path.resolve()
        project_output = (PROJECT_ROOT / "output").resolve()

        # Check if file is under output directory
        return str(resolved).startswith(str(project_output))
    except Exception:
        return False


@router.get(
    "/files/{file_path:path}", tags=["Files"], summary="Download Generated File"
)
async def download_file(file_path: str):
    """Download a generated analysis file (Excel, PowerPoint, etc.).

    Only serves files from the output/ directory for security.

    Args:
        file_path: Relative path from project root (e.g., "output/roi/report.xlsx")

    Returns:
        File download response
    """
    try:
        # Normalize and validate path
        normalized_path = _normalize_file_path(file_path)

        # Security check: only serve files from output directory
        if not _is_safe_path(normalized_path):
            raise HTTPException(
                status_code=403,
                detail="Access denied: File must be in output directory",
            )

        # Check if file exists
        if not normalized_path.exists():
            logger.warning(f"File not found: {normalized_path}")
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

        if not normalized_path.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")

        # Determine media type based on extension
        media_type_map = {
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".ppt": "application/vnd.ms-powerpoint",
            ".pdf": "application/pdf",
            ".csv": "text/csv",
            ".html": "text/html",
            ".json": "application/json",
        }

        extension = normalized_path.suffix.lower()
        media_type = media_type_map.get(extension, "application/octet-stream")

        logger.info(f"Serving file: {normalized_path}")
        return FileResponse(
            path=str(normalized_path),
            filename=normalized_path.name,
            media_type=media_type,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error serving file: {str(e)}")


@router.get("/", tags=["Files"], summary="File Service Info")
async def files_info():
    """Get information about the file serving service."""
    return {
        "service": "File Serving",
        "status": "running",
        "version": "1.0.0",
        "endpoint": "/files/{file_path}",
        "description": "Serves generated analysis files (Excel, PowerPoint, etc.)",
        "security": "Only files in output/ directory are accessible",
        "example": "/files/output/roi/report.xlsx",
    }
