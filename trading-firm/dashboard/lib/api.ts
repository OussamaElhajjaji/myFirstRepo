/**
 * Typed API client for the Trading Firm backend.
 * Includes WebSocket client with auto-reconnect.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const WS_URL = API_URL.replace(/^http/, 'ws')

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Position {
  market_id: string
  question: string
  outcome: 'YES' | 'NO'
  entry_price: number
  size_usd: number
  shares: number
  category: string
  opened_at: string
  agent_memo: string
}

export interface PortfolioState {
  equity: number
  cash: number
  total_invested: number
  total_pnl: number
  daily_pnl: number
  win_rate: number
  sharpe_ratio: number
  open_positions: Position[]
}

export interface PortfolioMetrics {
  total_pnl: number
  win_rate: number
  avg_win: number
  avg_loss: number
  sharpe_ratio: number
  max_drawdown: number
  total_trades: number
}

export interface AgentStatus {
  agent_id: string
  paused: boolean
  accuracy: number
  last_analysis_at: string | null
}

export interface MarketInfo {
  id: string
  question: string
  yes_price: number
  no_price: number
  volume: number
  liquidity: number
  days_to_end: number
  category: string
}

export interface Config {
  paper_trading: boolean
  risk_profile: string
  max_position_usd: number
  max_open_positions: number
  circuit_breaker_pct: number
  loop_interval_sec: number
  min_edge_threshold: number
  min_consensus_score: number
}

export interface BusEvent {
  topic: string
  payload: Record<string, unknown>
  timestamp?: string
}

// ---------------------------------------------------------------------------
// REST client
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => apiFetch<{ status: string; paper_trading: boolean }>('/health'),
  getPortfolio: () => apiFetch<PortfolioState>('/portfolio'),
  getPortfolioHistory: (limit = 100) =>
    apiFetch<{ equity_history: number[]; closed_positions: Position[] }>(
      `/portfolio/history?limit=${limit}`
    ),
  getPortfolioMetrics: () => apiFetch<PortfolioMetrics>('/portfolio/metrics'),
  getAgents: () => apiFetch<{ agents: AgentStatus[] }>('/agents'),
  getAgentMemory: (agentId: string, limit = 20) =>
    apiFetch<{ agent_id: string; memories: { key: string; value: unknown }[] }>(
      `/agents/${agentId}/memory?limit=${limit}`
    ),
  getMarkets: () => apiFetch<{ markets: MarketInfo[] }>('/markets'),
  getConfig: () => apiFetch<Config>('/config'),
  setRiskProfile: (profile: string) =>
    apiFetch<{ profile: string }>('/config/risk-profile', {
      method: 'POST',
      body: JSON.stringify({ profile }),
    }),
  pauseAgent: (agentId: string) =>
    apiFetch<{ agent_id: string; paused: boolean }>(`/agents/${agentId}/pause`, {
      method: 'POST',
    }),
  resumeAgent: (agentId: string) =>
    apiFetch<{ agent_id: string; paused: boolean }>(`/agents/${agentId}/resume`, {
      method: 'POST',
    }),
  pauseTrading: () => apiFetch<{ paused: boolean }>('/trading/pause', { method: 'POST' }),
  resumeTrading: () => apiFetch<{ paused: boolean }>('/trading/resume', { method: 'POST' }),
  emergencyStop: () =>
    apiFetch<{ stopped: boolean }>('/trading/emergency-stop', {
      method: 'POST',
      body: JSON.stringify({ confirm: 'STOP' }),
    }),
}

// ---------------------------------------------------------------------------
// WebSocket client with auto-reconnect
// ---------------------------------------------------------------------------

type EventHandler = (event: BusEvent) => void

export class TradingWebSocket {
  private ws: WebSocket | null = null
  private handlers: EventHandler[] = []
  private retryCount = 0
  private maxRetries = 5
  private stopped = false

  connect() {
    if (this.stopped) return
    try {
      this.ws = new WebSocket(`${WS_URL}/live`)
      this.ws.onopen = () => {
        this.retryCount = 0
        console.log('[WS] Connected')
      }
      this.ws.onmessage = (e) => {
        try {
          const event: BusEvent = JSON.parse(e.data)
          this.handlers.forEach((h) => h(event))
        } catch {
          // ignore parse errors
        }
      }
      this.ws.onclose = () => {
        if (!this.stopped) this._scheduleReconnect()
      }
      this.ws.onerror = () => {
        this.ws?.close()
      }
    } catch {
      this._scheduleReconnect()
    }
  }

  private _scheduleReconnect() {
    if (this.retryCount >= this.maxRetries) {
      console.warn('[WS] Max retries reached')
      return
    }
    const delay = Math.pow(2, this.retryCount) * 1000
    this.retryCount++
    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.retryCount})`)
    setTimeout(() => this.connect(), delay)
  }

  onEvent(handler: EventHandler) {
    this.handlers.push(handler)
  }

  disconnect() {
    this.stopped = true
    this.ws?.close()
  }
}

// ---------------------------------------------------------------------------
// React hooks (client-side only)
// ---------------------------------------------------------------------------

import { useEffect, useState, useCallback } from 'react'

export function usePortfolio(refreshMs = 5000) {
  const [data, setData] = useState<PortfolioState | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const portfolio = await api.getPortfolio()
      setData(portfolio)
      setError(null)
    } catch (e) {
      setError(String(e))
    }
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, refreshMs)
    return () => clearInterval(interval)
  }, [refresh, refreshMs])

  return { data, error, refresh }
}

export function useAgents(refreshMs = 10000) {
  const [agents, setAgents] = useState<AgentStatus[]>([])
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const res = await api.getAgents()
      setAgents(res.agents)
      setError(null)
    } catch (e) {
      setError(String(e))
    }
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, refreshMs)
    return () => clearInterval(interval)
  }, [refresh, refreshMs])

  return { agents, error, refresh }
}

export function useLiveEvents() {
  const [events, setEvents] = useState<BusEvent[]>([])

  useEffect(() => {
    const wsClient = new TradingWebSocket()
    wsClient.onEvent((event) => {
      setEvents((prev) => [event, ...prev].slice(0, 200))
    })
    wsClient.connect()
    return () => wsClient.disconnect()
  }, [])

  return events
}
