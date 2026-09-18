import type { ManualDecision, ReviewRevisionSnapshot, ReviewRow, ReviewTask, RuleResult, TemplateRule } from './types'

const legacyReviewTextTranslations: ReadonlyArray<readonly [string, string]> = [
  ['All checks in this source row are explicitly proven not applicable.', '本检查表来源行中的所有校验项均已有明确证据证明不适用。'],
  ['A required material is missing or an objective check has failed.', '缺少必需材料，或某项客观校验未通过。'],
  ['No hard failure was found, but a semantic obligation remains unresolved.', '未发现确定性不符合项，但仍有语义判断事项待确认。'],
  ['Every applicable deterministic obligation is positively evidenced.', '所有适用的客观校验项均已有明确证据证明符合。'],
  [' Atomic bases: ', '判定明细代码：'],
  ['JIRA link legality cannot be proven by literal rule matching.', '仅通过文字规则匹配无法证明 JIRA 链接有效性。'],
  ['Issue, status, and regression correspondence requires semantic review.', '问题、状态与回归记录的对应关系需要语义审核。'],
  ['Review closure and manager notification correspondence require semantic review.', '问题闭环与经理通知的对应关系需要语义审核。'],
  ['Adequacy of the limitation reason and outsourcing arrangement requires semantic review.', '能力限制原因及委外安排是否充分需要语义审核。'],
  ['Published report naming/version criteria were not supplied; no criterion is invented.', '未提供已发布的报告命名/版本标准；系统不会自行推断标准。'],
  ['Comparison with the supplied naming/version criterion requires semantic review.', '与已提供的命名/版本标准进行比对需要语义审核。'],
  ['The published homepage required-field list was not supplied; field names are not invented.', '未提供已发布的首页必填字段清单；系统不会自行推断字段名。'],
  ['Published criteria are present, but a traceable homepage required-field list cannot be read.', '已提供发布标准，但无法读取可追溯的首页必填字段清单。'],
  ['The homepage required-field list contains no traceable field names.', '首页必填字段清单中没有可追溯的字段名。'],
  ['Homepage-to-body consistency requires semantic review.', '首页与正文的一致性需要语义审核。'],
  ['The model/region/standard/use-case mapping was not supplied; no mapping is invented.', '未提供机型/区域/标准/使用场景映射；系统不会自行推断映射关系。'],
  ['Mandatory-case coverage against the supplied mapping requires semantic review.', '根据已提供映射核对应测用例覆盖情况需要语义审核。'],
  ['Completeness against the supplied required-item checklist requires semantic review.', '根据已提供的应测项清单核对完整性需要语义审核。'],
  ['Cross-record numeric equality requires semantic review.', '不同记录之间的数值一致性需要语义审核。'],
  ['Data, summary, and conclusion consistency requires semantic review.', '数据、小结和结论的一致性需要语义审核。'],
  ['No-omission and no-summary-loss judgment requires LLM or manual review.', '是否存在遗漏或小结信息丢失需要大语言模型或人工审核。'],
  ['EMC anomaly and JIRA correspondence requires semantic review.', 'EMC 异常与 JIRA 记录的对应关系需要语义审核。'],
  ['Unexplained conclusion conflicts across stages require semantic review.', '跨阶段存在的未解释结论冲突需要语义审核。'],
  ['Published ordering criteria were not supplied; no severity or ordering rule is invented.', '未提供已发布的排序标准；系统不会自行推断问题分级或排序规则。'],
  ['Emphasis and ordering against the supplied criteria require LLM or manual review.', '依据已提供标准核对强调内容和排序需要大语言模型或人工审核。'],
  ['Adequacy of the four fixed problem elements requires LLM or manual review.', '四个固定问题要素是否描述充分需要大语言模型或人工审核。'],
  ['Whether each conclusion expresses one independently actionable issue requires LLM or manual review.', '每条结论是否仅描述一个可独立处理的问题，需要大语言模型或人工审核。'],
  ['The published coating expectation was not supplied; no expected state is invented.', '未提供已发布的喷漆状态要求；系统不会自行推断预期状态。'],
  ['Comparison with the supplied coating expectation requires semantic review.', '与已提供的喷漆状态要求进行比对需要语义审核。'],
]

export function localizeReviewText(value: string | null | undefined): string {
  let text = String(value ?? '')
  for (const [source, translation] of legacyReviewTextTranslations) text = text.replaceAll(source, translation)
  const marker = '判定明细代码：'
  if (!text.includes(marker)) return text
  const [summary, codes = ''] = text.split(marker, 2)
  return `${summary}${marker}${codes.replace(/, /g, '、').replace(/\.$/, '。')}`
}

function deriveRows(results: RuleResult[], decisions: ManualDecision[], rules: TemplateRule[]): ReviewRow[] {
  const decisionsByResult = new Map(decisions.map((decision) => [decision.rule_result_id, decision]))
  const rulesById = new Map(rules.map((rule) => [rule.rule_id, rule]))
  return results.map((result) => {
    const decision = decisionsByResult.get(result.id) ?? null
    return {
      ruleId: result.rule_id,
      result,
      decision,
      initialStatus: result.initial_status,
      finalStatus: decision?.final_status ?? null,
      displayStatus: decision?.final_status ?? result.initial_status,
      rule: rulesById.get(result.rule_id) ?? null,
    }
  })
}

export function deriveReviewRows(task: ReviewTask): ReviewRow[] {
  return deriveRows(task.rule_results, task.manual_decisions, task.template_rules ?? [])
}

export function deriveRevisionRows(snapshot: ReviewRevisionSnapshot): ReviewRow[] {
  return deriveRows(snapshot.results, snapshot.decisions, snapshot.template_rules ?? [])
}

export function unresolvedReviewCount(task: ReviewTask): number {
  return deriveReviewRows(task).filter((row) => row.initialStatus === 'NEEDS_REVIEW' && row.finalStatus === null).length
}
