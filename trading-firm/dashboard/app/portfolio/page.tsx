'use client'

import { usePortfolio, api, type PortfolioMetrics } from '../../lib/api'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts'
import { useEffect, useState } from 'react'

export default function PortfolioPage() {
  const { data: portfolio } = usePortfolio(5000)
  const [metrics, setMetrics] = useState<PortfolioMetrics | null>(null)
  const [history, setHistory] = useState<{ equity_history: number[]; closed_positions: any[] }>({
    equity_history: [],
    closed_positions: [],
  })

  useEffect(() => {
    api.getPortfolioMetrics().then(setMetrics).catch(console.error)
    api.getPortfolioHistory(200).then(setHistory).catch(console.error)
  }, [])

  const equityChartData = history.equity_history.map((eq, i) => ({ i, equity: eq }))

  const closedByCategory: Record<string, number> = {}
  for (const pos of history.closed_positions) {
    const cat = (pos as any).category || 'Other'
    closedByCategory[cat] = (closedByCategory[cat] ?? 0) + ((pos as any).pnl ?? 0)
  }
  const categoryData = Object.entries(closedByCategory).map(([name, pnl]) => ({
    name,
    pnl,
  }))

  return (
    <div className="space-y-6">
      <h1 className="font-syne font-bold text-2xl text-[#00e5cc]">Performance</h1>

      {/* Metrics row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total P&L', value: metrics ? `$${metrics.total_pnl.toFixed(2)}` : '...' },
          { label: 'Win Rate', value: metrics ? `${(metrics.win_rate * 100).toFixed(1)}%` : '...' },
          { label: 'Sharpe', value: metrics ? metrics.sharpe_ratio.toFixed(2) : '...' },
          { label: 'Max Drawdown', value: metrics ? `${(metrics.max_drawdown * 100).toFixed(1)}%` : '...' },
        ].map(({ label, value }) => (
          <div key={label} className="card">
            <div className="text-xs text-[#c8d8e888] mb-1">{label}</div>
            <div className="text-xl font-bold text-[#00e5cc]">{value}</div>
          </div>
        ))}
      </div>

      {/* Equity curve */}
      <div className="card">
        <div className="font-syne font-semibold text-[#00e5cc] mb-4">Equity Curve</div>
        {equityChartData.length > 1 ? (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={equityChartData}>
              <defs>
                <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00e5cc" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#00e5cc" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="i" hide />
              <YAxis domain={['auto', 'auto']} tick={{ fill: '#c8d8e866', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#0a0f14', border: '1px solid #00e5cc22', borderRadius: 6 }}
                labelFormatter={() => ''}
                formatter={(v: number) => [`$${v.toFixed(2)}`, 'Equity']}
              />
              <Area
                type="monotone"
                dataKey="equity"
                stroke="#00e5cc"
                strokeWidth={2}
                fill="url(#equityGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="text-[#c8d8e844] text-sm h-24 flex items-center justify-center">
            No equity history yet
          </div>
        )}
      </div>

      {/* Category P&L */}
      {categoryData.length > 0 && (
        <div className="card">
          <div className="font-syne font-semibold text-[#00e5cc] mb-4">Category P&L</div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={categoryData}>
              <XAxis dataKey="name" tick={{ fill: '#c8d8e866', fontSize: 11 }} />
              <YAxis tick={{ fill: '#c8d8e866', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#0a0f14', border: '1px solid #00e5cc22', borderRadius: 6 }}
                formatter={(v: number) => [`$${v.toFixed(2)}`, 'P&L']}
              />
              <Bar
                dataKey="pnl"
                fill="#00e5cc"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Trade log */}
      <div className="card">
        <div className="font-syne font-semibold text-[#00e5cc] mb-4">Trade Log</div>
        {history.closed_positions.length === 0 ? (
          <div className="text-[#c8d8e844] text-sm">No closed positions yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[#c8d8e866] border-b border-[#ffffff11]">
                  <th className="text-left py-2 pr-3">Market</th>
                  <th className="text-left py-2 pr-3">Side</th>
                  <th className="text-right py-2 pr-3">Entry</th>
                  <th className="text-right py-2 pr-3">Exit</th>
                  <th className="text-right py-2">P&L</th>
                </tr>
              </thead>
              <tbody>
                {history.closed_positions.slice(-50).reverse().map((pos: any, i) => (
                  <tr key={i} className="border-b border-[#ffffff08]">
                    <td className="py-2 pr-3 max-w-[200px] truncate">{pos.question?.slice(0, 35)}...</td>
                    <td className="py-2 pr-3">
                      <span style={{ color: pos.outcome === 'YES' ? '#00e5cc' : '#ff6b35' }}>
                        {pos.outcome}
                      </span>
                    </td>
                    <td className="py-2 pr-3 text-right">{pos.entry_price?.toFixed(3)}</td>
                    <td className="py-2 pr-3 text-right">{pos.exit_price?.toFixed(3) ?? '-'}</td>
                    <td
                      className="py-2 text-right font-bold"
                      style={{ color: pos.pnl >= 0 ? '#00e5cc' : '#ff3355' }}
                    >
                      {pos.pnl >= 0 ? '+' : ''}{pos.pnl?.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
