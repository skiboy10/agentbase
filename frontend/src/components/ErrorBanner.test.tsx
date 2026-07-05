/**
 * Tests for ErrorBanner component
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@/test/utils'
import userEvent from '@testing-library/user-event'
import { ErrorBanner } from './ErrorBanner'

describe('ErrorBanner', () => {
  it('renders nothing when error is null', () => {
    const onDismiss = vi.fn()
    const { container } = render(<ErrorBanner error={null} onDismiss={onDismiss} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('renders error message when error is provided', () => {
    const onDismiss = vi.fn()
    render(<ErrorBanner error="Something went wrong" onDismiss={onDismiss} />)

    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('renders dismiss button', () => {
    const onDismiss = vi.fn()
    render(<ErrorBanner error="Error message" onDismiss={onDismiss} />)

    expect(screen.getByRole('button', { name: /dismiss/i })).toBeInTheDocument()
  })

  it('calls onDismiss when dismiss button is clicked', async () => {
    const user = userEvent.setup()
    const onDismiss = vi.fn()
    render(<ErrorBanner error="Error message" onDismiss={onDismiss} />)

    await user.click(screen.getByRole('button', { name: /dismiss/i }))

    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('applies error styling', () => {
    const onDismiss = vi.fn()
    render(<ErrorBanner error="Error" onDismiss={onDismiss} />)

    const banner = screen.getByText('Error').closest('div')
    expect(banner).toHaveClass('bg-destructive/20')
    expect(banner).toHaveClass('border-destructive')
  })
})
