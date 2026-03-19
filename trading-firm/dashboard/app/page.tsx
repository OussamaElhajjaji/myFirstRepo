'use client'

import { usePortfolio, useLiveEvents, useAgents, type BusEvent } from '../lib/api'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { useEffect, useState } from 'react'

function StatCard({
  label,
  value,
  color = '#00e5cc',
}: {
  label: string
  value: string
  color?: string
}) {
  return (
    <div className="card flex flex-col gap-1">
      <div className="text-xs text-[#c8d8e888] uppercase tracking-widest">{label}</div>
      <div className="text-2xl font-bold" style={{ color }}>
        {value}
      </div>
    </div>
  )
}

function EventFeed({ events }: { events: BusEvent[] }) {
  const topicColors: Record<string, string> = {
    'trade.executed': '#00e5cc',
    'agent.opinion': '#c8d8e8',
    'consensus.reached': '#ff6b35',
    'alert.risk': '#ff3355',
    'cycle.complete': '#888',
    'position.closed': '#00e5cc',
  }

  return (
    <div className="card h-96 overflow-y-auto">
      <div className="font-syne font-semibold text-[#00e5cc] mb-3 text-sm uppercase tracking-widest">
        Live Agent Feed
      </div>
      {events.length === 0 && (
        <div className="text-[#c8d8e844] text-sm">Waiting for events...</div>
      )}
      {events.map((ev, i) => (
        <div
          key={i}
          className="flex items-start gap-2 py-2 border-b border-[#ffffff08] text-xs"
        >
          <span
            className="shrink-0 uppercase font-bold"
            style={{ color: topicColors[ev.topic] ?? '#888' }}
          >
            [{ev.topic}]
          </span>
          <span className="text-[#c8d8e8cc] break-all">
            {JSON.stringify(ev.payload).slice(0, 120)}
          </span>
        </div>
      ))}
    </div>
  )
}

function PositionsTable({ positions }: { positions: any[] }) {
  return (
    <div className="card overflow-x-auto">
      <div className="font-syne font-semibold text-[#00e5cc] mb-3 text-sm uppercase tracking-widest">
        Open Positions
      </div>
      {positions.length === 0 ? (
        <div className="text-[#c8d8e844] text-sm">No open positions.</div>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-[#c8d8e866] border-b border-[#ffffff11]">
              <th className="text-left py-2 pr-4">Market</th>
              <th className="text-left py-2 pr-4">Side</th>
              <th className="text-right py-2 pr-4">Entry</th>
              <th className="text-right py-2 pr-4">Size</th>
              <th className="text-right py-2">Opened</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos) => (
              <tr
                key={pos.market_id}
                className="border-b border-[#ffffff08] hover:bg-[#00e5cc08]"
              >
                <td className="py-2 pr-4 max-w-[200px] truncate" title={pos.question}>
                  {pos.question.slice(0, 40)}...
                </td>
                <td className="py-2 pr-4">
                  <span
                    className="font-bold"
                    style={{
                      color: pos.outcome === 'YES' ? '#00e5cc' : '#ff6b35',
                    }}
                  >
                    {pos.outcome}
                  </span>
                </td>
                <td className="py-2 pr-4 text-right">{pos.entry_price.toFixed(3)}</td>
                <td className="py-2 pr-4 text-right">${pos.size_usd.toFixed(2)}</td>
                <td className="py-2 text-right text-[#c8d8e866]">
                  {new Date(pos.opened_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default function DashboardPage() {
  const { data: portfolio } = usePortfolio(3000)
  const events = useLiveEvents()
  const { agents } = useAgents()

  const pnlColor =
    !portfolio || portfolio.total_pnl >= 0 ? '#00e5cc' : '#ff3355'

  const equityData =
    portfolio?.open_positions.map((_, i) => ({
      i,
      equity: portfolio.equity,
    })) ?? []

  return (
    <div>
      {/* Status bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          label="Equity"
          value={portfolio ? `$${portfolio.equity.toLocaleString('en', { minimumFractionDigits: 2 })}` : '...'}
          color={pnlColor}
        />
        <StatCard
          label="Today P&L"
          value={portfolio ? `${portfolio.daily_pnl >= 0 ? '+' : ''}$${portfolio.daily_pnl.toFixed(2)}` : '...'}
          color={portfolio && portfolio.daily_pnl >= 0 ? '#00e5cc' : '#ff3355'}
        />
        <StatCard
          label="Open Positions"
          value={portfolio ? String(portfolio.open_positions.length) : '...'}
        />
        <StatCard
          label="Win Rate"
          value={portfolio ? `${(portfolio.win_rate * 100).toFixed(1)}%` : '...'}
        />
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="flex flex-col gap-6">
          <EventFeed events={events.slice(0, 50)} />
          {/* Agent status strip */}
          <div className="card">
            <div className="font-syne font-semibold text-[#00e5cc] mb-3 text-sm uppercase tracking-widest">
              Agent Status
            </div>
            <div className="grid grid-cols-3 gap-2">
              {agents.map((a) => (
                <div
                  key={a.agent_id}
                  className="flex items-center gap-2 text-xs"
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{
                      background: a.paused ? '#ff3355' : '#00e5cc',
                    }}
                  />
                  <span className="truncate">{a.agent_id}</span>
                  <span className="text-[#c8d8e866] shrink-0">
                    {(a.accuracy * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="flex flex-col gap-6">
          <PositionsTable positions={portfolio?.open_positions ?? []} />
          {/* Mini stats */}
          <div className="card">
            <div className="font-syne font-semibold text-[#00e5cc] mb-3 text-sm uppercase tracking-widest">
              Risk Overview
            </div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-[#c8d8e888]">Cash Available</span>
                <span>${portfolio?.cash.toFixed(2) ?? '...'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#c8d8e888]">Total Invested</span>
                <span>${portfolio?.total_invested.toFixed(2) ?? '...'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#c8d8e888]">Sharpe Ratio</span>
                <span>{portfolio?.sharpe_ratio.toFixed(2) ?? '...'}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
