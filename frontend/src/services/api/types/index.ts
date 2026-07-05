/**
 * Type barrel export - re-exports all types for convenient importing
 */

// Common types
export type {
  Provider,
  ModelAssignment,
  EmbeddingModel,
  EmbeddingConfig,
  HealthStatus,
} from './common';

// Source types
export type {
  AgentInfo,
  Source,
  SourceCreate,
  SourceUpdate,
  SourceAssignment,
  RefreshSourceRequest,
  RefreshResponse,
  IndexingStatus,
  IndexingLog,
  IndexingLogsResponse,
  RetryResponse,
  AdoptCollectionRequest,
  QdrantCollectionInfo,
  CollectionsResponse,
  SiteTreeNode,
  ScanUrlResponse,
  WatcherEvent,
  WatcherStatus,
} from './sources';

// Agent types
export type {
  Agent,
  AgentCreate,
  AgentUpdate,
  AgentDuplicate,
  SkillConfig,
  AgentQueryRequest,
  AgentQueryResponse,
  AgentQuerySourceItem,
  AgentLibrarySummary,
  AgentLibraryBindResponse,
  AgentLibraryUnbindResponse,
} from './agents';

// Prompt types
export type {
  Prompt,
  PromptCreate,
  PromptUpdate,
  PromptDuplicate,
  GeneratePromptRequest,
  GeneratePromptResponse,
} from './prompts';

// Auth types
export type {
  APIKey,
  APIKeyCreate,
  APIKeyCreateResponse,
} from './auth';

// Taxonomy types
export type {
  Taxonomy,
  TaxonomyCreate,
  TaxonomyUpdate,
  TaxonomyTerm,
  TaxonomyTermCreate,
  TaxonomyTermUpdate,
  TaxonomySuggestion,
  TaxonomyCoverage,
  StaleDocSummary,
  MergeRequest,
} from './taxonomy';

// Library types
export type {
  Library,
  LibraryCreate,
  LibraryUpdate,
  LibraryDocument,
  LibraryDocumentPage,
  LibraryDocumentListParams,
  LibrarySource,
  LibrarySearchResult,
  LibrarySearchParams,
  DeepSearchParams,
  DeepSearchResponse,
  LibraryChatMessage,
  LibraryChatConfig,
  LibraryChatSourceItem,
  LibraryChatRequest,
  LibraryChatResponse,
} from './library';

// Evaluation types
export type {
  QuestionStatus,
  QuestionOrigin,
  QuestionSet,
  Question,
  QuestionSetDetail,
  QuestionSetCreate,
  QuestionCreate,
  QuestionUpdate,
  GenerateQuestionsRequest,
  GenerateQuestionsResponse,
  Experiment,
  ExperimentCreate,
  ExperimentOverrides,
  ExperimentStatus,
  ExperimentType,
  CompareStartResponse,
  ComparisonReport,
  ComparisonQuestion,
  ComparisonQuestionVerdict,
} from './evaluation';

// Job queue types
export type {
  Job,
  JobStatus,
} from './jobs';

// Test Studio types
export type {
  TestSuite,
  TestSuiteCreate,
  TestSuiteUpdate,
  TestCase,
  TestCaseCreate,
  TestCaseUpdate,
  TestRun,
  TestCaseResult,
  TestStreamCallbacks,
} from './tests';
