"""Behavioral tests for the read-only staging boundary."""

from __future__ import annotations

import shutil
import zlib
from pathlib import Path
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest
from pydantic import ValidationError

from hw_review.domain.enums import EvidenceKind, FileRole
from hw_review.domain.models import SourceFileCreate, StagedFile
from hw_review.services import staging as staging_module
from hw_review.services.staging import FileStager, StageError, fingerprint


TASK_ID = UUID("11111111-1111-4111-8111-111111111111")
PRIMARY_METADATA = SourceFileCreate(
    role=FileRole.PRIMARY_REPORT,
    original_name="customer-visible.xls",
)


def _write_ooxml(path: Path, *entries: str) -> Path:
    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        for entry in entries:
            package.writestr(entry, "<xml />")
    return path


def _write_ooxml_with_corrupt_member(path: Path) -> Path:
    with ZipFile(path, "w") as package:
        package.writestr("[Content_Types].xml", b"content-types-payload")
        package.writestr("word/document.xml", b"document-payload")
    payload = bytearray(path.read_bytes())
    marker = b"document-payload"
    offset = payload.index(marker)
    payload[offset] ^= 0xFF
    path.write_bytes(payload)
    return path


def _write_ooxml_payloads(
    path: Path,
    payloads: dict[str, bytes],
    *,
    compression: int = ZIP_STORED,
) -> Path:
    with ZipFile(path, "w", compression) as package:
        for name, payload in payloads.items():
            package.writestr(name, payload)
    return path


def _mark_first_zip_member_encrypted(path: Path) -> Path:
    payload = bytearray(path.read_bytes())
    local_header = payload.index(b"PK\x03\x04")
    local_flags = int.from_bytes(payload[local_header + 6 : local_header + 8], "little")
    payload[local_header + 6 : local_header + 8] = (local_flags | 1).to_bytes(2, "little")
    central_header = payload.index(b"PK\x01\x02")
    central_flags = int.from_bytes(
        payload[central_header + 8 : central_header + 10], "little"
    )
    payload[central_header + 8 : central_header + 10] = (central_flags | 1).to_bytes(
        2,
        "little",
    )
    path.write_bytes(payload)
    return path


def _corrupt_deflate_member(path: Path, member_name: str) -> Path:
    with ZipFile(path) as package:
        member = package.getinfo(member_name)
        assert member.compress_type == ZIP_DEFLATED
        header_offset = member.header_offset
        compressed_size = member.compress_size
    payload = bytearray(path.read_bytes())
    name_length = int.from_bytes(payload[header_offset + 26 : header_offset + 28], "little")
    extra_length = int.from_bytes(payload[header_offset + 28 : header_offset + 30], "little")
    data_offset = header_offset + 30 + name_length + extra_length
    payload[data_offset : data_offset + compressed_size] = b"\xff" * compressed_size
    path.write_bytes(payload)
    return path


def _stager(tmp_path: Path) -> FileStager:
    return FileStager(tmp_path / "work")


def test_stage_copies_without_mutating_source_or_using_display_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catches source writes, path construction from user metadata, or a copy hash mismatch.
    source = tmp_path / "physical.xls"
    source.write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + b"compound-payload")
    monkeypatch.setattr(staging_module, "_ole_stream_names", lambda _path: {"Workbook"})
    metadata = SourceFileCreate(
        role=FileRole.PRIMARY_REPORT,
        original_name="../../do-not-use-this-name.xls",
    )
    before = fingerprint(source)

    staged = _stager(tmp_path).stage(source, TASK_ID, metadata)

    assert staged.detected_format == "XLS"
    assert staged.sha256 == before.sha256
    assert staged.size_bytes == before.size_bytes
    assert staged.source_mtime_ns == before.mtime_ns
    assert fingerprint(source) == before
    assert fingerprint(staged.path).sha256 == before.sha256
    assert staged.path.parent == (tmp_path / "work" / str(TASK_ID) / "input").resolve()
    assert staged.path.stem == str(staged.id)
    assert staged.path.name not in {source.name, metadata.original_name}


@pytest.mark.parametrize(
    ("suffix", "payload_factory", "expected"),
    [
        (".pdf", lambda path: path.write_bytes(b"%PDF-1.7\n%%EOF\n"), "PDF"),
        (
            ".xlsx",
            lambda path: _write_ooxml(path, "[Content_Types].xml", "xl/workbook.xml"),
            "XLSX",
        ),
        (
            ".docx",
            lambda path: _write_ooxml(path, "[Content_Types].xml", "word/document.xml"),
            "DOCX",
        ),
    ],
)
def test_signature_detection_for_pdf_and_ooxml_packages(
    tmp_path: Path,
    suffix: str,
    payload_factory,
    expected: str,
) -> None:
    # Catches extension-only detection and failure to inspect OOXML package entries.
    source = tmp_path / f"input{suffix}"
    payload_factory(source)

    staged = _stager(tmp_path).stage(source, TASK_ID, PRIMARY_METADATA)

    assert staged.detected_format == expected


@pytest.mark.parametrize(
    ("suffix", "stream_names", "expected"),
    [
        (".xls", {"Workbook"}, "XLS"),
        (".xls", {"Book"}, "XLS"),
        (".doc", {"WordDocument"}, "DOC"),
    ],
)
def test_ole_signature_is_disambiguated_by_compound_streams(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    stream_names: set[str],
    expected: str,
) -> None:
    # Catches treating every OLE file as XLS or trusting only its extension.
    source = tmp_path / f"input{suffix}"
    source.write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + b"compound-payload")
    monkeypatch.setattr(staging_module, "_ole_stream_names", lambda _path: stream_names)

    staged = _stager(tmp_path).stage(source, TASK_ID, PRIMARY_METADATA)

    assert staged.detected_format == expected


@pytest.mark.parametrize(
    ("name", "writer"),
    [
        ("report.pdf", lambda path: path.write_bytes(b"not a pdf")),
        (
            "report.docx",
            lambda path: _write_ooxml(path, "[Content_Types].xml", "xl/workbook.xml"),
        ),
    ],
)
def test_extension_signature_mismatch_is_rejected(
    tmp_path: Path,
    name: str,
    writer,
) -> None:
    # Catches accepting content whose detected format conflicts with its suffix.
    source = tmp_path / name
    writer(source)

    with pytest.raises(StageError) as error:
        _stager(tmp_path).stage(source, TASK_ID, PRIMARY_METADATA)

    assert error.value.code == "FILE_SIGNATURE_MISMATCH"


@pytest.mark.parametrize(
    ("hostile_task_id", "escaped_name"),
    [
        ("../escaped", "escaped"),
        ("not-a-uuid", "not-a-uuid"),
        ("AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA", "uppercase-id"),
    ],
)
def test_stage_rejects_noncanonical_task_ids_without_creating_paths(
    tmp_path: Path,
    hostile_task_id: str,
    escaped_name: str,
) -> None:
    # Catches path traversal or malformed strings reaching mkdir before UUID validation.
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.7\n%%EOF\n")
    stager = _stager(tmp_path)

    with pytest.raises(StageError) as error:
        stager.stage(source, hostile_task_id, PRIMARY_METADATA)  # type: ignore[arg-type]

    assert error.value.code == "INVALID_TASK_ID"
    assert not (tmp_path / escaped_name).exists()
    assert list((tmp_path / "work").iterdir()) == []


def test_stage_rejects_hostile_task_object_without_calling_its_stringifier(
    tmp_path: Path,
) -> None:
    # Catches arbitrary objects influencing a filesystem path through __str__.
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.7\n%%EOF\n")
    stager = _stager(tmp_path)

    class HostileTaskId:
        def __str__(self) -> str:
            raise AssertionError("hostile __str__ must not be called")

    with pytest.raises(StageError) as error:
        stager.stage(source, HostileTaskId(), PRIMARY_METADATA)  # type: ignore[arg-type]

    assert error.value.code == "INVALID_TASK_ID"
    assert list((tmp_path / "work").iterdir()) == []


def test_stage_coerces_a_canonical_uuid_string(tmp_path: Path) -> None:
    # Catches accepting a UUID string for the path but failing to normalize the domain value.
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.7\n%%EOF\n")

    staged = _stager(tmp_path).stage(  # type: ignore[arg-type]
        source,
        str(TASK_ID),
        PRIMARY_METADATA,
    )

    assert staged.task_id == TASK_ID
    assert staged.path.parents[1].name == str(TASK_ID)


def test_unsupported_extension_and_signature_have_stable_error(tmp_path: Path) -> None:
    # Catches arbitrary binary files entering the parser pipeline.
    source = tmp_path / "report.bin"
    source.write_bytes(b"plain binary data")

    with pytest.raises(StageError) as error:
        _stager(tmp_path).stage(source, TASK_ID, PRIMARY_METADATA)

    assert error.value.code == "UNSUPPORTED_FILE_FORMAT"


def test_corrupt_ooxml_container_has_stable_error(tmp_path: Path) -> None:
    # Catches damaged ZIP payloads being mislabeled as valid Office documents.
    source = tmp_path / "report.docx"
    source.write_bytes(b"PK\x03\x04this-is-not-a-zip")

    with pytest.raises(StageError) as error:
        _stager(tmp_path).stage(source, TASK_ID, PRIMARY_METADATA)

    assert error.value.code == "CORRUPT_FILE"


def test_ooxml_with_corrupt_member_crc_has_stable_error(tmp_path: Path) -> None:
    # Catches accepting a ZIP from its directory even though a member fails CRC validation.
    source = _write_ooxml_with_corrupt_member(tmp_path / "report.docx")

    with pytest.raises(StageError) as error:
        _stager(tmp_path).stage(source, TASK_ID, PRIMARY_METADATA)

    assert error.value.code == "CORRUPT_FILE"


def test_ooxml_without_content_types_manifest_has_stable_error(tmp_path: Path) -> None:
    # Catches treating an arbitrary ZIP with one Office-looking path as valid OOXML.
    source = _write_ooxml(tmp_path / "report.docx", "word/document.xml")

    with pytest.raises(StageError) as error:
        _stager(tmp_path).stage(source, TASK_ID, PRIMARY_METADATA)

    assert error.value.code == "CORRUPT_FILE"


def test_highly_compressible_ooxml_exceeding_expansion_limits_is_rejected(
    tmp_path: Path,
) -> None:
    # Catches a small ZIP expanding without bounds before the task workspace is created.
    source = _write_ooxml_payloads(
        tmp_path / "report.docx",
        {
            "[Content_Types].xml": b"manifest",
            "word/document.xml": b"0" * (256 * 1024),
        },
        compression=ZIP_DEFLATED,
    )
    raw_size = source.stat().st_size
    assert raw_size < 1024 * 1024
    stager = FileStager(
        tmp_path / "work",
        max_file_size_bytes=1024 * 1024,
        max_ooxml_member_uncompressed_bytes=512 * 1024,
        max_ooxml_aggregate_uncompressed_bytes=128 * 1024,
        max_ooxml_compression_ratio=10,
    )

    with pytest.raises(StageError) as error:
        stager.stage(source, TASK_ID, PRIMARY_METADATA)

    assert error.value.code == "ARCHIVE_RESOURCE_LIMIT_EXCEEDED"
    assert not (tmp_path / "work" / str(TASK_ID)).exists()


@pytest.mark.parametrize(
    "limit_overrides",
    [
        {"max_ooxml_member_count": 1},
        {"max_ooxml_member_uncompressed_bytes": 7},
        {"max_ooxml_aggregate_uncompressed_bytes": 15},
        {"max_ooxml_compression_ratio": 0.99},
    ],
)
def test_each_ooxml_resource_ceiling_rejects_excess_before_task_creation(
    tmp_path: Path,
    limit_overrides: dict[str, int | float],
) -> None:
    # Catches any configured archive ceiling being recorded but not enforced.
    source = _write_ooxml_payloads(
        tmp_path / "report.docx",
        {
            "[Content_Types].xml": b"manifest",
            "word/document.xml": b"document",
        },
    )
    stager = FileStager(
        tmp_path / "work",
        max_file_size_bytes=source.stat().st_size,
        **limit_overrides,
    )

    with pytest.raises(StageError) as error:
        stager.stage(source, TASK_ID, PRIMARY_METADATA)

    assert error.value.code == "ARCHIVE_RESOURCE_LIMIT_EXCEEDED"
    assert not (tmp_path / "work" / str(TASK_ID)).exists()


def test_ooxml_resource_ceilings_accept_exact_boundaries(tmp_path: Path) -> None:
    # Catches off-by-one rejection at member, size, aggregate, or ratio boundaries.
    source = _write_ooxml_payloads(
        tmp_path / "report.docx",
        {
            "[Content_Types].xml": b"manifest",
            "word/document.xml": b"document",
        },
    )
    stager = FileStager(
        tmp_path / "work",
        max_file_size_bytes=source.stat().st_size,
        max_ooxml_member_count=2,
        max_ooxml_member_uncompressed_bytes=8,
        max_ooxml_aggregate_uncompressed_bytes=16,
        max_ooxml_compression_ratio=1,
    )

    staged = stager.stage(source, TASK_ID, PRIMARY_METADATA)

    assert staged.detected_format == "DOCX"


@pytest.mark.parametrize(
    "invalid_limit",
    [
        {"max_file_size_bytes": 0},
        {"max_ooxml_member_count": 0},
        {"max_ooxml_member_uncompressed_bytes": -1},
        {"max_ooxml_aggregate_uncompressed_bytes": 0},
        {"max_ooxml_compression_ratio": 0},
    ],
)
def test_stager_rejects_nonpositive_safety_limits_before_creating_root(
    tmp_path: Path,
    invalid_limit: dict[str, int],
) -> None:
    # Catches disabled ceilings and constructor side effects before validation.
    work_root = tmp_path / "work"

    with pytest.raises(ValueError):
        FileStager(work_root, **invalid_limit)

    assert not work_root.exists()


def test_encrypted_ooxml_member_is_rejected_as_corrupt_before_task_creation(
    tmp_path: Path,
) -> None:
    # Catches password-protected members escaping deterministic integrity inspection.
    source = _mark_first_zip_member_encrypted(
        _write_ooxml_payloads(
            tmp_path / "report.docx",
            {
                "[Content_Types].xml": b"manifest",
                "word/document.xml": b"document",
            },
        )
    )

    with pytest.raises(StageError) as error:
        _stager(tmp_path).stage(source, TASK_ID, PRIMARY_METADATA)

    assert error.value.code == "CORRUPT_FILE"
    assert not (tmp_path / "work" / str(TASK_ID)).exists()


def test_unreadable_ooxml_member_is_mapped_to_stable_corrupt_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catches a truncated member stream leaking an adapter exception to callers.
    source = _write_ooxml_payloads(
        tmp_path / "report.docx",
        {
            "[Content_Types].xml": b"manifest",
            "word/document.xml": b"document",
        },
    )

    def fail_open(*_args, **_kwargs):
        raise EOFError("truncated member stream")

    monkeypatch.setattr(ZipFile, "open", fail_open)

    with pytest.raises(StageError) as error:
        _stager(tmp_path).stage(source, TASK_ID, PRIMARY_METADATA)

    assert error.value.code == "CORRUPT_FILE"
    assert not (tmp_path / "work" / str(TASK_ID)).exists()


def test_deflate_stream_error_is_mapped_to_stable_corrupt_error(
    tmp_path: Path,
) -> None:
    # Catches raw DEFLATE decoder failures leaking past the stable staging boundary.
    source = _corrupt_deflate_member(
        _write_ooxml_payloads(
            tmp_path / "report.docx",
            {
                "[Content_Types].xml": bytes(range(64)),
                "word/document.xml": bytes(range(256)) * 16,
            },
            compression=ZIP_DEFLATED,
        ),
        "word/document.xml",
    )
    with ZipFile(source) as package:
        assert package.getinfo("word/document.xml").compress_type == ZIP_DEFLATED
        with pytest.raises(zlib.error):
            package.read("word/document.xml")

    with pytest.raises(StageError) as error:
        _stager(tmp_path).stage(source, TASK_ID, PRIMARY_METADATA)

    assert error.value.code == "CORRUPT_FILE"
    assert not (tmp_path / "work" / str(TASK_ID)).exists()


def test_ambiguous_ooxml_container_has_stable_error(tmp_path: Path) -> None:
    # Catches a package matching two supported formats being guessed into one branch.
    source = _write_ooxml(
        tmp_path / "report.docx",
        "[Content_Types].xml",
        "xl/workbook.xml",
        "word/document.xml",
    )

    with pytest.raises(StageError) as error:
        _stager(tmp_path).stage(source, TASK_ID, PRIMARY_METADATA)

    assert error.value.code == "AMBIGUOUS_FILE_FORMAT"


def test_copy_verification_failure_removes_incomplete_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catches a failed or altered copy leaving a parser-visible staged payload behind.
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.7\noriginal\n%%EOF\n")

    def corrupting_copy(_source: Path, destination: Path) -> Path:
        destination.write_bytes(b"%PDF-1.7\nchanged\n%%EOF\n")
        return destination

    monkeypatch.setattr(shutil, "copy2", corrupting_copy)

    with pytest.raises(StageError) as error:
        _stager(tmp_path).stage(source, TASK_ID, PRIMARY_METADATA)

    assert error.value.code == "COPY_VERIFICATION_FAILED"
    input_dir = tmp_path / "work" / str(TASK_ID) / "input"
    assert input_dir.exists()
    assert list(input_dir.iterdir()) == []


def test_post_copy_model_failure_removes_payload_and_preserves_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catches model-construction failures bypassing staged-payload cleanup.
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.7\n%%EOF\n")
    original_error = RuntimeError("sentinel model construction failure")

    def fail_model_construction(**_values):
        raise original_error

    monkeypatch.setattr(staging_module, "StagedFile", fail_model_construction)

    with pytest.raises(RuntimeError) as error:
        _stager(tmp_path).stage(source, TASK_ID, PRIMARY_METADATA)

    assert error.value is original_error
    input_dir = tmp_path / "work" / str(TASK_ID) / "input"
    assert input_dir.exists()
    assert list(input_dir.iterdir()) == []


def test_blank_source_display_name_is_rejected() -> None:
    # Catches blank metadata crossing from Task 1 into a valid staged payload.
    with pytest.raises(ValidationError):
        SourceFileCreate(
            role=FileRole.PRIMARY_REPORT,
            original_name=" \t ",
        )


def test_file_at_configured_size_boundary_is_accepted(tmp_path: Path) -> None:
    # Catches an off-by-one rejection at the inclusive file-size limit.
    payload = b"%PDF-1.7\n%%EOF\n"
    source = tmp_path / "report.pdf"
    source.write_bytes(payload)
    stager = FileStager(tmp_path / "work", max_file_size_bytes=len(payload))

    staged = stager.stage(source, TASK_ID, PRIMARY_METADATA)

    assert staged.size_bytes == len(payload)


def test_file_over_configured_size_is_rejected_before_detection_or_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catches oversized input reaching format inspection or creating task payload paths.
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.7\n%%EOF\n")
    before = fingerprint(source)
    stager = FileStager(tmp_path / "work", max_file_size_bytes=before.size_bytes - 1)

    def unexpected_detection(*_args, **_kwargs):
        raise AssertionError("oversized file must be rejected before format detection")

    monkeypatch.setattr(staging_module, "_detect_format", unexpected_detection)

    with pytest.raises(StageError) as error:
        stager.stage(source, TASK_ID, PRIMARY_METADATA)

    assert error.value.code == "FILE_TOO_LARGE"
    assert fingerprint(source) == before
    assert list((tmp_path / "work").iterdir()) == []


def test_default_size_limit_rejects_more_than_100_mib_without_reading_payload(
    tmp_path: Path,
) -> None:
    # Catches an absent or incorrectly scaled recommended local default.
    source = tmp_path / "oversized.pdf"
    with source.open("wb") as payload:
        payload.truncate(100 * 1024 * 1024 + 1)
    stager = _stager(tmp_path)

    with pytest.raises(StageError) as error:
        stager.stage(source, TASK_ID, PRIMARY_METADATA)

    assert error.value.code == "FILE_TOO_LARGE"
    assert list((tmp_path / "work").iterdir()) == []


def test_staged_file_is_immutable(tmp_path: Path) -> None:
    # Catches later layers silently changing the staged file's verified identity.
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.7\n%%EOF\n")
    staged = _stager(tmp_path).stage(source, TASK_ID, PRIMARY_METADATA)

    with pytest.raises(ValidationError):
        staged.detected_format = "DOCX"


def test_supporting_evidence_metadata_is_preserved(tmp_path: Path) -> None:
    # Catches staging dropping role or routing labels needed by later rule evaluation.
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.7\n%%EOF\n")
    metadata = SourceFileCreate(
        role=FileRole.SUPPORTING_EVIDENCE,
        original_name="evidence.pdf",
        evidence_kinds=(EvidenceKind.EMC_REPORT, EvidenceKind.PUBLISHED_CRITERIA),
    )

    staged = _stager(tmp_path).stage(source, TASK_ID, metadata)

    assert staged.role is FileRole.SUPPORTING_EVIDENCE
    assert staged.evidence_kinds == (
        EvidenceKind.EMC_REPORT,
        EvidenceKind.PUBLISHED_CRITERIA,
    )
    assert staged.original_name == "evidence.pdf"


@pytest.mark.parametrize(
    ("role", "evidence_kinds"),
    [
        (FileRole.SUPPORTING_EVIDENCE, ()),
        (FileRole.PRIMARY_REPORT, (EvidenceKind.EMC_REPORT,)),
    ],
)
def test_staged_file_revalidates_role_and_evidence_kind_contract(
    tmp_path: Path,
    role: FileRole,
    evidence_kinds: tuple[EvidenceKind, ...],
) -> None:
    # Catches invalid routing metadata entering Task 4 through direct construction.
    with pytest.raises(ValidationError):
        StagedFile(
            id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            task_id=TASK_ID,
            role=role,
            evidence_kinds=evidence_kinds,
            original_name="report.pdf",
            detected_format="PDF",
            path=tmp_path / "report.pdf",
            size_bytes=10,
            sha256="0" * 64,
            source_mtime_ns=1,
        )
