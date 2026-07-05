/**
 * API Client for Agentbase Backend
 *
 * This is the main entry point that re-exports all API namespaces and types
 * for backward compatibility. All existing imports from '../services/api' will
 * continue to work unchanged.
 *
 * Structure:
 * - api/base.ts - Shared utilities (apiFetch, createSSEStream)
 * - api/types/ - Type definitions organized by domain
 * - api/*.ts - API namespace implementations
 */

// Re-export API namespaces
export { providersApi } from './providers';
export { sourcesApi } from './sources';
export { promptsApi, promptGeneratorApi } from './prompts';
export { agentsApi } from './agents';
export { configApi, healthApi } from './config';
export { authApi } from './auth';
export { taxonomyApi } from './taxonomy';
export { libraryApi } from './library';
export { evaluationApi } from './evaluation';
export { jobsApi } from './jobs';
export { testsApi } from './tests';

// Re-export all types for backward compatibility
export type {
  // Common types
  Provider,
  ModelAssignment,
  EmbeddingModel,
  EmbeddingConfig,
  HealthStatus,
  // Source types
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
  // Agent types
  Agent,
  AgentCreate,
  AgentUpdate,
  AgentDuplicate,
  SkillConfig,
  AgentLibrarySummary,
  AgentLibraryBindResponse,
  AgentLibraryUnbindResponse,
  // Prompt types
  Prompt,
  PromptCreate,
  PromptUpdate,
  PromptDuplicate,
  GeneratePromptRequest,
  GeneratePromptResponse,
  // Auth types
  APIKey,
  APIKeyCreate,
  APIKeyCreateResponse,
  // Taxonomy types
  Taxonomy,
  TaxonomyCreate,
  TaxonomyUpdate,
  TaxonomyTerm,
  TaxonomySuggestion,
  TaxonomyCoverage,
  // Agent query types
  AgentQueryRequest,
  AgentQueryResponse,
  AgentQuerySourceItem,
  // Library types
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
  // Evaluation types
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
  // Test Studio types
  TestSuite,
  TestSuiteCreate,
  TestSuiteUpdate,
  TestCase,
  TestCaseCreate,
  TestCaseUpdate,
  TestRun,
  TestCaseResult,
  TestStreamCallbacks,
} from './types';
