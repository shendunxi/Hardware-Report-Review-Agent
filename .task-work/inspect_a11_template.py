from __future__ import annotations

import json
from pathlib import Path

import xlrd


template_path = Path(
    r"D:\Document\AI创新应用大赛\硬件测试报告及检查表\硬件测试过程检查单.xls"
)
book = xlrd.open_workbook(template_path, formatting_info=True)
result: dict[str, object] = {
    "path": str(template_path),
    "size": template_path.stat().st_size,
    "sheets": [],
}
for sheet in book.sheets():
    rows: list[dict[str, object]] = []
    for row_index in range(sheet.nrows):
        populated = []
        for column_index in range(sheet.ncols):
            value = sheet.cell_value(row_index, column_index)
            if value not in ("", None):
                populated.append({"column": column_index + 1, "value": value})
        if populated:
            rows.append({"row": row_index + 1, "cells": populated})
    result["sheets"].append(
        {
            "name": sheet.name,
            "nrows": sheet.nrows,
            "ncols": sheet.ncols,
            "merged_cells": [list(item) for item in sheet.merged_cells],
            "rows": rows,
        }
    )

print(json.dumps(result, ensure_ascii=False, indent=2))
