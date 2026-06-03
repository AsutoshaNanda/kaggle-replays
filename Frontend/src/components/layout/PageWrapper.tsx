// Authenticated page shell: Navbar on top, Sidebar + scrollable content below.

import type { JSX, ReactNode } from 'react'
import { Navbar } from './Navbar'
import { Sidebar } from './Sidebar'

export function PageWrapper({ children }: { children: ReactNode }): JSX.Element {
  return (
    <div className="mesh-bg" style={{ minHeight: '100vh' }}>
      <Navbar />
      <div className="flex" style={{ paddingTop: 56 }}>
        <Sidebar />
        <main className="flex-1 px-4 py-6 md:px-8 md:py-8" style={{ minWidth: 0 }}>
          <div className="mx-auto w-full" style={{ maxWidth: 1280 }}>
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}
