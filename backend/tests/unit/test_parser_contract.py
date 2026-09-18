"""Contract tests for normalized parser output and format dispatch."""

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from hw_review.domain.enums import FileRole
from hw_review.domain.hashing import normalized_text_hash, ordered_identity_hash
from hw_review.domain.models import (
    ContentBlock,
    DocumentContainer,
    ReportDocument,
    StagedFile,
    TableCell,
)
from hw_review.parsers.base import DocumentLookupError
from hw_review.services.parsing import ParserRegistry, ParserRegistryError


def _staged() -> StagedFile:
    return StagedFile(
        id=uuid4(),
        task_id=uuid4(),
        role=FileRole.PRIMARY_REPORT,
        original_name="fixture.xls",
        detected_format="XLS",
        path=Path("fixture.xls"),
        size_bytes=0,
        sha256="0" * 64,
        source_mtime_ns=0,
    )


def _cell(source_id, *, address: str = "B2", row: int = 1, column: int = 1):
    text = "结论"
    return TableCell(
        row=row,
        column=column,
        address=address,
        structural_address=f"sheet:0:Sheet1/cell:{address}",
        raw_value=text,
        display_value=text,
        content_hash=normalized_text_hash(text),
        merged_range="B2:C2" if address == "B2" else None,
    )


def _document(staged: StagedFile) -> ReportDocument:
    cell = _cell(staged.id)
    block_hash = ordered_identity_hash(
        (f"{cell.structural_address}\0{cell.content_hash}",)
    )
    block = ContentBlock(
        id=uuid4(),
        kind="table",
        order=0,
        structural_address="sheet:0:Sheet1/range:B2:C2",
        content_hash=block_hash,
        cells=(cell,),
    )
    container = DocumentContainer(
        id=uuid4(),
        kind="sheet",
        name_or_number="Sheet1",
        order=0,
        blocks=(block,),
    )
    digest = ordered_identity_hash(
        (
            f"{container.order}\0{block.order}\0{block.structural_address}\0{block.content_hash}",
        )
    )
    return ReportDocument(
        id=uuid4(),
        source_file_id=staged.id,
        format="XLS",
        parser_version="fake-1",
        container_count=1,
        text_digest=digest,
        containers=(container,),
    )


class _FakeParser:
    format = "XLS"

    def parse(self, staged: StagedFile) -> ReportDocument:
        return _document(staged)


def test_every_parser_returns_normalized_immutable_document() -> None:
    staged = _staged()
    document = _FakeParser().parse(staged)

    assert document.source_file_id == staged.id
    assert [container.order for container in document.containers] == [0]
    assert all(
        len(block.content_hash) == 64
        for container in document.containers
        for block in container.blocks
    )
    assert document.find_cell("Sheet1", "B2").display_value == "结论"

    with pytest.raises(ValidationError):
        document.model_copy(update={"container_count": 2})
    with pytest.raises(ValidationError):
        document.containers[0].blocks = ()


def test_cross_field_invariants_reject_malformed_blocks_and_cells() -> None:
    document = _document(_staged())
    block = document.containers[0].blocks[0]

    with pytest.raises(ValidationError, match="content_hash"):
        block.model_copy(update={"content_hash": ""})
    with pytest.raises(ValidationError, match="unique"):
        block.model_copy(update={"cells": (block.cells[0], block.cells[0])})
    with pytest.raises(ValidationError, match="row"):
        block.cells[0].model_copy(update={"row": 4})


def test_collection_order_invariants_are_enforced_on_validated_copy() -> None:
    document = _document(_staged())
    block = document.containers[0].blocks[0]
    second = block.model_copy(update={"order": 1, "structural_address": "sheet:0:Sheet1/range:D4:D4"})
    malformed = second.model_copy(update={"order": 2})

    with pytest.raises(ValidationError, match="order"):
        document.containers[0].model_copy(update={"blocks": (block, malformed)})


def test_normalized_identity_hashes_reject_drift_on_construction_and_copy() -> None:
    document = _document(_staged())
    container = document.containers[0]
    block = container.blocks[0]
    cell = block.cells[0]

    with pytest.raises(ValidationError, match="content_hash"):
        cell.model_copy(update={"display_value": "changed"})

    changed_cell = cell.model_copy(
        update={
            "display_value": "changed",
            "content_hash": normalized_text_hash("changed"),
        }
    )
    with pytest.raises(ValidationError, match="ordered cell identities"):
        block.model_copy(update={"cells": (changed_cell,)})

    valid_text = ContentBlock(
        id=uuid4(),
        kind="text",
        order=0,
        structural_address="page:0/block:0",
        text="line 1\r\nline 2",
        content_hash=normalized_text_hash("line 1\nline 2"),
    )
    with pytest.raises(ValidationError, match="normalized text"):
        valid_text.model_copy(update={"text": "different"})

    changed_block = block.model_copy(
        update={
            "cells": (changed_cell,),
            "content_hash": ordered_identity_hash(
                (
                    f"{changed_cell.structural_address}\0{changed_cell.content_hash}",
                )
            ),
        }
    )
    changed_container = container.model_copy(update={"blocks": (changed_block,)})
    with pytest.raises(ValidationError, match="text_digest"):
        document.model_copy(update={"containers": (changed_container,)})


def test_sheet_locator_prefix_tracks_container_name_and_order() -> None:
    document = _document(_staged())
    container = document.containers[0]
    block = container.blocks[0]
    cell = block.cells[0]

    with pytest.raises(ValidationError, match="sheet locator prefix"):
        container.model_copy(update={"name_or_number": "Renamed"})
    with pytest.raises(ValidationError, match="sheet locator prefix"):
        container.model_copy(update={"order": 1})

    wrong_cell = cell.model_copy(
        update={"structural_address": "sheet:9:Sheet1/cell:B2"}
    )
    wrong_block = block.model_copy(
        update={
            "cells": (wrong_cell,),
            "content_hash": ordered_identity_hash(
                (f"{wrong_cell.structural_address}\0{wrong_cell.content_hash}",)
            ),
        }
    )
    with pytest.raises(ValidationError, match="sheet locator prefix"):
        container.model_copy(update={"blocks": (wrong_block,)})

    deceptive_cell = cell.model_copy(
        update={
            "structural_address": "sheet:0:Sheet1/cell:alias/cell:B2",
        }
    )
    deceptive_block = block.model_copy(
        update={
            "cells": (deceptive_cell,),
            "content_hash": ordered_identity_hash(
                (
                    f"{deceptive_cell.structural_address}\0"
                    f"{deceptive_cell.content_hash}",
                )
            ),
        }
    )
    with pytest.raises(ValidationError, match="sheet locator prefix"):
        container.model_copy(update={"blocks": (deceptive_block,)})

    opaque = ContentBlock(
        id=uuid4(),
        kind="attachment",
        order=1,
        structural_address="workbook/object:opaque",
        content_hash=normalized_text_hash("opaque bytes"),
    )
    with_opaque = container.model_copy(update={"blocks": (block, opaque)})
    assert with_opaque.blocks[1] is opaque


def test_find_cell_has_stable_missing_and_duplicate_failures() -> None:
    document = _document(_staged())
    with pytest.raises(DocumentLookupError) as missing:
        document.find_cell("Sheet1", "A1")
    assert missing.value.code == "CELL_NOT_FOUND"

    first_block = document.containers[0].blocks[0]
    duplicate_block = first_block.model_copy(
        update={
            "id": uuid4(),
            "order": 1,
            "structural_address": "sheet:0:Sheet1/range:B2:B2-duplicate",
        }
    )
    duplicate_container = document.containers[0].model_copy(
        update={"blocks": (first_block, duplicate_block)}
    )
    duplicate = document.model_copy(
        update={
            "containers": (duplicate_container,),
            "text_digest": ordered_identity_hash(
                (
                    f"0\0{first_block.order}\0{first_block.structural_address}\0"
                    f"{first_block.content_hash}",
                    f"0\0{duplicate_block.order}\0{duplicate_block.structural_address}\0"
                    f"{duplicate_block.content_hash}",
                )
            ),
        }
    )
    with pytest.raises(DocumentLookupError) as duplicate_error:
        duplicate.find_cell("Sheet1", "B2")
    assert duplicate_error.value.code == "DUPLICATE_CELL"


def test_registry_dispatches_normalized_format_without_extension_logic() -> None:
    parser = _FakeParser()
    registry = ParserRegistry((parser,))

    assert registry.for_format(" xls ") is parser

    with pytest.raises(ParserRegistryError) as duplicate:
        registry.register(_FakeParser())
    assert duplicate.value.code == "DUPLICATE_PARSER"

    with pytest.raises(ParserRegistryError) as missing:
        registry.for_format("pdf")
    assert missing.value.code == "PARSER_NOT_FOUND"
