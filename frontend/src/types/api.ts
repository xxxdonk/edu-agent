export type Difficulty = 'beginner' | 'intermediate' | 'advanced';
export type ResourceType = 'explanation' | 'mind_map' | 'quiz' | 'reading' | 'coding';
export type ReviewStatus = 'pending' | 'approved' | 'rejected' | 'needs_revision';
export type TaskStatus = 'pending' | 'running' | 'completed' | 'partial_success' | 'failed';
export type AgentRunStatus = 'pending' | 'started' | 'completed' | 'failed' | 'skipped';
export type EvidenceSource = 'conversation' | 'evaluation' | 'inference' | 'system_default';

export interface FieldEvidence {
  source: EvidenceSource;
  quote: string;
  message_id: string | null;
}

export interface ProfileField<T> {
  value: T;
  evidence: FieldEvidence[];
  confidence: number;
}

export interface TimeBudget {
  minutes_per_day: number;
  days_per_week: number;
}

export interface StudentProfile {
  student_id: string;
  version: number;
  major: ProfileField<string | null>;
  course: ProfileField<string | null>;
  knowledge_level: ProfileField<Difficulty | null>;
  learning_goals: ProfileField<string[]>;
  weak_topics: ProfileField<string[]>;
  learning_history: ProfileField<string[]>;
  cognitive_style: ProfileField<string | null>;
  language_preference: ProfileField<string | null>;
  resource_preference: ProfileField<string[]>;
  time_budget: ProfileField<TimeBudget | null>;
  evidence: FieldEvidence[];
  confidence: number;
  updated_at: string;
}

export interface ChatMessage {
  message_id: string;
  role: 'user' | 'assistant';
  content: string;
}

export interface ProfileChatRequest {
  student_id: string;
  conversation_id: string | null;
  messages: ChatMessage[];
  evaluation_summary: string | null;
}

export interface ProfileChatResponse {
  profile: StudentProfile;
  missing_dimensions: string[];
  next_question: string | null;
  is_complete: boolean;
  extraction_mode: 'development_heuristic' | 'llm_structured';
}

export interface LearningPathStep {
  step: number;
  topic: string;
  learning_goal: string;
  reason: string;
  recommended_resources: ResourceType[];
  completion_criteria: string[];
  estimated_minutes: number;
  prerequisites: string[];
}

export interface LearningPath {
  path_id: string;
  student_id: string;
  profile_version: number;
  course: string;
  status: 'active' | 'superseded' | 'completed';
  steps: LearningPathStep[];
  adjustment_reason: string | null;
  generation_mode: 'development_rule_based' | 'llm_structured';
  created_at: string;
}

export interface PathGenerateRequest {
  student_id: string;
  profile: StudentProfile | null;
  previous_path_id: string | null;
  evaluation_summary: string | null;
}

export interface SourceReference {
  source_id: string;
  title: string;
  locator: string;
  chunk_id: string | null;
}

export interface Resource {
  resource_id: string;
  resource_type: ResourceType;
  title: string;
  content: string;
  content_format: 'markdown' | 'mermaid' | 'json' | 'python' | 'text';
  target_topic: string;
  difficulty: Difficulty;
  personalization_reason: string;
  source_references: SourceReference[];
  review_status: ReviewStatus;
  created_at: string;
}

export interface ResourceGenerationRequest {
  student_id: string;
  path_id: string;
  step: number;
  resource_types: ResourceType[];
  regenerate: boolean;
}

export interface TaskAcceptedResponse {
  task_id: string;
  status: TaskStatus;
  status_url: string;
  events_url: string;
}

export interface AgentRun {
  agent: string;
  resource_type: ResourceType | null;
  status: AgentRunStatus;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
}

export interface TaskState {
  task_id: string;
  task_type: 'resource_generation' | 'evaluation';
  student_id: string;
  status: TaskStatus;
  progress: number;
  current_stage: string;
  requested_resource_types: ResourceType[];
  result_resource_ids: string[];
  agent_runs: AgentRun[];
  errors: string[];
  created_at: string;
  updated_at: string;
}

export interface TaskEvent {
  event_id: string;
  task_id: string;
  sequence: number;
  event_type: 'task' | 'agent' | 'review' | 'heartbeat';
  status: string;
  progress: number;
  message: string;
  agent: string | null;
  resource_type: ResourceType | null;
  error: string | null;
  created_at: string;
}

export interface EvaluationAnswer {
  question_id: string;
  response: string;
}

export interface EvaluationSubmission {
  student_id: string;
  path_id: string;
  step: number;
  answers: EvaluationAnswer[];
  time_spent_minutes: number;
}

export interface EvaluationResult {
  evaluation_id: string;
  student_id: string;
  path_id: string;
  step: number;
  mastery_score: number;
  passed: boolean;
  weak_topics: string[];
  feedback: string;
  profile_update_required: boolean;
  path_update_required: boolean;
  evaluated_at: string;
}

export interface ApiErrorBody {
  error: {code: string; message: string; details: Record<string, unknown>};
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  environment: string;
  database: string;
}

export interface QuizQuestion {
  id: string;
  type: 'single_choice' | 'short_answer' | 'comprehensive' | string;
  level: string;
  question: string;
  options?: string[];
  answer: string;
  explanation: string;
}

export interface QuizDocument {
  topic: string;
  difficulty: Difficulty;
  questions: QuizQuestion[];
}

export type ViewStatus = 'idle' | 'loading' | 'success' | 'empty' | 'partial' | 'error';
export type UiAgentStatus = 'waiting' | 'running' | 'completed' | 'failed';

export interface UiAgentTrace {
  key: string;
  name: string;
  label: string;
  status: UiAgentStatus;
  message: string;
  progress: number;
  error?: string;
}

export interface ApiIssue {
  endpoint: string;
  request: unknown;
  expected: string;
  actual: string;
  browserError: string;
  reproduction: string[];
  createdAt: string;
}
