/**
 * MSW server for Node.js testing environment
 */
import { setupServer } from 'msw/node'
import { handlers } from './handlers'

// Set up requests interception using the given handlers
export const server = setupServer(...handlers)
