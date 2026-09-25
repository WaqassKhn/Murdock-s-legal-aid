export interface Capabilities {
  max_upload_mb: number;
  ocr_available: boolean;
  request_processing: boolean;
}
export interface User {
  id: string;
  email: string;
}
export interface Workspace {
  id: string;
  name: string;
  objective: string;
  jurisdiction: string;
  created_at: string;
  document_count: number;
  is_demo: boolean;
}
export type Status =
  'uploaded' | 'extracting' | 'indexing' | 'analyzing' | 'ready' | 'partially_processed' | 'failed';
export interface DocumentRecord {
  id: string;
  workspace_id: string;
  name: string;
  status: Status;
  media_type: string;
  page_count: number;
  warnings: string[];
  created_at: string;
  version: number;
  job_id: string;
  processing_required?: boolean;
}
export interface Page {
  number: number;
  text: string;
  quality: number;
  ocr: boolean;
  warning?: string;
  blocks: { text: string; bbox?: number[] }[];
}
export interface Citation {
  document_id: string;
  page: number;
  section: string;
  excerpt: string;
  confidence: number;
  bbox?: number[];
}
export interface EvidenceField {
  value: string;
  citations: Citation[];
  confidence: number;
}
export type Attention =
  'Low attention' | 'Review recommended' | 'High attention' | 'Insufficient information';
export interface Clause {
  id: string;
  clause_type: string;
  original: string;
  explanation: string;
  affected_parties: string[];
  rights: string[];
  obligations: string[];
  deadlines: string[];
  financial_exposure: string[];
  defined_terms?: { term: string; definition: string; citations: Citation[] }[];
  attention: Attention;
  ambiguities: string[];
  risk_reason?: string;
  lawyer_question?: string;
  citations: Citation[];
  confidence: number;
}
export interface Obligation {
  id: string;
  document_id: string;
  responsible_party: string;
  action: string;
  trigger: string;
  time_window: string;
  recurrence: string;
  consequence: string;
  status: 'open' | 'complete';
  citations: Citation[];
  confidence: number;
  user_action?: string;
  user_notes?: string;
  document_name?: string;
}
export interface ActionQuestion {
  id: string;
  question: string;
  reason: string;
  document_id: string;
  citations: Citation[];
}
export interface TimelineEvent {
  id: string;
  document_id: string;
  document_name: string;
  title: string;
  expression: string;
  trigger: string;
  calendar_date: string | null;
  kind: 'dated' | 'relative' | 'unclear';
  explanation: string;
  status: 'open' | 'complete';
  citations: Citation[];
}
export interface ActionPlan {
  workspace_id: string;
  workspace_name: string;
  objective: string;
  responsibilities: Obligation[];
  timeline: TimelineEvent[];
  open_questions: ActionQuestion[];
  lawyer_questions: ActionQuestion[];
  negotiation_prompts: ActionQuestion[];
  risks: (Risk & { document_id: string; document_name: string })[];
  preparation_evidence: Citation[];
  disclaimer: string;
}
export interface Risk {
  id: string;
  finding: string;
  why_it_matters: string;
  severity: Attention;
  affected_party: string;
  confidence: number;
  suggested_clarification: string;
  lawyer_question: string;
  citations: Citation[];
}
export interface Analysis {
  metadata: Record<string, EvidenceField>;
  summary: string;
  summary_citations?: Citation[];
  meaning: string;
  meaning_citations?: Citation[];
  clauses: Clause[];
  obligations: Obligation[];
  risks: Risk[];
  mode: string;
}
export interface DocumentDetail extends DocumentRecord {
  pages: Page[];
  analysis: Analysis | null;
}
export interface Answer {
  direct_answer: string;
  explanation: string;
  citations: Citation[];
  excerpts: string[];
  missing_information: string[];
  confidence: number;
  follow_up_questions: string[];
  category: string;
  abstained: boolean;
  mode: string;
  answer_type?: 'explicit' | 'interpreted' | 'not_found';
  confidence_label?: 'high' | 'medium' | 'low';
  verification_step?: string;
  relevant_clauses?: Citation[];
}
export interface ComparisonFinding {
  id: string;
  clause_type: string;
  change_type: string;
  before: string;
  after: string;
  explanation: string;
  attention_before: Attention;
  attention_after: Attention;
  citations: Citation[];
  warning?: string;
}
export interface Comparison {
  id: string;
  left_id: string;
  right_id: string;
  findings: ComparisonFinding[];
  mode: string;
}
export interface Report {
  id: string;
  title: string;
  created_at: string;
  format: string;
}
export type View =
  'Workspaces' | 'Documents' | 'Analysis' | 'Compare' | 'Obligations' | 'Ask' | 'Reports';
