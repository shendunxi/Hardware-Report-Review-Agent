"""Read-only source staging with content-signature verification."""

from __future__ import annotations

import hashlib
import math
import shutil
import zlib
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import BadZipFile, ZipFile

import olefile

from hw_review.domain.models import SourceFileCreate, StagedFile


_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
_ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_FORMAT_BY_EXTENSION = {
    ".xls": "XLS",
    ".xlsx": "XLSX",
    ".doc": "DOC",
    ".docx": "DOCX",
    ".pdf": "PDF",
}
_EXTENSION_BY_FORMAT = {value: key for key, value in _FORMAT_BY_EXTENSION.items()}
DEFAULT_MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_OOXML_MEMBER_COUNT = 10_000
DEFAULT_MAX_OOXML_COMPRESSION_RATIO = 100.0


class StageError(Exception):
    """Stable staging failure that is safe to expose at the API boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class FileFingerprint:
    """Source facts used to prove that staging did not alter a file."""

    sha256: str
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class OoxmlSafetyLimits:
    """Bounded resource envelope for inspecting one OOXML ZIP package."""

    member_count: int
    member_uncompressed_bytes: int
    aggregate_uncompressed_bytes: int
    compression_ratio: float


def fingerprint(path: Path) -> FileFingerprint:
    """Return a stable SHA-256, size, and nanosecond modification-time snapshot."""

    source_path = Path(path)
    digest = hashlib.sha256()
    with source_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    stats = source_path.stat()
    return FileFingerprint(
        sha256=digest.hexdigest(),
        size_bytes=stats.st_size,
        mtime_ns=stats.st_mtime_ns,
    )


def _ole_stream_names(path: Path) -> set[str]:
    """Inspect the compound directory without executing embedded content."""

    try:
        compound = olefile.OleFileIO(str(path))
        try:
            return {
                entry[-1]
                for entry in compound.listdir(streams=True, storages=False)
                if entry
            }
        finally:
            compound.close()
    except (OSError, IOError, ValueError) as error:
        raise StageError("CORRUPT_FILE", "OLE compound directory is unreadable") from error


def _detect_ole_format(path: Path) -> str:
    names = {name.casefold() for name in _ole_stream_names(path)}
    is_workbook = bool({"workbook", "book"} & names)
    is_document = "worddocument" in names
    if is_workbook == is_document:
        raise StageError(
            "AMBIGUOUS_FILE_FORMAT",
            "OLE container does not identify exactly one supported document format",
        )
    return "XLS" if is_workbook else "DOC"


def _archive_limit_error(message: str) -> StageError:
    return StageError("ARCHIVE_RESOURCE_LIMIT_EXCEEDED", message)


def _detect_ooxml_format(path: Path, limits: OoxmlSafetyLimits) -> str | None:
    try:
        with ZipFile(path) as package:
            members = package.infolist()
            if len(members) > limits.member_count:
                raise _archive_limit_error("OOXML package contains too many members")

            entries = {
                member.filename.replace("\\", "/").casefold() for member in members
            }
            if "[content_types].xml" not in entries:
                raise StageError(
                    "CORRUPT_FILE",
                    "OOXML package is missing its content-types manifest",
                )

            declared_total = 0
            declared_compressed_total = 0
            for member in members:
                if member.flag_bits & 0x1:
                    raise StageError(
                        "CORRUPT_FILE",
                        "OOXML package contains an encrypted member",
                    )
                if member.file_size > limits.member_uncompressed_bytes:
                    raise _archive_limit_error(
                        "OOXML member exceeds the uncompressed-size limit"
                    )
                declared_total += member.file_size
                if declared_total > limits.aggregate_uncompressed_bytes:
                    raise _archive_limit_error(
                        "OOXML package exceeds the aggregate uncompressed-size limit"
                    )
                if not member.is_dir():
                    declared_compressed_total += member.compress_size
                    if member.compress_size == 0:
                        if member.file_size > 0:
                            raise _archive_limit_error(
                                "OOXML member exceeds the compression-ratio limit"
                            )
                    elif member.file_size > member.compress_size * limits.compression_ratio:
                        raise _archive_limit_error(
                            "OOXML member exceeds the compression-ratio limit"
                        )
            if (
                declared_compressed_total == 0
                and declared_total > 0
                or declared_compressed_total > 0
                and declared_total
                > declared_compressed_total * limits.compression_ratio
            ):
                raise _archive_limit_error(
                    "OOXML package exceeds the aggregate compression-ratio limit"
                )

            actual_total = 0
            for member in members:
                if member.is_dir():
                    continue
                member_total = 0
                with package.open(member, "r") as stream:
                    while True:
                        member_remaining = limits.member_uncompressed_bytes - member_total
                        aggregate_remaining = (
                            limits.aggregate_uncompressed_bytes - actual_total
                        )
                        read_size = min(
                            1024 * 1024,
                            member_remaining + 1,
                            aggregate_remaining + 1,
                        )
                        chunk = stream.read(read_size)
                        if not chunk:
                            break
                        member_total += len(chunk)
                        actual_total += len(chunk)
                        if member_total > limits.member_uncompressed_bytes:
                            raise _archive_limit_error(
                                "OOXML member exceeds the uncompressed-size limit"
                            )
                        if actual_total > limits.aggregate_uncompressed_bytes:
                            raise _archive_limit_error(
                                "OOXML package exceeds the aggregate uncompressed-size limit"
                            )
                        if (
                            member.compress_size == 0
                            and member_total > 0
                            or member.compress_size > 0
                            and member_total
                            > member.compress_size * limits.compression_ratio
                        ):
                            raise _archive_limit_error(
                                "OOXML member exceeds the compression-ratio limit"
                            )
                if member_total != member.file_size:
                    raise StageError(
                        "CORRUPT_FILE",
                        "OOXML member size does not match its directory entry",
                    )

            if actual_total != declared_total:
                raise StageError(
                    "CORRUPT_FILE",
                    "OOXML package size does not match its directory entries",
                )
    except (
        BadZipFile,
        EOFError,
        OSError,
        RuntimeError,
        ValueError,
        NotImplementedError,
        zlib.error,
    ) as error:
        raise StageError("CORRUPT_FILE", "OOXML ZIP package is unreadable") from error

    is_workbook = "xl/workbook.xml" in entries
    is_document = "word/document.xml" in entries
    if is_workbook and is_document:
        raise StageError(
            "AMBIGUOUS_FILE_FORMAT",
            "OOXML package identifies more than one supported document format",
        )
    if is_workbook:
        return "XLSX"
    if is_document:
        return "DOCX"
    return None


def _detect_format(
    path: Path,
    extension: str,
    ooxml_limits: OoxmlSafetyLimits,
) -> str:
    try:
        with path.open("rb") as source:
            signature = source.read(8)
    except OSError as error:
        raise StageError("SOURCE_UNREADABLE", "source file cannot be read") from error

    detected: str | None
    if signature.startswith(b"%PDF-"):
        detected = "PDF"
    elif signature == _OLE_SIGNATURE:
        detected = _detect_ole_format(path)
    elif signature.startswith(_ZIP_SIGNATURES):
        detected = _detect_ooxml_format(path, ooxml_limits)
    else:
        detected = None

    expected = _FORMAT_BY_EXTENSION.get(extension)
    if expected is None:
        raise StageError("UNSUPPORTED_FILE_FORMAT", "file extension is not supported")
    if detected != expected:
        raise StageError(
            "FILE_SIGNATURE_MISMATCH",
            "file extension and detected content signature do not match",
        )
    return detected


class FileStager:
    """Copy user-selected files into a verified UUID-scoped parser workspace."""

    def __init__(
        self,
        work_root: Path,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
        max_ooxml_member_count: int = DEFAULT_MAX_OOXML_MEMBER_COUNT,
        max_ooxml_member_uncompressed_bytes: int | None = None,
        max_ooxml_aggregate_uncompressed_bytes: int | None = None,
        max_ooxml_compression_ratio: float = DEFAULT_MAX_OOXML_COMPRESSION_RATIO,
    ) -> None:
        _require_positive_int("max_file_size_bytes", max_file_size_bytes)
        _require_positive_int("max_ooxml_member_count", max_ooxml_member_count)
        member_bytes = (
            max_file_size_bytes
            if max_ooxml_member_uncompressed_bytes is None
            else max_ooxml_member_uncompressed_bytes
        )
        aggregate_bytes = (
            4 * max_file_size_bytes
            if max_ooxml_aggregate_uncompressed_bytes is None
            else max_ooxml_aggregate_uncompressed_bytes
        )
        _require_positive_int("max_ooxml_member_uncompressed_bytes", member_bytes)
        _require_positive_int("max_ooxml_aggregate_uncompressed_bytes", aggregate_bytes)
        if (
            isinstance(max_ooxml_compression_ratio, bool)
            or not isinstance(max_ooxml_compression_ratio, (int, float))
            or not math.isfinite(max_ooxml_compression_ratio)
            or max_ooxml_compression_ratio <= 0
        ):
            raise ValueError("max_ooxml_compression_ratio must be positive and finite")
        root = Path(work_root)
        root.mkdir(parents=True, exist_ok=True)
        self._work_root = root.resolve()
        self._max_file_size_bytes = max_file_size_bytes
        self._ooxml_limits = OoxmlSafetyLimits(
            member_count=max_ooxml_member_count,
            member_uncompressed_bytes=member_bytes,
            aggregate_uncompressed_bytes=aggregate_bytes,
            compression_ratio=float(max_ooxml_compression_ratio),
        )

    def stage(
        self,
        source: Path,
        task_id: UUID,
        metadata: SourceFileCreate,
    ) -> StagedFile:
        canonical_task_id = _coerce_task_id(task_id)
        try:
            source_path = Path(source).resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise StageError("FILE_NOT_FOUND", "source file does not exist") from error
        if not source_path.is_file():
            raise StageError("SOURCE_NOT_FILE", "source path is not a regular file")

        try:
            source_size = source_path.stat().st_size
        except OSError as error:
            raise StageError("SOURCE_UNREADABLE", "source file cannot be inspected") from error
        if source_size > self._max_file_size_bytes:
            raise StageError(
                "FILE_TOO_LARGE",
                "source file exceeds the configured staging size limit",
            )

        before = fingerprint(source_path)
        detected_format = _detect_format(
            source_path,
            source_path.suffix.casefold(),
            self._ooxml_limits,
        )
        file_id = uuid4()
        input_dir = self._verified_input_dir(canonical_task_id)
        destination = input_dir / f"{file_id}{_EXTENSION_BY_FORMAT[detected_format]}"

        try:
            shutil.copy2(source_path, destination)
        except OSError as error:
            destination.unlink(missing_ok=True)
            raise StageError("FILE_COPY_FAILED", "source file could not be staged") from error
        except BaseException:
            destination.unlink(missing_ok=True)
            raise

        try:
            copied = fingerprint(destination)
            after = fingerprint(source_path)
            if after != before:
                raise StageError(
                    "SOURCE_CHANGED_DURING_STAGING",
                    "source file changed while it was being staged",
                )
            if copied.sha256 != before.sha256 or copied.size_bytes != before.size_bytes:
                raise StageError(
                    "COPY_VERIFICATION_FAILED",
                    "staged copy does not match the selected source",
                )
            staged = StagedFile(
                id=file_id,
                task_id=canonical_task_id,
                role=metadata.role,
                evidence_kinds=metadata.evidence_kinds,
                original_name=metadata.original_name,
                detected_format=detected_format,
                path=destination.resolve(),
                size_bytes=before.size_bytes,
                sha256=before.sha256,
                source_mtime_ns=before.mtime_ns,
            )
        except BaseException:
            destination.unlink(missing_ok=True)
            raise

        return staged

    def _verified_input_dir(self, task_id: UUID) -> Path:
        task_dir = self._work_root / str(task_id)
        if task_dir.is_symlink():
            raise StageError("UNSAFE_WORKSPACE", "task workspace cannot be a symlink")
        resolved_task_dir = task_dir.resolve(strict=False)
        if resolved_task_dir.parent != self._work_root:
            raise StageError("UNSAFE_WORKSPACE", "task workspace is outside the configured root")
        task_dir.mkdir(exist_ok=True)
        if task_dir.resolve() != resolved_task_dir:
            raise StageError("UNSAFE_WORKSPACE", "task workspace is outside the configured root")

        input_dir = task_dir / "input"
        if input_dir.is_symlink():
            raise StageError("UNSAFE_WORKSPACE", "input workspace cannot be a symlink")
        input_dir.mkdir(exist_ok=True)
        resolved_input = input_dir.resolve()
        if resolved_input.parent != task_dir.resolve():
            raise StageError("UNSAFE_WORKSPACE", "input workspace is outside the task directory")
        return resolved_input


def _coerce_task_id(value: object) -> UUID:
    """Accept only UUIDs or their canonical lowercase hyphenated string form."""

    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        raise StageError("INVALID_TASK_ID", "task ID must be a UUID")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as error:
        raise StageError("INVALID_TASK_ID", "task ID must be a canonical UUID") from error
    if value != str(parsed):
        raise StageError("INVALID_TASK_ID", "task ID must be a canonical UUID")
    return parsed


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
