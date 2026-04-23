import type { Metadata } from 'next'
import { IBM_Plex_Mono, Syne } from 'next/font/google'
import './globals.css'

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-mono',
})

const syne = Syne({
  subsets: ['latin'],
  weight: ['400', '600', '700', '800'],
  variable: '--font-syne',
})

export const metadata: Metadata = {
  title: 'Polymarket Trading Firm',
  description: 'Autonomous AI Trading Firm Dashboard',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className={`${ibmPlexMono.variable} ${syne.variable}`}>
      <body className="bg-[#080c10] text-[#c8d8e8] font-mono min-h-screen">
        {/* Scanline overlay */}
        <div
          className="fixed inset-0 pointer-events-none z-50"
          style={{
            backgroundImage:
              'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px)',
          }}
        />
        {/* Top navigation */}
        <nav className="fixed top-0 left-0 right-0 z-40 bg-[#0a0f14] border-b border-[#00e5cc22] px-6 py-3">
          <div className="flex items-center justify-between max-w-7xl mx-auto">
            <div className="flex items-center gap-6">
              <span className="font-syne font-bold text-[#00e5cc] text-lg tracking-wider">
                ◈ TRADING FIRM
              </span>
              <div className="flex gap-4 text-sm">
                {[
                  { href: '/', label: 'Dashboard' },
                  { href: '/agents', label: 'Agents' },
                  { href: '/portfolio', label: 'Portfolio' },
                  { href: '/settings', label: 'Settings' },
                ].map(({ href, label }) => (
                  <a
                    key={href}
                    href={href}
                    className="text-[#c8d8e8] hover:text-[#00e5cc] transition-colors"
                  >
                    {label}
                  </a>
                ))}
              </div>
            </div>
            <div className="text-xs text-[#c8d8e866]">
              {new Date().toLocaleDateString()} | PAPER MODE
            </div>
          </div>
        </nav>
        <main className="pt-16 max-w-7xl mx-auto px-6 py-6">{children}</main>
      </body>
    </html>
  )
}
