"""DOC/DOCX parser using only the isolated :mod:`word_worker` contract."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pymupdf

from hw_review.domain.hashing import normalize_display_text, normalized_text_hash, ordered_identity_hash
from hw_review.domain.models import (
    ContentBlock,
    ConversionProvenance,
    DocumentContainer,
    ParseWarning,
    ReportDocument,
    StagedFile,
    TableCell,
)
from hw_review.parsers.base import a1_address
from hw_review.parsers.word_worker import (
    POLICY_MICROSOFT_ONLY,
    ConversionArtifacts,
    DocConversionError,
    WordWorker,
)


DocParseError = DocConversionError


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DocParser:
    """Normalize Word structure while retaining hashes for all derived artifacts."""

    version = "word-isolated-worker/v1"

    def __init__(
        self,
        *,
        worker=None,
        timeout_seconds: int = 1200,
        format: str = "DOC",
        word_policy: str = POLICY_MICROSOFT_ONLY,
    ) -> None:
        normalized = format.strip().upper()
        if normalized not in {"DOC", "DOCX"}:
            raise ValueError("DocParser format must be DOC or DOCX")
        self.format = normalized
        self._worker = worker or WordWorker(policy=word_policy)
        self._timeout_seconds = timeout_seconds

    def parse(self, staged: StagedFile) -> ReportDocument:
        if staged.detected_format != self.format:
            raise DocParseError("WRONG_FORMAT", f"{self.format} parser requires detected format {self.format}")
        self._verify_source(staged)
        output_dir = staged.path.parents[1] / "conversion" / str(staged.id)
        try:
            artifacts = self._worker.convert(staged.path, output_dir, self._timeout_seconds)
            self._validate_artifacts(staged, output_dir, artifacts)
            return self._normalize(staged, artifacts)
        except TimeoutError as error:
            self._clean_output(output_dir)
            raise DocParseError("DOC_CONVERSION_TIMEOUT", "Word conversion exceeded its deadline") from error
        except DocParseError:
            self._clean_output(output_dir)
            raise
        except Exception as error:
            self._clean_output(output_dir)
            raise DocParseError("DOC_ARTIFACT_INVALID", "Word conversion artifacts are invalid") from error

    @staticmethod
    def _verify_source(staged: StagedFile) -> None:
        try:
            if staged.path.stat().st_size != staged.size_bytes or _sha256(staged.path) != staged.sha256:
                raise DocParseError("STAGED_FILE_CHANGED", "staged Word file size or hash has changed")
        except OSError as error:
            raise DocParseError("STAGED_FILE_CHANGED", "staged Word file is unavailable") from error

    @staticmethod
    def _validate_artifacts(staged: StagedFile, output_dir: Path, artifacts: ConversionArtifacts) -> None:
        output_base = output_dir.resolve()
        target = artifacts.pdf_path.parent.resolve()
        if target.parent != output_base or target.name != str(artifacts.attempt_id):
            raise DocParseError("DOC_ARTIFACT_INVALID", "conversion attempt identity mismatch")
        if artifacts.source_path.resolve() != staged.path.resolve():
            raise DocParseError("DOC_ARTIFACT_INVALID", "conversion source path mismatch")
        if artifacts.source_sha256 != staged.sha256 or artifacts.source_size_bytes != staged.size_bytes:
            raise DocParseError("DOC_ARTIFACT_INVALID", "conversion source identity mismatch")
        for path, expected_size, expected in (
            (artifacts.pdf_path, artifacts.pdf_size_bytes, artifacts.pdf_sha256),
            (artifacts.html_path, artifacts.html_size_bytes, artifacts.html_sha256),
            (
                artifacts.structured_json_path,
                artifacts.structured_json_size_bytes,
                artifacts.structured_json_sha256,
            ),
        ):
            try:
                resolved = path.resolve(strict=True)
            except OSError as error:
                raise DocParseError("DOC_ARTIFACT_INVALID", "conversion artifact is missing") from error
            if path.is_symlink() or resolved.parent != target or not resolved.is_file():
                raise DocParseError("DOC_ARTIFACT_INVALID", "conversion artifact escaped task directory")
            if resolved.stat().st_size != expected_size:
                raise DocParseError("DOC_ARTIFACT_INVALID", "conversion artifact size mismatch")
            if _sha256(resolved) != expected:
                raise DocParseError("DOC_ARTIFACT_INVALID", "conversion artifact hash mismatch")
        if _sha256(staged.path) != staged.sha256:
            raise DocParseError("STAGED_FILE_CHANGED", "staged Word file changed during conversion")

    def _normalize(self, staged: StagedFile, artifacts: ConversionArtifacts) -> ReportDocument:
        try:
            structure = json.loads(artifacts.structured_json_path.read_text(encoding="utf-8"))
            paragraphs = structure["paragraphs"]
            tables = structure["tables"]
            if not isinstance(paragraphs, list) or not isinstance(tables, list):
                raise TypeError("structure arrays required")
            visual = pymupdf.open(artifacts.pdf_path)
        except Exception as error:
            raise DocParseError("DOC_ARTIFACT_INVALID", "structured Word artifact cannot be read") from error
        try:
            page_count = visual.page_count
            by_page: dict[int, list[tuple[tuple, str, object]]] = defaultdict(list)
            for item in paragraphs:
                page = max(1, int(item["page"]))
                index = int(item["index"])
                text = normalize_display_text(str(item["text"]))
                if text:
                    by_page[page].append(((0, index), "paragraph", (index, text)))
            for item in tables:
                page = max(1, int(item["page"]))
                index = int(item["index"])
                by_page[page].append(((1, index), "table", (index, item["cells"])))
            max_page = max([page_count, *by_page.keys()], default=0)
            document_id = uuid5(
                NAMESPACE_URL,
                f"{self.format.lower()}:{staged.id}:{staged.sha256}:{artifacts.pdf_sha256}:{artifacts.structured_json_sha256}",
            )
            warnings: list[ParseWarning] = []
            containers = []
            for page_number in range(1, max_page + 1):
                page_address = f"page:{page_number}"
                specs = sorted(by_page.get(page_number, []), key=lambda item: item[0])
                blocks: list[ContentBlock] = []
                container_id = uuid5(document_id, page_address)
                for _, kind, value in specs:
                    if kind == "paragraph":
                        index, text = value
                        address = f"{page_address}/paragraph:{index}"
                        blocks.append(
                            ContentBlock(
                                id=uuid5(container_id, address),
                                kind="text",
                                order=len(blocks),
                                structural_address=address,
                                text=text,
                                content_hash=normalized_text_hash(text),
                            )
                        )
                    else:
                        index, raw_cells = value
                        cells = []
                        for raw in raw_cells:
                            row = int(raw["row"]) - 1
                            column = int(raw["column"]) - 1
                            display = normalize_display_text(str(raw["text"]))
                            if not display:
                                continue
                            address = a1_address(row, column)
                            locator = f"{page_address}/table:{index}/cell:{address}"
                            cells.append(
                                TableCell(
                                    row=row,
                                    column=column,
                                    address=address,
                                    structural_address=locator,
                                    raw_value=display,
                                    display_value=display,
                                    content_hash=normalized_text_hash(display),
                                )
                            )
                        cells.sort(key=lambda cell: (cell.row, cell.column))
                        if cells:
                            address = f"{page_address}/table:{index}"
                            blocks.append(
                                ContentBlock(
                                    id=uuid5(container_id, address),
                                    kind="table",
                                    order=len(blocks),
                                    structural_address=address,
                                    content_hash=ordered_identity_hash(
                                        f"{cell.structural_address}\0{cell.content_hash}" for cell in cells
                                    ),
                                    cells=tuple(cells),
                                )
                            )
                if page_number <= page_count:
                    visual_page = visual.load_page(page_number - 1)
                    if not normalize_display_text(visual_page.get_text("text")):
                        warnings.append(
                            ParseWarning(
                                code="IMAGE_ONLY_PAGE",
                                message="converted page has no readable text layer; OCR was not attempted",
                                structural_address=page_address,
                            )
                        )
                    occurrences: list[
                        tuple[tuple[float, float, float, float] | None, int, int]
                    ] = []
                    seen_xrefs: set[int] = set()
                    for image_info in visual_page.get_images(full=True):
                        xref = int(image_info[0])
                        if xref in seen_xrefs:
                            continue
                        seen_xrefs.add(xref)
                        try:
                            rects = visual_page.get_image_rects(xref)
                        except Exception:
                            rects = []
                        if rects:
                            occurrences.extend(
                                (tuple(float(value) for value in rect), xref, occurrence)
                                for occurrence, rect in enumerate(rects)
                            )
                        else:
                            occurrences.append((None, xref, 0))
                    occurrences.sort(
                        key=lambda item: self._bbox_key(item[0])
                        + (item[1], item[2])
                    )
                    for image_index, (bbox, xref, occurrence) in enumerate(
                        occurrences, start=1
                    ):
                        try:
                            payload = visual.extract_image(xref).get("image", b"")
                            if not isinstance(payload, bytes) or not payload:
                                raise ValueError("image bytes unavailable")
                            content_hash = hashlib.sha256(payload).hexdigest()
                        except Exception:
                            fallback = (
                                f"{artifacts.pdf_sha256}\0{page_number}\0{xref}\0{occurrence}"
                            ).encode("utf-8")
                            content_hash = hashlib.sha256(fallback).hexdigest()
                        address = f"{page_address}/image:{image_index}"
                        blocks.append(
                            ContentBlock(
                                id=uuid5(container_id, address),
                                kind="image",
                                order=len(blocks),
                                structural_address=address,
                                bbox=bbox,
                                content_hash=content_hash,
                            )
                        )
                containers.append(
                    DocumentContainer(
                        id=container_id,
                        kind="page",
                        name_or_number=page_number,
                        order=page_number - 1,
                        blocks=tuple(blocks),
                    )
                )
            container_tuple = tuple(containers)
            return ReportDocument(
                id=document_id,
                source_file_id=staged.id,
                format=self.format,
                parser_version=self.version,
                container_count=len(container_tuple),
                text_digest=ordered_identity_hash(
                    f"{container.order}\0{block.order}\0{block.structural_address}\0{block.content_hash}"
                    for container in container_tuple
                    for block in container.blocks
                ),
                parse_warnings=tuple(warnings),
                containers=container_tuple,
                conversion_provenance=ConversionProvenance(
                    source_sha256=artifacts.source_sha256,
                    pdf_sha256=artifacts.pdf_sha256,
                    html_sha256=artifacts.html_sha256,
                    structured_json_sha256=artifacts.structured_json_sha256,
                    word_version=artifacts.word_version,
                    duration_seconds=artifacts.duration_seconds,
                    peak_memory_bytes=artifacts.peak_memory_bytes,
                    automation_host=artifacts.automation_host,
                ),
            )
        finally:
            visual.close()

    @staticmethod
    def _bbox_key(bbox):
        if bbox is None:
            return (float("inf"),) * 4
        return (bbox[1], bbox[0], bbox[3], bbox[2])

    @staticmethod
    def _clean_output(output_dir: Path) -> None:
        if output_dir.exists() and not output_dir.is_symlink():
            shutil.rmtree(output_dir)
