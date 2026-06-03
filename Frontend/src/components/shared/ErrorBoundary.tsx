// Class-based error boundary. Shows a sanitized message and a reload button.

import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertIcon } from '@/components/shared/icons'

interface ErrorBoundaryProps {
  children: ReactNode
}
interface ErrorBoundaryState {
  hasError: boolean
  message: string
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, message: '' }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, message: error.message }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error('Caught by ErrorBoundary:', error, info.componentStack)
  }

  private handleReload = (): void => {
    window.location.reload()
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div
          className="mesh-bg flex items-center justify-center p-4"
          style={{ minHeight: '100vh' }}
        >
          <div
            className="glass-card text-center"
            style={{ padding: 40, maxWidth: 480, width: '100%' }}
          >
            <div className="mb-3 flex justify-center" style={{ color: 'var(--accent-red)' }}>
              <AlertIcon size={40} />
            </div>
            <h2 className="mb-2" style={{ fontSize: '1.25rem' }}>
              Something went wrong
            </h2>
            <p
              className="mb-6"
              style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}
            >
              {this.state.message || 'Unexpected error.'}
            </p>
            <button className="btn-primary-glow" onClick={this.handleReload}>
              Reload Page
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
