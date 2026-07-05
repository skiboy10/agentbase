export interface HelpEntry {
  label: string
  summary: string
  detail: string
  example?: string
  keyConcept?: string
}

export const help = {
  sources: {
    page: {
      label: 'Sources',
      summary: 'Ingest, index, and manage the documents that power agent knowledge retrieval.',
      detail: 'A source points to a directory of files, a set of URLs, or a GitHub repo. When you index a source, Agentbase extracts text, splits it into chunks, and stores vector embeddings in Qdrant for semantic search.',
      example: 'A folder of PDFs, a website to crawl, a GitHub repository',
      keyConcept: 'Each source gets its own Qdrant collection with independently searchable chunks.',
    },
    emptyState: {
      label: 'No sources yet',
      summary: 'Add your first source to start building knowledge.',
      detail: 'Sources are the raw content that powers your agents. Upload files, point to a URL, or connect a GitHub repo.',
    },
    searchTest: {
      label: 'Search Test',
      summary: 'Test how well your indexed sources answer a query.',
      detail: 'Search Test runs a query directly against raw source chunks in Qdrant. Use it to verify that a source is indexed and returning relevant results before adding it to a library. Unlike Library search, this bypasses curation — it shows exactly what is stored at the source level.',
      keyConcept: 'Library search queries curated collections; Search Test queries raw sources directly.',
    },
    chunks: {
      label: 'Chunks',
      summary: 'The number of text segments indexed from this source and available for retrieval.',
      detail: 'When a source is indexed, its documents are split into smaller passages called chunks. Each chunk is embedded and stored for semantic search. More chunks generally means finer-grained retrieval.',
    },
  },
  libraries: {
    page: {
      label: 'Libraries',
      summary: 'Curated document collections for RAG retrieval.',
      detail: 'A library bundles multiple sources into a single searchable unit. Queries search across all member sources at once. Document and chunk counts roll up to the library level.',
      example: 'A "Product Documentation" library combining engineering docs, support articles, and training materials',
      keyConcept: 'Libraries are what you bind to agents — they define the knowledge an agent can access.',
    },
    emptyState: {
      label: 'No libraries yet',
      summary: 'Create a library to organize your sources for retrieval.',
      detail: 'Libraries group sources into searchable collections. Create one, then add sources to it. Bind libraries to agents to enable RAG.',
    },
    chunks: {
      label: 'Chunks',
      summary: 'The number of text segments stored in this library and available for retrieval.',
      detail: 'When a source is indexed, its documents are split into smaller passages called chunks. Each chunk is embedded and stored for semantic search. More chunks generally means finer-grained retrieval.',
    },
    searchMode: {
      hybrid: {
        label: 'Hybrid search',
        summary: 'Combines meaning-based (semantic) matching with exact keyword matching. Best for most queries.',
        detail: 'Hybrid search runs a semantic vector search and a keyword search in parallel, then merges the results. This catches both conceptual matches and exact term matches, making it the most robust option for general-purpose queries.',
      },
      vector: {
        label: 'Vector search',
        summary: 'Finds results by meaning rather than exact words. Good for conceptual questions.',
        detail: 'Vector search converts your query into a numerical embedding and finds the passages closest in meaning, even if they use different wording. It handles paraphrases and synonyms well but may miss results that hinge on a specific term.',
      },
      deep: {
        label: 'Deep search',
        summary: 'Breaks your question into sub-queries and runs multiple retrieval passes. Slower, but surfaces harder-to-find results.',
        detail: 'Deep search decomposes your question into several narrower sub-queries, runs each one, and merges the retrieved passages. This helps when the answer is spread across multiple documents or when a single query would miss key context.',
      },
    },
    topK: {
      label: 'Documents per search',
      summary: 'How many documents to retrieve per search query (full label: Documents Retrieved Per Search).',
      detail: 'A higher value returns more candidate passages, giving the model more context to draw from. A lower value is faster and more focused. Typical values range from 3 to 20.',
    },
    vectorWeight: {
      label: 'Vector weight',
      summary: 'Controls the balance between semantic and keyword matching in hybrid search.',
      detail: 'At 1.0 the result is purely semantic; at 0.0 it is purely keyword-based. Values around 0.7 work well for most queries. Shift toward 0.0 when exact term matching matters more, toward 1.0 for conceptual questions.',
    },
    reranking: {
      label: 'Reranking',
      summary: 'Re-scores retrieved passages for relevance before returning them.',
      detail: 'After the initial retrieval pass, reranking applies a cross-encoder model to re-score each passage against the query. This improves precision at the cost of a small latency increase.',
    },
  },
  taxonomy: {
    page: {
      label: 'Taxonomy',
      summary: 'Manage controlled vocabularies for classifying and enriching documents.',
      detail: 'Taxonomies define classification systems with hierarchical terms organized into facets. During enrichment, an LLM classifies each document chunk against your taxonomy, adding structured metadata that improves search precision.',
      example: 'Facets like "Products", "Topics", "Platforms" with terms under each',
      keyConcept: 'Enrichment metadata enables filtered retrieval — search within specific categories.',
    },
    emptyState: {
      label: 'No taxonomies yet',
      summary: 'Create a taxonomy to classify and enrich your documents.',
      detail: 'Taxonomies let you define controlled vocabularies. When sources are enriched, documents are automatically classified against your terms.',
    },
    pipelineHealth: {
      label: 'Pipeline Health',
      summary: 'Monitor enrichment coverage, stale documents, and pending classification suggestions for this taxonomy.',
      detail: 'Pipeline Health shows how completely your documents have been classified against this taxonomy, highlights documents enriched with an older version, and surfaces AI-suggested terms awaiting review. Use it to identify gaps and keep enrichment current after taxonomy changes.',
      keyConcept: 'Stale documents were classified against an older taxonomy version — re-enrich to update their metadata.',
    },
    what: {
      label: 'What is a taxonomy?',
      summary: 'A taxonomy is a controlled vocabulary that lets you classify documents with consistent, structured labels.',
      detail: 'Each taxonomy contains terms grouped into facets. When a source is enriched, an LLM reads each chunk and applies matching terms from the taxonomy as metadata, making documents filterable by category.',
    },
    facets: {
      label: 'Facets',
      summary: 'Facets are named categories that group related terms — for example "Platform", "Product", or "Topic".',
      detail: 'Use facets to model the different dimensions you want to filter on. Broad structural facets (Platform, Product) keep classification consistent; thematic facets (Topic, Audience) add context for retrieval. Each term in a taxonomy belongs to exactly one facet.',
    },
    terms: {
      label: 'Terms',
      summary: 'Terms are the specific values within a facet that documents can be classified as.',
      detail: 'Add a term for every distinct value you expect to see in your documents. Terms belong to a facet and carry optional keywords that guide the LLM classifier.',
    },
    keywords: {
      label: 'Keywords',
      summary: 'Keywords are signal words that help the LLM recognise when a chunk belongs to this term.',
      detail: 'Add synonyms, abbreviations, and closely related phrases as keywords. During indexing, the enrichment pipeline uses these to improve classification accuracy — the more precise your keywords, the fewer misclassifications you will see.',
    },
    suggestions: {
      label: 'Suggestions',
      summary: 'Suggestions are new term candidates surfaced by the LLM when it encounters values not already in the taxonomy.',
      detail: 'When enrichment classifies a chunk and the best match falls outside your existing terms, it records a suggestion. Review pending suggestions here: approve to add the term, reject to discard it, or merge it into an existing term if it is a duplicate or synonym.',
    },
    coverage: {
      label: 'Coverage',
      summary: 'Coverage shows what percentage of your documents have been classified by this taxonomy.',
      detail: 'A document counts as covered when at least one of its chunks has been assigned a term from this taxonomy. Low coverage usually means sources have not been enriched yet, or that the taxonomy terms do not match the document vocabulary well. Re-enrich sources after adding new terms to improve coverage.',
    },
    staleDocs: {
      label: 'Stale documents',
      summary: 'Documents classified against an older version of this taxonomy.',
      detail: 'When you add or edit terms, the taxonomy version increments. Documents classified against an earlier version are marked stale. Re-enrich the relevant sources to bring them up to date.',
    },
  },
  agents: {
    page: {
      label: 'Agents',
      summary: 'Define agents with prompts, knowledge, and model settings — accessible via API and MCP.',
      detail: 'An agent combines an LLM model, a system prompt, temperature settings, and library bindings. When queried, it retrieves relevant context from its libraries and generates an informed response.',
      example: 'A "Product Expert" agent bound to documentation and training libraries',
      keyConcept: 'Agents handle RAG automatically — the caller just sends a question.',
    },
    emptyState: {
      label: 'No agents yet',
      summary: 'Create your first agent to start answering questions.',
      detail: 'Agents combine a model, system prompt, and library bindings into a queryable endpoint. Create one and start asking questions.',
    },
  },
  providers: {
    page: {
      label: 'Providers',
      summary: 'Connect LLM providers and configure which models are available.',
      detail: 'Provider connections supply the models that agents use for answering questions and that the pipeline uses for embeddings and enrichment. Configure API keys and base URLs, then enable specific models.',
      example: 'Ollama running locally, OpenAI API key, Anthropic Claude',
      keyConcept: 'Configure providers first — agents and the enrichment pipeline need models to work.',
    },
  },
  settings: {
    page: {
      label: 'Settings',
      summary: 'Platform configuration for embeddings, retrieval, and context management.',
      detail: 'Configure appearance, embedding defaults, and retrieval parameters. Backend settings are controlled via environment variables.',
    },
  },
  apiKeys: {
    page: {
      label: 'API Keys',
      summary: 'Manage platform API keys for programmatic access and MCP connections.',
      detail: 'Create API keys with specific permission scopes (read, write, admin). Keys authenticate access to the REST API and MCP server from external tools and agents.',
    },
    emptyState: {
      label: 'No API keys yet',
      summary: 'Create an API key for programmatic access.',
      detail: 'API keys authenticate requests to the REST API and MCP server. Create one with the appropriate scopes for your use case.',
    },
  },
  quickstart: {
    page: {
      label: 'Quickstart',
      summary: 'Learn how Agentbase works and get started in minutes.',
      detail: 'Agentbase is a knowledge curation platform that gives AI agents deep expertise in specialized domains. Ingest documents, build searchable libraries, and create agents that answer questions with retrieval-augmented generation.',
    },
  },
  apiReference: {
    page: {
      label: 'API Reference',
      summary: 'Full REST API documentation with endpoint details and examples.',
      detail: 'Browse all available API endpoints, request formats, and response schemas. Test endpoints directly from the documentation.',
    },
  },
  experiments: {
    page: {
      label: 'Experiments',
      summary: 'A/B test embedding models and chunking strategies against your sources.',
      detail: 'Compare different configurations to find the best retrieval quality for your domain. Test embedding models, chunk sizes, and overlap settings side by side.',
    },
  },
  workflow: {
    steps: [
      { key: 'providers', label: 'Provider', href: '/providers', description: 'Connect LLM providers' },
      { key: 'sources', label: 'Source', href: '/sources', description: 'Ingest content' },
      { key: 'taxonomy', label: 'Taxonomy', href: '/taxonomy', description: 'Classify documents' },
      { key: 'libraries', label: 'Library', href: '/libraries', description: 'Curate collections' },
      { key: 'agents', label: 'Agent', href: '/agents', description: 'Query with RAG' },
    ],
  },
} as const

export type HelpPath = string

export function getHelp(path: string): HelpEntry | undefined {
  const parts = path.split('.')
  let current: unknown = help
  for (const part of parts) {
    if (current && typeof current === 'object' && part in current) {
      current = (current as Record<string, unknown>)[part]
    } else {
      return undefined
    }
  }
  return current as HelpEntry | undefined
}
