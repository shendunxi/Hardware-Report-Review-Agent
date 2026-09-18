"""Integration coverage for deterministic, non-OCR PDF normalization."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest
import psutil

from hw_review.domain.enums import FileRole
from hw_review.domain.models import SourceFileCreate, StagedFile
from hw_review.parsers.pdf import PdfParseError, PdfParser
from hw_review.services.cleanup import WorkspaceCleaner
from hw_review.services.staging import FileStager, fingerprint


S07 = Path(
    r"D:\Document\AI创新应用大赛\硬件测试报告审核智能体\硬件测试报告及检查表"
    r"\TCY30\PP\TCY30 (903442) PP 可靠性测试报告_20260609.pdf"
)


def _staged(path: Path, *, detected_format: str = "PDF") -> StagedFile:
    payload = path.read_bytes()
    return StagedFile(
        id=uuid4(),
        task_id=uuid4(),
        role=FileRole.PRIMARY_REPORT,
        original_name=path.name,
        detected_format=detected_format,
        path=path,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        source_mtime_ns=path.stat().st_mtime_ns,
    )


def _save_text_pdf(path: Path, pages: tuple[tuple[str, ...], ...]) -> None:
    document = pymupdf.open()
    for lines in pages:
        page = document.new_page()
        for index, text in enumerate(lines):
            page.insert_text((72, 72 + index * 40), text)
    document.save(path)
    document.close()


def _png_bytes() -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 3, 3), False)
    pixmap.clear_with(0x336699)
    return pixmap.tobytes("png")


def test_pdf_text_has_stable_page_locator_bbox_hash_and_identity(tmp_path: Path) -> None:
    path = tmp_path / "text.pdf"
    _save_text_pdf(path, (("alpha", "beta"),))
    staged = _staged(path)

    first = PdfParser().parse(staged)
    second = PdfParser().parse(staged)

    block = next(block for block in first.containers[0].blocks if block.kind == "text")
    assert first.source_file_id == staged.id
    assert first.format == "PDF"
    assert first.container_count == 1
    assert first.containers[0].name_or_number == 1
    assert block.structural_address == "page:1/text:1"
    assert block.bbox is not None and len(block.bbox) == 4
    assert len(block.content_hash) == 64
    assert first.id == second.id
    assert first.text_digest == second.text_digest
    assert first.containers == second.containers


def test_image_only_page_inventories_image_and_emits_located_warning(tmp_path: Path) -> None:
    path = tmp_path / "image.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_image(pymupdf.Rect(20, 30, 120, 130), stream=_png_bytes())
    document.save(path)
    document.close()

    parsed = PdfParser().parse(_staged(path))

    images = [block for block in parsed.containers[0].blocks if block.kind == "image"]
    assert len(images) == 1
    assert images[0].text is None
    assert images[0].structural_address == "page:1/image:1"
    assert images[0].bbox == (20.0, 30.0, 120.0, 130.0)
    assert any(
        warning.code == "IMAGE_ONLY_PAGE"
        and warning.structural_address == "page:1"
        for warning in parsed.parse_warnings
    )


def test_multi_page_text_and_images_preserve_deterministic_visual_order(tmp_path: Path) -> None:
    path = tmp_path / "multi.pdf"
    document = pymupdf.open()
    first = document.new_page()
    first.insert_text((200, 200), "lower-right")
    first.insert_text((40, 40), "upper-left")
    first.insert_image(pymupdf.Rect(10, 250, 30, 270), stream=_png_bytes())
    second = document.new_page()
    second.insert_text((60, 60), "second-page")
    document.save(path)
    document.close()

    staged = _staged(path)
    one = PdfParser().parse(staged)
    two = PdfParser().parse(staged)

    assert [container.name_or_number for container in one.containers] == [1, 2]
    assert [block.order for block in one.containers[0].blocks] == list(
        range(len(one.containers[0].blocks))
    )
    assert [block.kind for block in one.containers[0].blocks] == ["text", "text", "image"]
    assert [block.text for block in one.containers[0].blocks if block.kind == "text"] == [
        "upper-left",
        "lower-right",
    ]
    assert one.text_digest == two.text_digest
    assert one.containers == two.containers


def test_reused_pdf_image_is_inventoried_once_per_visual_occurrence(tmp_path: Path) -> None:
    path = tmp_path / "reused-image.pdf"
    document = pymupdf.open()
    page = document.new_page()
    xref = page.insert_image(pymupdf.Rect(10, 10, 30, 30), stream=_png_bytes())
    page.insert_image(pymupdf.Rect(50, 50, 80, 80), xref=xref)
    document.save(path)
    document.close()

    parsed = PdfParser().parse(_staged(path))
    images = [block for block in parsed.containers[0].blocks if block.kind == "image"]

    assert len(images) == 2
    assert [block.bbox for block in images] == [
        (10.0, 10.0, 30.0, 30.0),
        (50.0, 50.0, 80.0, 80.0),
    ]


def test_malformed_image_extraction_uses_deterministic_source_bound_hash() -> None:
    class BrokenImageDocument:
        def extract_image(self, _xref):
            raise RuntimeError("malformed image stream")

    parser = PdfParser()
    source_hash = "a" * 64
    first = parser._image_content_hash(BrokenImageDocument(), source_hash, 2, 17, 0)
    second = parser._image_content_hash(BrokenImageDocument(), source_hash, 2, 17, 0)

    assert first == second
    assert len(first) == 64
    assert first != hashlib.sha256(b"").hexdigest()


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("wrong", "WRONG_FORMAT"),
        ("changed-size", "STAGED_FILE_CHANGED"),
        ("changed-hash", "STAGED_FILE_CHANGED"),
        ("protected", "PDF_PROTECTED"),
        ("corrupt", "PDF_CORRUPT"),
    ],
)
def test_pdf_failure_codes_are_stable(tmp_path: Path, case: str, expected: str) -> None:
    path = tmp_path / "case.pdf"
    _save_text_pdf(path, (("payload",),))
    staged = _staged(path, detected_format="DOC" if case == "wrong" else "PDF")
    if case == "changed-size":
        path.write_bytes(path.read_bytes() + b"changed")
    elif case == "changed-hash":
        payload = bytearray(path.read_bytes())
        payload[-2] ^= 1
        path.write_bytes(payload)
        assert path.stat().st_size == staged.size_bytes
    elif case == "protected":
        plain = pymupdf.open(path)
        encrypted_path = tmp_path / "encrypted.pdf"
        plain.save(
            encrypted_path,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="owner",
            user_pw="secret",
        )
        plain.close()
        path = encrypted_path
        staged = _staged(path)
    elif case == "corrupt":
        path.write_bytes(b"%PDF-1.7\nnot a valid pdf")
        staged = _staged(path)

    with pytest.raises(PdfParseError) as error:
        PdfParser().parse(staged)
    assert error.value.code == expected


def test_optional_table_discovery_failure_is_a_located_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "table-warning.pdf"
    _save_text_pdf(path, (("text remains usable",),))

    monkeypatch.setattr(
        PdfParser,
        "_table_blocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("unsupported")),
    )
    parsed = PdfParser().parse(_staged(path))

    assert any(
        warning.code == "TABLE_DISCOVERY_FAILED"
        and warning.structural_address == "page:1"
        for warning in parsed.parse_warnings
    )
    assert any(block.kind == "text" for block in parsed.containers[0].blocks)


def test_real_s07_is_staged_read_only_measured_and_cleaned() -> None:
    if not S07.is_file():
        pytest.skip("frozen S-07 is unavailable")
    repository_root = Path(__file__).resolve().parents[3]
    work_root = repository_root / ".task-work" / "task-5-s07"
    work_root.mkdir(parents=True, exist_ok=True)
    task_id = uuid4()
    before = fingerprint(S07)
    try:
        staged = FileStager(work_root).stage(
            S07,
            task_id,
            SourceFileCreate(role=FileRole.PRIMARY_REPORT, original_name=S07.name),
        )
        assert staged.path != S07
        process = psutil.Process()
        started = time.perf_counter()
        document = PdfParser().parse(staged)
        duration = time.perf_counter() - started
        after = fingerprint(S07)
        assert after == before
        assert duration < 20 * 60
        assert document.container_count >= 1
        text_count = sum(block.kind == "text" for page in document.containers for block in page.blocks)
        table_count = sum(block.kind == "table" for page in document.containers for block in page.blocks)
        image_count = sum(block.kind == "image" for page in document.containers for block in page.blocks)
        assert text_count or any(warning.code == "IMAGE_ONLY_PAGE" for warning in document.parse_warnings)
        memory = process.memory_info()
        print(
            "REAL_PDF_METRICS",
            {
                "sample_id": "S-07",
                "source_before": before,
                "source_after": after,
                "bytes": staged.size_bytes,
                "page_count": document.container_count,
                "text_count": text_count,
                "table_count": table_count,
                "image_count": image_count,
                "duration_seconds": duration,
                "peak_memory_bytes": int(getattr(memory, "peak_wset", memory.rss)),
            },
        )
    finally:
        assert fingerprint(S07) == before
        WorkspaceCleaner(work_root).clean_task(task_id)
        assert not (work_root / str(task_id)).exists()
        if work_root.exists() and not any(work_root.iterdir()):
            work_root.rmdir()
