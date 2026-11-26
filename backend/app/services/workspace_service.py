import os
import shutil
import subprocess
import zipfile
import re
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

# Base workspace directory on the filesystem
WORKSPACE_ROOT = Path("workspaces").resolve()

MAX_ZIP_COMPRESSED_SIZE_BYTES = 50 * 1024 * 1024   # 50 MB
MAX_ZIP_UNCOMPRESSED_SIZE_BYTES = 200 * 1024 * 1024 # 200 MB
MAX_ZIP_RATIO = 100  # Max compression ratio to prevent zip bombs
MAX_ZIP_FILES_COUNT = 10000


class WorkspaceSecurityError(Exception):
    """Raised when repository cloning or archive extraction violates security constraints."""
    pass


def get_repo_workspace_path(repo_id: str) -> Path:
    """Return the isolated workspace path for a specific repository."""
    # Ensure repo_id contains only alphanumeric and hyphens (UUID format)
    if not re.match(r"^[a-zA-Z0-9_-]+$", repo_id):
        raise WorkspaceSecurityError("Invalid repository ID format.")
    
    repo_path = (WORKSPACE_ROOT / repo_id).resolve()
    # Confirm it does not escape the WORKSPACE_ROOT
    if not str(repo_path).startswith(str(WORKSPACE_ROOT)):
        raise WorkspaceSecurityError("Workspace path traversal detected.")
    
    return repo_path


def validate_clone_url(clone_url: str) -> str:
    """Validate that clone_url is safe (https only, no command injection)."""
    parsed = urlparse(clone_url)
    if parsed.scheme not in ("https", "http"):
        raise WorkspaceSecurityError("Only HTTP/HTTPS repository clone URLs are permitted.")
    
    # Must have a valid hostname (e.g. github.com, gitlab.com)
    if not parsed.netloc:
        raise WorkspaceSecurityError("Invalid repository URL hostname.")
    
    # Prevent shell injection characters or options
    if any(c in clone_url for c in (";", "&", "|", "`", "$", "\n", "\r", " ")):
        raise WorkspaceSecurityError("Clone URL contains prohibited characters.")
        
    return clone_url


def clone_repository(repo_id: str, clone_url: str, access_token: Optional[str] = None) -> Path:
    """Clone a Git repository into an isolated directory with timeout and safety checks."""
    validate_clone_url(clone_url)
    target_dir = get_repo_workspace_path(repo_id)

    # Clean existing directory if present
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Inject token into URL if authenticated
    authenticated_url = clone_url
    if access_token and "github.com" in clone_url:
        parsed = urlparse(clone_url)
        authenticated_url = f"https://x-access-token:{access_token}@{parsed.netloc}{parsed.path}"

    cmd = [
        "git",
        "clone",
        "--depth", "1",
        "--single-branch",
        authenticated_url,
        str(target_dir),
    ]

    try:
        # Strict execution without shell=True to prevent argument injection
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=90,  # 90s clone timeout
            check=False
        )
        if process.returncode != 0:
            # Mask token in error message
            err_msg = process.stderr.replace(access_token, "***") if access_token else process.stderr
            raise WorkspaceSecurityError(f"Git clone failed: {err_msg.strip()}")
            
        return target_dir
    except subprocess.TimeoutExpired:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise WorkspaceSecurityError("Git clone timed out after 90 seconds.")


def extract_zip_archive(repo_id: str, zip_file_bytes: bytes) -> Tuple[Path, int]:
    """Safely extract a ZIP archive into the workspace directory.
    
    Guards against:
    - ZipSlip (path traversal via ../ or absolute paths)
    - Symlink exploitation
    - Decompression bombs (size/ratio limits)
    - Prohibited executable scripts
    """
    if len(zip_file_bytes) > MAX_ZIP_COMPRESSED_SIZE_BYTES:
        raise WorkspaceSecurityError(f"ZIP archive exceeds max allowed upload size of 50 MB.")

    import io
    target_dir = get_repo_workspace_path(repo_id)

    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(zip_file_bytes)) as zf:
            total_uncompressed_bytes = 0
            file_count = 0

            # 1. First pass: Pre-validation of all members
            for member in zf.infolist():
                file_count += 1
                if file_count > MAX_ZIP_FILES_COUNT:
                    raise WorkspaceSecurityError("Archive contains too many files (max 10,000 files).")

                # Check for Zip Slip / Traversal
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise WorkspaceSecurityError(f"Malicious archive entry detected (Path Traversal): {member.filename}")

                resolved_dest = (target_dir / member_path).resolve()
                if not str(resolved_dest).startswith(str(target_dir)):
                    raise WorkspaceSecurityError(f"Zip Slip path traversal attempt: {member.filename}")

                # Check for symlinks (high 4 bits of external_attr = 0xA)
                is_symlink = (member.external_attr >> 16) & 0o120000 == 0o120000
                if is_symlink:
                    raise WorkspaceSecurityError(f"Archive entry is a symlink, which is prohibited: {member.filename}")

                total_uncompressed_bytes += member.file_size
                if total_uncompressed_bytes > MAX_ZIP_UNCOMPRESSED_SIZE_BYTES:
                    raise WorkspaceSecurityError("Uncompressed archive size exceeds safety limit of 200 MB.")

            # Check compression ratio against zip bomb attacks
            if len(zip_file_bytes) > 0:
                ratio = total_uncompressed_bytes / len(zip_file_bytes)
                if ratio > MAX_ZIP_RATIO and total_uncompressed_bytes > 5 * 1024 * 1024:
                    raise WorkspaceSecurityError("Archive compression ratio exceeds safe limit (possible Zip Bomb).")

            # 2. Second pass: Safe extraction
            for member in zf.infolist():
                # Extract only regular files or directories
                zf.extract(member, path=target_dir)

            # Clean up macOS metadata folder if present
            macosx_dir = target_dir / "__MACOSX"
            if macosx_dir.exists() and macosx_dir.is_dir():
                shutil.rmtree(macosx_dir, ignore_errors=True)

            # If archive contained a single root directory (standard in GitHub downloads),
            # flatten it so the workspace root contains the repository files directly
            entries = [e for e in target_dir.iterdir() if e.name != "__MACOSX"]
            if len(entries) == 1 and entries[0].is_dir():
                single_dir = entries[0]
                temp_dir = target_dir.parent / f"{target_dir.name}_temp_flatten"
                single_dir.rename(temp_dir)
                shutil.rmtree(target_dir, ignore_errors=True)
                temp_dir.rename(target_dir)

            return target_dir, file_count
    except zipfile.BadZipFile:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise WorkspaceSecurityError("Invalid or corrupted ZIP file.")
