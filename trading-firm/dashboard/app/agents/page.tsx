'use client'

import { useAgents, api, type AgentStatus } from '../../lib/api'
import { useState } from 'react'

const AGENT_ICONS: Record<string, string> = {
  analyst: '📊',
  journalist: '📰',
  macro: '🌍',
  historian: '📚',
  risk_manager: '🛡️',
  contrarian: '🔄',
  strategist: '♟️',
  security_agent: '🔒',
  execution: '⚡',
}

function AgentCard({ agent, onToggle }: { agent: AgentStatus; onToggle: () => void }) {
  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{AGENT_ICONS[agent.agent_id] ?? '🤖'}</span>
          <div>
            <div className="font-syne font-semibold text-sm">{agent.agent_id}</div>
            <div className="text-xs text-[#c8d8e866]">
              {agent.last_analysis_at
                ? new Date(agent.last_analysis_at).toLocaleTimeString()
                : 'No analysis yet'}
            </div>
          </div>
        </div>
        <button
          onClick={onToggle}
          className={`text-xs px-3 py-1 rounded border transition-colors ${
            agent.paused
              ? 'border-[#00e5cc] text-[#00e5cc] hover:bg-[#00e5cc22]'
              : 'border-[#ff3355] text-[#ff3355] hover:bg-[#ff335522]'
          }`}
        >
          {agent.paused ? 'Resume' : 'Pause'}
        </button>
      </div>

      {/* Status badge */}
      <div className="flex items-center gap-2">
        <span
          className="w-2 h-2 rounded-full"
          style={{ background: agent.paused ? '#ff3355' : '#00e5cc' }}
        />
        <span className="text-xs" style={{ color: agent.paused ? '#ff3355' : '#00e5cc' }}>
          {agent.paused ? 'PAUSED' : 'ACTIVE'}
        </span>
      </div>

      {/* Accuracy */}
      <div>
        <div className="flex justify-between text-xs mb-1">
          <span className="text-[#c8d8e888]">Accuracy</span>
          <span>{(agent.accuracy * 100).toFixed(1)}%</span>
        </div>
        <div className="h-1.5 bg-[#ffffff11] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${agent.accuracy * 100}%`,
              background: agent.accuracy > 0.6 ? '#00e5cc' : '#ff6b35',
            }}
          />
        </div>
      </div>
    </div>
  )
}

export default function AgentsPage() {
  const { agents, refresh } = useAgents(5000)
  const [loading, setLoading] = useState<string | null>(null)

  const toggleAgent = async (agent: AgentStatus) => {
    setLoading(agent.agent_id)
    try {
      if (agent.paused) {
        await api.resumeAgent(agent.agent_id)
      } else {
        await api.pauseAgent(agent.agent_id)
      }
      await refresh()
    } catch (e) {
      console.error(e)
    }
    setLoading(null)
  }

  return (
    <div>
      <h1 className="font-syne font-bold text-2xl text-[#00e5cc] mb-6">
        Agent Command Centre
      </h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.length === 0 ? (
          <div className="text-[#c8d8e844] col-span-3">
            Loading agents... (ensure the API server is running)
          </div>
        ) : (
          agents.map((agent) => (
            <AgentCard
              key={agent.agent_id}
              agent={agent}
              onToggle={() => toggleAgent(agent)}
            />
          ))
        )}
      </div>
    </div>
  )
}
