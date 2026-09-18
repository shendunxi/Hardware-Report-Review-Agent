"""Read-only legacy XLS parser backed by xlrd and olefile."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from uuid import NAMESPACE_URL, UUID, uuid5

import olefile
import xlrd

from hw_review.domain.hashing import normalized_text_hash, ordered_identity_hash
from hw_review.domain.models import (
    ContentBlock,
    DocumentContainer,
    ParseWarning,
    ReportDocument,
    StagedFile,
    TableCell,
)
from hw_review.parsers.base import ParserError, a1_address


class XlsParseError(ParserError):
    """Stable XLS-specific parse failure."""


class XlsParser:
    """Normalize a verified staged BIFF workbook without recalculation."""

    format = "XLS"
    version = "xlrd-2.0.2+olefile-0.47/v1"
    _ole_signature = bytes.fromhex("D0CF11E0A1B11AE1")

    def parse(self, staged: StagedFile) -> ReportDocument:
        if staged.detected_format != self.format:
            raise XlsParseError("WRONG_FORMAT", "XLS parser requires detected format XLS")
        payload = self._verified_payload(staged)
        if not payload.startswith(self._ole_signature):
            raise XlsParseError(
                "CORRUPT_WORKBOOK", "XLS payload is not an OLE compound workbook"
            )
        try:
            workbook = xlrd.open_workbook(
                file_contents=payload,
                formatting_info=True,
                on_demand=False,
            )
        except xlrd.biffh.XLRDError as error:
            lowered = str(error).casefold()
            code = (
                "UNSUPPORTED_OR_ENCRYPTED"
                if "encrypt" in lowered or "password" in lowered or "unsupported" in lowered
                else "CORRUPT_WORKBOOK"
            )
            raise XlsParseError(code, "XLS workbook cannot be read") from error
        except (OSError, EOFError, ValueError, IndexError) as error:
            raise XlsParseError("CORRUPT_WORKBOOK", "XLS workbook cannot be read") from error

        document_id = uuid5(NAMESPACE_URL, f"xls:{staged.id}:{staged.sha256}")
        containers, cell_warnings = self._sheet_containers(workbook, document_id)
        object_specs = self._inventory_ole_objects(staged.path)
        containers = self._attach_objects(containers, object_specs)
        warnings = (
            ParseWarning(
                code="FORMULA_METADATA_UNAVAILABLE",
                message=(
                    "xlrd exposes cached cell values but not original formula text; "
                    "no formula was recalculated or inferred"
                ),
            ),
            *cell_warnings,
        )
        digest = self._document_digest(containers)
        return ReportDocument(
            id=document_id,
            source_file_id=staged.id,
            format=self.format,
            parser_version=self.version,
            container_count=len(containers),
            text_digest=digest,
            parse_warnings=warnings,
            containers=containers,
        )

    @staticmethod
    def _verified_payload(staged: StagedFile) -> bytes:
        try:
            payload = Path(staged.path).read_bytes()
        except OSError as error:
            raise XlsParseError(
                "STAGED_FILE_CHANGED", "staged XLS payload is unavailable"
            ) from error
        if len(payload) != staged.size_bytes:
            raise XlsParseError("STAGED_FILE_CHANGED", "staged XLS size has changed")
        if hashlib.sha256(payload).hexdigest() != staged.sha256:
            raise XlsParseError("STAGED_FILE_CHANGED", "staged XLS hash has changed")
        return payload

    def _sheet_containers(
        self, workbook: xlrd.book.Book, document_id: UUID
    ) -> tuple[tuple[DocumentContainer, ...], tuple[ParseWarning, ...]]:
        containers: list[DocumentContainer] = []
        warnings: list[ParseWarning] = []
        for sheet_index in range(workbook.nsheets):
            sheet = workbook.sheet_by_index(sheet_index)
            escaped_name = quote(sheet.name, safe="")
            prefix = f"sheet:{sheet_index}:{escaped_name}"
            merged_by_master = {
                (row_start, column_start): (
                    f"{a1_address(row_start, column_start)}:"
                    f"{a1_address(row_end - 1, column_end - 1)}"
                )
                for row_start, row_end, column_start, column_end in sheet.merged_cells
            }
            cells: list[TableCell] = []
            for row in range(sheet.nrows):
                for column in range(sheet.ncols):
                    cell = sheet.cell(row, column)
                    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                        continue
                    address = a1_address(row, column)
                    structural_address = f"{prefix}/cell:{address}"
                    try:
                        raw_value, display_value = self._cell_values(
                            cell, workbook.datemode
                        )
                    except (OverflowError, ValueError):
                        raw_value = cell.value
                        display_value = str(cell.value)
                        warnings.append(
                            ParseWarning(
                                code="DATE_VALUE_OUT_OF_RANGE",
                                message=(
                                    "date-formatted numeric value is outside the "
                                    "supported datetime range; raw value retained"
                                ),
                                structural_address=structural_address,
                            )
                        )
                    cells.append(
                        TableCell(
                            row=row,
                            column=column,
                            address=address,
                            structural_address=structural_address,
                            raw_value=raw_value,
                            display_value=display_value,
                            formula_if_available=None,
                            cached_formula_value=None,
                            merged_range=merged_by_master.get((row, column)),
                            content_hash=normalized_text_hash(display_value),
                        )
                    )
            blocks: tuple[ContentBlock, ...] = ()
            container_id = uuid5(document_id, f"container:{sheet_index}:{sheet.name}")
            if cells:
                first, last = cells[0].address, cells[-1].address
                structural_address = f"{prefix}/range:{first}:{last}"
                block_hash = ordered_identity_hash(
                    f"{cell.structural_address}\0{cell.content_hash}" for cell in cells
                )
                blocks = (
                    ContentBlock(
                        id=uuid5(container_id, structural_address),
                        kind="table",
                        order=0,
                        structural_address=structural_address,
                        content_hash=block_hash,
                        cells=tuple(cells),
                    ),
                )
            containers.append(
                DocumentContainer(
                    id=container_id,
                    kind="sheet",
                    name_or_number=sheet.name,
                    order=sheet_index,
                    blocks=blocks,
                )
            )
        return tuple(containers), tuple(warnings)

    @staticmethod
    def _cell_values(cell: xlrd.sheet.Cell, datemode: int) -> tuple[object, str]:
        if cell.ctype == xlrd.XL_CELL_TEXT:
            return cell.value, cell.value
        if cell.ctype == xlrd.XL_CELL_NUMBER:
            return cell.value, str(cell.value)
        if cell.ctype == xlrd.XL_CELL_DATE:
            converted = xlrd.xldate.xldate_as_datetime(cell.value, datemode)
            display = converted.isoformat(sep=" ")
            return cell.value, display
        if cell.ctype == xlrd.XL_CELL_BOOLEAN:
            value = bool(cell.value)
            return value, "TRUE" if value else "FALSE"
        if cell.ctype == xlrd.XL_CELL_ERROR:
            return int(cell.value), xlrd.biffh.error_text_from_code.get(
                cell.value, f"#ERROR({int(cell.value)})"
            )
        return cell.value, str(cell.value)

    @staticmethod
    def _inventory_ole_objects(path: Path) -> tuple[tuple[str, str, str], ...]:
        core_streams = {
            "workbook",
            "book",
            "\x05summaryinformation",
            "\x05documentsummaryinformation",
        }
        try:
            compound = olefile.OleFileIO(str(path))
            try:
                objects: list[tuple[str, str, str]] = []
                entries = sorted(
                    compound.listdir(streams=True, storages=False),
                    key=lambda parts: tuple(part.casefold() for part in parts),
                )
                for parts in entries:
                    if not parts or (
                        len(parts) == 1 and parts[0].casefold() in core_streams
                    ):
                        continue
                    joined = "/".join(parts)
                    stream = compound.openstream(parts)
                    try:
                        digest = hashlib.sha256()
                        while True:
                            chunk = stream.read(1024 * 1024)
                            if not chunk:
                                break
                            digest.update(chunk)
                    finally:
                        stream.close()
                    extension = Path(parts[-1]).suffix.casefold()
                    kind = (
                        "image"
                        if extension in {".bmp", ".dib", ".gif", ".jpeg", ".jpg", ".png"}
                        or parts[-1].casefold() == "pictures"
                        else "attachment"
                    )
                    objects.append((kind, joined, digest.hexdigest()))
                return tuple(objects)
            finally:
                compound.close()
        except (OSError, IOError, ValueError) as error:
            raise XlsParseError(
                "CORRUPT_WORKBOOK", "XLS OLE directory cannot be inspected"
            ) from error

    @staticmethod
    def _attach_objects(
        containers: tuple[DocumentContainer, ...],
        objects: tuple[tuple[str, str, str], ...],
    ) -> tuple[DocumentContainer, ...]:
        if not objects or not containers:
            return containers
        first = containers[0]
        blocks = list(first.blocks)
        for kind, name, content_hash in objects:
            address = f"workbook/object:{quote(name, safe='')}"
            blocks.append(
                ContentBlock(
                    id=uuid5(first.id, address),
                    kind=kind,
                    order=len(blocks),
                    structural_address=address,
                    content_hash=content_hash,
                )
            )
        return (
            first.model_copy(update={"blocks": tuple(blocks)}),
            *containers[1:],
        )

    def _document_digest(self, containers: tuple[DocumentContainer, ...]) -> str:
        return ordered_identity_hash(
            f"{container.order}\0{block.order}\0{block.structural_address}\0{block.content_hash}"
            for container in containers
            for block in container.blocks
        )
