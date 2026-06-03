// App entry point.
import React from 'react'
import ReactDOM from 'react-dom/client'
import '@/styles/global.css'
import { App } from '@/App'
import { applyTheme, getStoredTheme } from '@/components/shared/ThemeToggle'

// Apply the saved theme before first paint to avoid a flash of the wrong theme.
applyTheme(getStoredTheme())

const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('Root element #root not found')
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
