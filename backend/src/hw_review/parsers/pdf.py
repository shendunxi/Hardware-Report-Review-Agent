"""Deterministic read-only PDF parser using the supported PyMuPDF module."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import pymupdf

from hw_review.domain.hashing import normalize_display_text, normalized_text_hash, ordered_identity_hash
from hw_review.domain.models import (
    ContentBlock,
    DocumentContainer,
    ParseWarning,
    ReportDocument,
    StagedFile,
    TableCell,
)
from hw_review.parsers.base import ParserError, a1_address


class PdfParseError(ParserError):
    """Stable PDF parsing failure."""


@dataclass(frozen=True, slots=True)
class _BlockSpec:
    kind: str
    address: str
    bbox: tuple[float, float, float, float] | None
    content_hash: str
    text: str | None = None
    cells: tuple[TableCell, ...] = ()


class PdfParser:
    """Normalize a verified staged PDF without OCR or content inference."""

    format = "PDF"
    version = f"pymupdf-{pymupdf.__version__}/v1"

    def parse(self, staged: StagedFile) -> ReportDocument:
        if staged.detected_format != self.format:
            raise PdfParseError("WRONG_FORMAT", "PDF parser requires detected format PDF")
        self._verify_staged(staged)
        try:
            document = pymupdf.open(staged.path)
        except Exception as error:
            raise PdfParseError("PDF_CORRUPT", "PDF cannot be opened") from error
        try:
            if document.needs_pass:
                raise PdfParseError("PDF_PROTECTED", "password-protected PDF is unsupported")
            document_id = uuid5(NAMESPACE_URL, f"pdf:{staged.id}:{staged.sha256}")
            containers: list[DocumentContainer] = []
            warnings: list[ParseWarning] = []
            for page_index in range(document.page_count):
                page_number = page_index + 1
                page_address = f"page:{page_number}"
                try:
                    page = document.load_page(page_index)
                    specs, has_text = self._page_specs(document, page, page_number, staged.sha256)
                except PdfParseError:
                    raise
                except Exception as error:
                    raise PdfParseError("PDF_CORRUPT", "PDF page cannot be read") from error
                try:
                    specs.extend(self._table_blocks(page, page_number))
                except Exception:
                    warnings.append(
                        ParseWarning(
                            code="TABLE_DISCOVERY_FAILED",
                            message="optional PDF table discovery failed; other page content was retained",
                            structural_address=page_address,
                        )
                    )
                specs.sort(key=self._visual_key)
                container_id = uuid5(document_id, page_address)
                blocks = tuple(
                    ContentBlock(
                        id=uuid5(container_id, spec.address),
                        kind=spec.kind,
                        order=order,
                        structural_address=spec.address,
                        text=spec.text,
                        bbox=spec.bbox,
                        content_hash=spec.content_hash,
                        cells=spec.cells,
                    )
                    for order, spec in enumerate(specs)
                )
                if not has_text:
                    warnings.append(
                        ParseWarning(
                            code="IMAGE_ONLY_PAGE",
                            message="page has no readable text layer; OCR was not attempted",
                            structural_address=page_address,
                        )
                    )
                containers.append(
                    DocumentContainer(
                        id=container_id,
                        kind="page",
                        name_or_number=page_number,
                        order=page_index,
                        blocks=blocks,
                    )
                )
            container_tuple = tuple(containers)
            return ReportDocument(
                id=document_id,
                source_file_id=staged.id,
                format="PDF",
                parser_version=self.version,
                container_count=len(container_tuple),
                text_digest=self._digest(container_tuple),
                parse_warnings=tuple(warnings),
                containers=container_tuple,
            )
        except PdfParseError:
            raise
        except (RuntimeError, ValueError, OSError) as error:
            raise PdfParseError("PDF_CORRUPT", "PDF content is corrupt or unsupported") from error
        finally:
            document.close()

    @staticmethod
    def _verify_staged(staged: StagedFile) -> None:
        try:
            size = staged.path.stat().st_size
            digest = hashlib.sha256()
            with staged.path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as error:
            raise PdfParseError("STAGED_FILE_CHANGED", "staged PDF is unavailable") from error
        if size != staged.size_bytes or digest.hexdigest() != staged.sha256:
            raise PdfParseError("STAGED_FILE_CHANGED", "staged PDF size or hash has changed")

    def _page_specs(self, document, page, page_number: int, source_hash: str):
        specs: list[_BlockSpec] = []
        text_entries: list[tuple[tuple[float, float, float, float], str]] = []
        for raw in page.get_text("blocks", sort=False):
            if len(raw) < 5 or (len(raw) > 6 and raw[6] != 0):
                continue
            text = normalize_display_text(str(raw[4]))
            if not text:
                continue
            bbox = tuple(float(value) for value in raw[:4])
            text_entries.append((bbox, text))
        text_entries.sort(key=lambda item: (item[0][1], item[0][0], item[0][3], item[0][2], item[1]))
        for index, (bbox, text) in enumerate(text_entries, start=1):
            specs.append(
                _BlockSpec(
                    kind="text",
                    address=f"page:{page_number}/text:{index}",
                    bbox=bbox,
                    text=text,
                    content_hash=normalized_text_hash(text),
                )
            )

        occurrences: list[tuple[tuple[float, float, float, float] | None, int, int]] = []
        seen_xrefs: set[int] = set()
        for image_info in page.get_images(full=True):
            xref = int(image_info[0])
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            try:
                rectangles = page.get_image_rects(xref)
            except Exception:
                rectangles = []
            if rectangles:
                occurrences.extend((tuple(float(v) for v in rect), xref, i) for i, rect in enumerate(rectangles))
            else:
                occurrences.append((None, xref, 0))
        occurrences.sort(key=lambda item: self._bbox_key(item[0]) + (item[1], item[2]))
        for index, (bbox, xref, occurrence) in enumerate(occurrences, start=1):
            content_hash = self._image_content_hash(
                document, source_hash, page_number, xref, occurrence
            )
            specs.append(
                _BlockSpec(
                    kind="image",
                    address=f"page:{page_number}/image:{index}",
                    bbox=bbox,
                    content_hash=content_hash,
                )
            )
        return specs, bool(text_entries)

    @staticmethod
    def _image_content_hash(
        document, source_hash: str, page_number: int, xref: int, occurrence: int
    ) -> str:
        try:
            payload = document.extract_image(xref).get("image", b"")
            if not isinstance(payload, bytes) or not payload:
                raise ValueError("image bytes unavailable")
            return hashlib.sha256(payload).hexdigest()
        except Exception:
            fallback = f"{source_hash}\0{page_number}\0{xref}\0{occurrence}".encode(
                "utf-8"
            )
            return hashlib.sha256(fallback).hexdigest()

    def _table_blocks(self, page, page_number: int) -> list[_BlockSpec]:
        finder = getattr(page, "find_tables", None)
        if finder is None:
            return []
        result = finder()
        tables = list(getattr(result, "tables", ()))
        tables.sort(key=lambda table: self._bbox_key(tuple(float(v) for v in table.bbox)))
        output: list[_BlockSpec] = []
        for table_index, table in enumerate(tables, start=1):
            matrix = table.extract()
            cells: list[TableCell] = []
            for row, values in enumerate(matrix):
                for column, value in enumerate(values):
                    if value is None or not normalize_display_text(str(value)):
                        continue
                    display = normalize_display_text(str(value))
                    address = a1_address(row, column)
                    locator = f"page:{page_number}/table:{table_index}/cell:{address}"
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
            if not cells:
                continue
            block_address = f"page:{page_number}/table:{table_index}"
            output.append(
                _BlockSpec(
                    kind="table",
                    address=block_address,
                    bbox=tuple(float(v) for v in table.bbox),
                    content_hash=ordered_identity_hash(
                        f"{cell.structural_address}\0{cell.content_hash}" for cell in cells
                    ),
                    cells=tuple(cells),
                )
            )
        return output

    @classmethod
    def _visual_key(cls, spec: _BlockSpec):
        return cls._bbox_key(spec.bbox) + (spec.kind, spec.address)

    @staticmethod
    def _bbox_key(bbox):
        if bbox is None:
            return (float("inf"),) * 4
        return (bbox[1], bbox[0], bbox[3], bbox[2])

    @staticmethod
    def _digest(containers: tuple[DocumentContainer, ...]) -> str:
        return ordered_identity_hash(
            f"{container.order}\0{block.order}\0{block.structural_address}\0{block.content_hash}"
            for container in containers
            for block in container.blocks
        )
