'use client'

import { useEffect, useState } from 'react'
import { api, type Config } from '../../lib/api'

const PROFILES = [
  {
    name: 'conservative',
    label: 'Conservative',
    desc: 'Max $20/position, 5 open, 15% circuit breaker',
    color: '#00e5cc',
  },
  {
    name: 'moderate',
    label: 'Moderate',
    desc: 'Max $50/position, 10 open, 25% circuit breaker',
    color: '#ff6b35',
  },
  {
    name: 'aggressive',
    label: 'Aggressive',
    desc: 'Max $100/position, 20 open, 40% circuit breaker',
    color: '#ff3355',
  },
]

export default function SettingsPage() {
  const [config, setConfig] = useState<Config | null>(null)
  const [stopInput, setStopInput] = useState('')
  const [showStopModal, setShowStopModal] = useState(false)
  const [showLiveModal, setShowLiveModal] = useState(false)
  const [liveInput, setLiveInput] = useState('')
  const [status, setStatus] = useState('')

  useEffect(() => {
    api.getConfig().then(setConfig).catch(console.error)
  }, [])

  const setProfile = async (profile: string) => {
    await api.setRiskProfile(profile)
    const updated = await api.getConfig()
    setConfig(updated)
    setStatus(`Risk profile changed to ${profile}`)
  }

  const handleEmergencyStop = async () => {
    if (stopInput !== 'STOP') return
    await api.emergencyStop()
    setShowStopModal(false)
    setStatus('Emergency stop executed — all trading halted.')
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="font-syne font-bold text-2xl text-[#00e5cc]">Settings</h1>

      {status && (
        <div className="card border-[#00e5cc44] text-[#00e5cc] text-sm">{status}</div>
      )}

      {/* Risk profile */}
      <div className="card">
        <div className="font-syne font-semibold text-[#00e5cc] mb-4">Risk Profile</div>
        <div className="space-y-3">
          {PROFILES.map((p) => (
            <button
              key={p.name}
              onClick={() => setProfile(p.name)}
              className={`w-full text-left p-4 rounded border transition-all ${
                config?.risk_profile === p.name
                  ? 'border-[#00e5cc] bg-[#00e5cc11]'
                  : 'border-[#ffffff11] hover:border-[#ffffff33]'
              }`}
            >
              <div className="flex justify-between items-center">
                <span className="font-semibold" style={{ color: p.color }}>
                  {p.label}
                </span>
                {config?.risk_profile === p.name && (
                  <span className="text-xs text-[#00e5cc]">● ACTIVE</span>
                )}
              </div>
              <div className="text-xs text-[#c8d8e888] mt-1">{p.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Current config */}
      {config && (
        <div className="card">
          <div className="font-syne font-semibold text-[#00e5cc] mb-4">Current Configuration</div>
          <div className="space-y-2 text-sm">
            {[
              ['Mode', config.paper_trading ? 'PAPER TRADING' : '⚠️ LIVE TRADING'],
              ['Loop Interval', `${config.loop_interval_sec}s`],
              ['Min Edge Threshold', `${(config.min_edge_threshold * 100).toFixed(0)}%`],
              ['Min Consensus Score', config.min_consensus_score.toFixed(2)],
              ['Max Position', `$${config.max_position_usd}`],
              ['Max Open Positions', String(config.max_open_positions)],
              ['Circuit Breaker', `${config.circuit_breaker_pct}%`],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span className="text-[#c8d8e888]">{k}</span>
                <span
                  className="font-mono"
                  style={{
                    color:
                      v.includes('LIVE') ? '#ff6b35' : '#c8d8e8',
                  }}
                >
                  {v}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Emergency stop */}
      <div className="card border-[#ff335533]">
        <div className="font-syne font-semibold text-[#ff3355] mb-2">Emergency Stop</div>
        <div className="text-xs text-[#c8d8e888] mb-4">
          Cancels all pending orders and immediately halts the trading agent.
        </div>
        <button
          onClick={() => setShowStopModal(true)}
          className="px-4 py-2 bg-[#ff335522] text-[#ff3355] border border-[#ff3355] rounded hover:bg-[#ff335544] transition-colors text-sm"
        >
          ⚠ EMERGENCY STOP
        </button>
      </div>

      {/* Emergency stop modal */}
      {showStopModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="card border-[#ff3355] max-w-sm w-full mx-4">
            <div className="font-syne font-bold text-[#ff3355] text-lg mb-2">Confirm Emergency Stop</div>
            <div className="text-sm text-[#c8d8e888] mb-4">
              This will cancel all pending orders and halt all agent activity.
              Type STOP to confirm.
            </div>
            <input
              className="w-full bg-[#080c10] border border-[#ff335566] text-[#ff3355] rounded px-3 py-2 mb-4 text-sm font-mono outline-none focus:border-[#ff3355]"
              placeholder="Type STOP"
              value={stopInput}
              onChange={(e) => setStopInput(e.target.value)}
            />
            <div className="flex gap-3">
              <button
                onClick={() => { setShowStopModal(false); setStopInput('') }}
                className="flex-1 px-4 py-2 border border-[#ffffff22] rounded text-sm hover:bg-[#ffffff11]"
              >
                Cancel
              </button>
              <button
                onClick={handleEmergencyStop}
                disabled={stopInput !== 'STOP'}
                className="flex-1 px-4 py-2 bg-[#ff3355] text-white rounded text-sm disabled:opacity-30 hover:bg-[#ff3355cc]"
              >
                Confirm Stop
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
