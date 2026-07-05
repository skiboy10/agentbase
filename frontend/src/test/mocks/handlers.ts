/**
 * MSW request handlers for API mocking
 * These handlers intercept API calls and return mock data
 */
import { http, HttpResponse, delay } from 'msw'
import { mockSources, mockProviders, mockPrompts } from './data'

export const handlers = [
  // =============
  // Health Check
  // =============
  http.get('/health', () => {
    return HttpResponse.json({ status: 'healthy', version: '1.0.0', providers: {} })
  }),

  // =============
  // Sources API
  // =============
  http.get('/api/sources', async ({ request }) => {
    await delay(50)
    const url = new URL(request.url)
    const projectId = url.searchParams.get('project_id')

    let sources = mockSources
    if (projectId) {
      sources = sources.filter(s => s.project_id === projectId)
    }
    return HttpResponse.json(sources)
  }),

  http.get('/api/sources/:id', async ({ params }) => {
    await delay(50)
    const source = mockSources.find(s => s.id === params.id)
    if (!source) {
      return new HttpResponse(null, { status: 404 })
    }
    return HttpResponse.json(source)
  }),

  http.post('/api/sources', async ({ request }) => {
    await delay(50)
    const body = await request.json() as Record<string, unknown>
    const newSource = {
      id: `source-${Date.now()}`,
      ...body,
      status: 'pending',
      document_count: 0,
      chunk_count: 0,
      progress: 0,
      progress_total: 0,
      progress_message: null,
      progress_updated_at: null,
      error_message: null,
      collection_name: null,
      embedding_provider: null,
      embedding_model: null,
      embedding_dimensions: null,
      assigned_projects: [],
      owner_project: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    return HttpResponse.json(newSource, { status: 201 })
  }),

  http.post('/api/sources/:id/index', async ({ params }) => {
    await delay(100)
    return HttpResponse.json({
      source_id: params.id,
      status: 'indexing',
      message: 'Indexing started',
    })
  }),

  http.post('/api/sources/search', async ({ request }) => {
    await delay(50)
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json([
      {
        content: `Mock search result for: ${body.query}`,
        source: 'https://example.com/docs',
        score: 0.95,
        metadata: {},
      },
    ])
  }),

  // =============
  // Providers API
  // =============
  http.get('/api/providers', async () => {
    await delay(50)
    return HttpResponse.json(mockProviders)
  }),

  http.get('/api/providers/:name/models', async ({ params }) => {
    await delay(50)
    const models: Record<string, string[]> = {
      ollama: ['llama3.2', 'mistral', 'codellama'],
      openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo'],
      anthropic: ['claude-3-opus', 'claude-3-sonnet', 'claude-3-haiku'],
    }
    return HttpResponse.json(models[params.name as string] || [])
  }),

  http.post('/api/providers/:name/test', async () => {
    await delay(100)
    return HttpResponse.json({ status: 'success', healthy: true, message: 'Connection successful' })
  }),

  // =============
  // Prompts API
  // =============
  http.get('/api/prompts/prompts', async ({ request }) => {
    await delay(50)
    const url = new URL(request.url)
    const projectId = url.searchParams.get('project_id')

    let prompts = mockPrompts
    if (projectId) {
      prompts = prompts.filter(p => p.project_id === projectId || p.project_id === null)
    }
    return HttpResponse.json(prompts)
  }),

  http.get('/api/prompts/prompts/default/:taskType', async ({ params }) => {
    await delay(50)
    const taskType = params.taskType as string
    const prompt = mockPrompts.find(p => p.task_type === taskType && p.is_default)
    return HttpResponse.json(prompt || mockPrompts[0])
  }),

  http.post('/api/prompts/prompts', async ({ request }) => {
    await delay(50)
    const body = await request.json() as Record<string, unknown>
    const newPrompt = {
      id: `prompt-${Date.now()}`,
      ...body,
      version: 1,
      use_rag: body.use_rag ?? false,
      description: body.description || null,
      rag_context_template: body.rag_context_template || null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    return HttpResponse.json(newPrompt, { status: 201 })
  }),
]
