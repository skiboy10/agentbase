import type { LibraryChatMessage, LibraryChatConfig, LibraryChatSourceItem } from '../../../services/api/types/library'

export type { LibraryChatMessage, LibraryChatConfig, LibraryChatSourceItem }

export interface ChatDisplayMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: LibraryChatSourceItem[]
  model?: string
}
