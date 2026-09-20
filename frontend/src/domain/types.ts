export type RoleId = 'tester' | 'admin' | 'combined'
export interface SessionContext { actor: string; roles: string[]; role: RoleId }
export type TaskState = 'CREATED' | 'FILES_STAGED' | 'PARSING' | 'PARSED' | 'EVALUATING' | 'READY_FOR_REVIEW' | 'FAILED' | 'COMPLETED'
export type ReviewStatus = 'COMPLIANT' | 'NON_COMPLIANT' | 'NOT_APPLICABLE' | 'NEEDS_REVIEW'
export type FinalStatus = Exclude<ReviewStatus, 'NEEDS_REVIEW'>
export type TemplateStatus = 'DRAFT' | 'PUBLISHED' | 'RETIRED'

export interface EvidenceLocator {
  source_file_id: string
  container: string
  structural_address: string
  bbox: [number, number, number, number] | null
  quoted_text: string | null
  content_hash: string
}

export interface SourceFile {
  id: string
  task_id: string
  role: 'PRIMARY_REPORT' | 'SUPPORTING_EVIDENCE'
  evidence_kinds: string[]
  original_name: string
  detected_format: string
  size_bytes: number
  sha256: string
  source_mtime_ns: number
}

export interface RuleResult {
  id: string
  task_id: string
  rule_id: string
  initial_status: ReviewStatus
  basis_code: string
  basis_text: string
  evidence_locators: EvidenceLocator[]
  missing_materials: string[]
  unresolved_semantics: string[]
  engine_version: string
  baseline_version: string
  active_revision_no: number
  created_at: string
}

export interface ManualDecision {
  id: string
  rule_result_id: string
  final_status: FinalStatus
  reason: string
  supplemental_evidence: EvidenceLocator[]
  actor: string
  decided_at: string
}

export interface ReviewRevision {
  id: string
  task_id: string
  revision_no: number
  completed_at: string
  result_snapshot: string
  snapshot?: ReviewRevisionSnapshot | null
}

export interface ReviewRevisionSnapshot {
  task_id: string
  revision_no: number
  template_id: string | null
  template_name: string
  template_version: string
  template_source_sha256: string
  template_rules?: TemplateRule[]
  results: RuleResult[]
  decisions: ManualDecision[]
}

export interface StageFailure {
  id: string
  task_id: string
  stage: string
  code: string
  message: string
  occurred_at: string
}

export interface TaskExecutionStatus {
  /** True once the execution lease expired, i.e. POST /execute will run again. */
  reclaimable: boolean
  seconds_until_reclaimable: number
}

export interface ReviewTask {
  id: string
  state: TaskState
  active_revision_no: number
  display_name: string
  template_id: string | null
  template_name: string
  template_version: string
  template_rule_count: number
  template_rules?: TemplateRule[]
  /** Server-derived; null unless the task sits in an interrupted state. */
  execution: TaskExecutionStatus | null
  created_at: string
  updated_at: string
  source_files: SourceFile[]
  stage_failures: StageFailure[]
  rule_results: RuleResult[]
  manual_decisions: ManualDecision[]
  revisions: ReviewRevision[]
}

export interface TemplateFinding {
  code: string
  severity: 'ERROR' | 'WARNING'
  message: string
  structural_address: string | null
}

export interface TemplateSummary {
  id: string
  name: string
  version: string
  status: TemplateStatus
  source_filename: string
  source_sha256: string
  source_size_bytes: number
  source_mtime_ns: number
  source_rows: number
  effective_rules: number
  validation_findings: TemplateFinding[]
  created_by: string
  created_at: string
  updated_at: string
  published_at: string | null
}

export interface TemplateRule {
  id: string
  template_id: string
  rule_id: string
  source_row: number | null
  source_sequence: number
  summary: string
  verifiable_requirement: string
  required_materials: string
  main_judgment: 'RULE' | 'RULE_PLUS_AI' | 'AI' | 'MANUAL' | 'DISABLED'
  confirmed_boundary: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface TemplateDetail {
  template: TemplateSummary
  rules: TemplateRule[]
}

export type TemplateAuditAction =
  | 'TEMPLATE_UPLOADED'
  | 'RULE_CREATED'
  | 'RULE_UPDATED'
  | 'RULE_DELETED'
  | 'TEMPLATE_PUBLISHED'
  | 'TEMPLATE_RETIRED'

export type AuditSnapshot = Record<string, string | number | boolean | null>

export interface TemplateAuditEvent {
  id: string
  template_id: string
  template_version: string
  action: TemplateAuditAction
  rule_id: string | null
  actor: string
  occurred_at: string
  before: AuditSnapshot | null
  after: AuditSnapshot | null
}

export interface SupportingUpload {
  file: File
  evidenceKinds: string[]
}

export interface ReviewRow {
  ruleId: string
  result: RuleResult
  decision: ManualDecision | null
  initialStatus: ReviewStatus
  finalStatus: FinalStatus | null
  displayStatus: ReviewStatus
  rule: TemplateRule | null
}
