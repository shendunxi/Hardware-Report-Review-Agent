import pytest

from hw_review.rules.a11_registry import A11Registry


EXPECTED_ROWS = (
    ("TR-01", 10, 1, "JIRA项目及链接", "JIRA项目已建立；报告包含对应链接", "JIRA页面截图/导出件、报告", "RULE", True),
    ("TR-02", 13, 2, "上阶段问题确认及回归", "识别上阶段问题、状态及需回归项的回归记录", "上阶段问题清单、状态、回归记录", "RULE_PLUS_AI", True),
    ("TR-03", 14, 3, "软件相关问题处理", "软件相关FAIL已登记；有处理说明；评审后关闭；已通知相应负责人", "FAIL清单、定位结论、JIRA、评审和通知记录", "RULE_PLUS_AI", True),
    ("TR-04", 15, 4, "功耗记录", "典型工作功耗、待机功耗均存在，并登记至指定记录", "报告功耗数据、共享记录导出件/截图", "RULE", True),
    ("TR-05", 16, 5, "共享路径", "不独立执行", "无独立材料", "DISABLED", False),
    ("TR-06", 17, 6, "委外测试安排", "存在内部无法执行的需求时，有原因和委外安排", "需求清单、能力限制、委外证明", "RULE_PLUS_AI", True),
    ("TR-07", 18, 7, "报告版本及命名", "版本、文件名及报告内项目/阶段信息符合已发布规则", "报告、正式命名规则", "RULE", True),
    ("TR-08", 19, 8, "首页填写", "已发布必填字段均存在，且与正文一致", "首页、必填字段清单", "RULE_PLUS_AI", True),
    ("TR-09", 20, 9, "测试用例选择", "机型和区域对应的必选用例无遗漏", "机型/区域/标准/用例对应表、报告", "RULE", True),
    ("TR-10", 21, 10, "测试数据完整性", "每个应测项有记录；必填数据无空缺；未执行项有原因", "应测项清单、用例、报告", "RULE", True),
    ("TR-11", 22, 11, "数据与纸质记录一致", "数值格式有效，且与纸质原始记录一致", "报告、纸质记录扫描件/照片", "RULE", True),
    ("TR-12", 23, 12, "小结和结论正确", "小结引用数据存在；小结、最终结论与数据一致", "报告数据、小结、结论", "RULE_PLUS_AI", True),
    ("TR-13", 24, 13, "问题无漏写漏总结", "原始记录问题进入问题清单，问题清单项目在小结/结论得到处理", "原始记录、日志、问题清单、小结、结论", "AI", True),
    ("TR-14", 25, 14, "EMC报告及JIRA处理", "适用时有EMC报告；合格余量≥3dB；有JIRA；异常已登记", "适用性依据、EMC报告、JIRA记录", "RULE_PLUS_AI", True),
    ("TR-15", 26, 15, "阶段报告衔接", "当前阶段明确；引用历史记录；无未解释的结论冲突", "当前及以前阶段报告", "RULE_PLUS_AI", True),
    ("TR-16", 27, 16, "结论重点及顺序", "需要关注的问题被突出；排列满足已发布排序依据", "结论、问题清单、排序依据", "AI", True),
    ("TR-17", 28, 17, "问题表述", "每条问题包含测试对象、测试条件、观察现象、实际结果", "问题清单", "AI", True),
    ("TR-18", 29, 18, "单条结论目标单一", "一条结论只表达一个可独立处理的问题", "结论、问题清单", "AI", True),
    ("TR-19", 30, 19, "CA卡工装温升测试", "适用时存在温升测试记录和结果", "适用性信息、温升记录", "RULE", True),
    ("TR-20", 31, 20, "PP阶段开关机自动化", "PP阶段存在自动化测试记录和结果", "阶段信息、自动化测试记录", "RULE", True),
    ("TR-21", 32, 21, "WIFI结论填写", "WIFI报告内小结论和页面顶端结论均非空", "WIFI报告", "RULE", True),
    ("TR-22", 33, 22, "温升部件喷漆状态", "适用性明确；证据可识别CPU散热器和tuner屏蔽框喷漆状态，并可与已发布要求比较", "温升报告、照片/记录、喷漆要求", "RULE_PLUS_AI", True),
)

EXPECTED_BOUNDARIES = (
    "[你说的] 不臆造链接格式；未提供JIRA证据则不符合，材料存在但合法性依据不足则待人工确认",
    "[我推断的] 不能仅因当前报告未提旧问题而判符合",
    "[你说的] 产品显示用语统一为“软件测试团队经理”；源模板文字不改",
    "[你说的] 任一功耗缺失则不符合；共享记录未提供则登记项不符合",
    "[你说的] 作为TR-04证据地址保留源行和导出位置，不计入执行项",
    "[我推断的] 无内部能力限制时须有依据才判不适用",
    "[你说的] 不臆造命名规则；依据未提供但材料已存在时待人工确认",
    "[你说的] 不臆造首页必填字段；清单未定义时待人工确认",
    "[你说的] 不臆造映射；映射未定义时待人工确认，已定义但任务缺机型/区域证据时不符合",
    "[我推断的] 报告可读且必填项为空时不符合；应测清单属必需证据时未上传则不符合",
    "[你说的] 纸质记录未上传则不符合，不能只查报告内部格式后判符合",
    "[我推断的] “正确”仅指与已提供证据一致，不作产品质量最终裁决",
    "[我推断的] 只有最终报告时只能检查内部一致性，不能证明无漏写",
    "[我推断的] 无需EMC须有依据后才判不适用",
    "[你说的] 历史报告属于必需证据时未提供则不符合",
    "[你说的] 不设置严重性，不臆造排序规则；依据不足时待人工确认",
    "[你说的] 固定按上述4个要素判定",
    "[我推断的] 是否同一问题按对象、现象和处理动作共同判断",
    "[我推断的] 不适用须有依据；适用性材料属必需证据时未提供则不符合",
    "[你说的] 非PP阶段不适用；阶段信息缺失则不符合",
    "[你说的] 只检查两处是否填写，不检查内容一致性",
    "[你说的] 不臆造期望状态；照片等必需证据未上传则不符合，期望要求未定义而材料已提供则待人工确认",
)


def test_registry_matches_all_frozen_source_rows_exactly() -> None:
    rows = A11Registry.source_rows()
    actual = tuple(
        (
            row.id,
            row.source_row,
            row.source_sequence,
            row.summary,
            row.verifiable_requirement,
            row.required_materials,
            row.main_judgment,
            row.enabled,
        )
        for row in rows
    )

    assert actual == EXPECTED_ROWS
    assert {row.baseline_version for row in rows} == {"A11"}
    assert {row.registry_version for row in rows} == {"a11-registry-1"}
    assert tuple(row.confirmed_boundary for row in rows) == EXPECTED_BOUNDARIES


def test_registry_has_22_source_rows_and_21_ordered_executed_rules() -> None:
    assert len(A11Registry.source_rows()) == 22
    assert [row.id for row in A11Registry.executed_rules()] == [
        f"TR-{number:02d}" for number in range(1, 23) if number != 5
    ]
    assert A11Registry.get("TR-05").enabled is False
    assert A11Registry.get("TR-05").main_judgment == "DISABLED"


@pytest.mark.parametrize("unknown", ["TR-00", "TR-23", "tr-01", "TR-1", ""])
def test_registry_unknown_or_alias_lookup_fails_stably(unknown: str) -> None:
    with pytest.raises(KeyError) as error:
        A11Registry.get(unknown)

    assert error.value.args == (f"unknown A11 rule ID: {unknown}",)
