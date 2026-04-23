# Security Model

This document describes the threat model and mitigations for the
Polymarket Trading Firm.

---

## Threat 1: Prompt Injection via Market Data

**Threat**: A malicious market creator writes `"ignore previous instructions"` in the
market question or description, attempting to hijack Claude's output.

**Mitigation**:
- `sanitize_for_prompt(s, field)` in `core/security.py` strips 10+ injection patterns
  before any market string enters a Claude prompt.
- SecurityAgent scans every market before analysis via `scan_market()`.
- All market data is flagged and logged to `security.log` on detection.

---

## Threat 2: Oversized API Responses (DoS)

**Threat**: A compromised or malicious API endpoint returns a multi-gigabyte JSON response,
causing the process to OOM crash.

**Mitigation**:
- `safe_json_from_response()` streams responses in 64KB chunks and enforces a hard 5 MB cap.
- Content-Type is validated before parsing.

---

## Threat 3: SSRF / URL Injection

**Threat**: Attacker injects a malicious URL into a market field, causing the system to
make outbound requests to internal services.

**Mitigation**:
- `assert_safe_url(url)` validates scheme (must be `https`) and hostname
  against a fixed allowlist (`ALLOWED_HOSTS`).
- Applied to every outbound HTTP request.

---

## Threat 4: Portfolio State Tampering

**Threat**: Attacker with filesystem access modifies `portfolio_state.json` to inflate
the balance or remove positions.

**Mitigation**:
- Every save includes an HMAC-SHA256 signature (`sign_state` / `verify_state`).
- Every load verifies the signature; failure → fresh portfolio (log error, never load tampered state).
- Balance > 10× starting is rejected as implausible (even if HMAC passes).

---

## Threat 5: Secret Leakage via Logs

**Threat**: Anthropic API keys or EVM private keys appear in log files.

**Mitigation**:
- `ScrubbingFilter` (a `logging.Filter` subclass) is attached to every logger handler.
- It calls `scrub_secrets()` on every log record before emit.
- Regex patterns cover `sk-ant-*` keys and 64-hex EVM private keys.

---

## Threat 6: Wash Trading / Market Manipulation

**Threat**: A market has artificially inflated volume with near-zero liquidity
(wash trading) to appear active.

**Mitigation**:
- SecurityAgent flags markets where `liquidity < 1% of volume`.
- Severity computed as "high" → market is skipped automatically.

---

## Threat 7: Price Manipulation / Stale Prices

**Threat**: Market prices are manipulated or stale, causing agents to see a false edge.

**Mitigation**:
- `Market.__post_init__` validates every price with `validate_price()` (0.001–0.999).
- Price sum check: if YES + NO deviates from 1.0 by > 0.15, market is rejected.
- Analyst agent tracks 24h price drift via memory and flags large movements.

---

## Threat 8: Rate Limit Bypass / API Abuse

**Threat**: The trading loop hammers the Anthropic or Polymarket APIs, incurring massive costs
or triggering rate-limit bans.

**Mitigation**:
- `RateLimiter` (sliding window) enforces 50 calls/min per agent to Anthropic.
- Polymarket: 120 calls/min for market data, 10 calls/min for live orders.
- `wait_if_needed()` blocks until the window clears.

---

## Threat 9: Circuit Breaker Bypass

**Threat**: A bug or attacker manipulates equity readings, bypassing the circuit breaker.

**Mitigation**:
- Circuit breaker is checked at the **start** of every cycle (Step 1) AND
  immediately before every execution (Step 7).
- Once tripped, it stays tripped until manually reset — no automatic recovery.
- Portfolio HMAC prevents external tampering with equity values.

---

## Threat 10: Insecure CLOB Authentication

**Threat**: Private key is logged, hardcoded, or transmitted insecurely.

**Mitigation**:
- All secrets read from environment variables via `python-dotenv`.
- `ScrubbingFilter` removes keys from logs.
- `.env` file permissions set to 600 by `setup.sh`.
- `.gitignore` excludes `.env` at the project root.

---

## Threat 11: Dependency Supply Chain

**Threat**: A compromised Python package introduces malicious code.

**Mitigation**:
- `requirements.txt` pins minimum versions.
- For production use: `pip install --require-hashes` with locked hash file.
- Run `pip audit` regularly.

---

## Threat 12: WebSocket Eavesdropping

**Threat**: An attacker on the same network intercepts the WebSocket stream,
seeing portfolio state and trade decisions.

**Mitigation**:
- CORS is restricted to `http://localhost:3000` only.
- API server binds to `localhost:8000` by default (not 0.0.0.0).
- For production: add TLS termination via reverse proxy (nginx/caddy).

---

## Threat 13: Fake News / Journalist Manipulation

**Threat**: An adversary publishes fake news stories that score highly in the journalist's
web search, causing a bad trading decision.

**Mitigation**:
- Journalist agent uses a curated source filter (reuters.com, bbc.com, apnews.com).
- Contrarian agent stress-tests all consensus decisions.
- Multiple independent agents must agree before a trade is placed.
- Minimum consensus score of 0.65 prevents single-source manipulation.

---

## Threat 14: Agent Accuracy Gaming

**Threat**: An attacker manipulates the SQLite memory database to lower an agent's
accuracy weight, reducing its influence on consensus.

**Mitigation**:
- Memory database is a local SQLite file — access requires filesystem compromise.
- Accuracy starts at 0.5 (neutral) and moves slowly with each trade.
- All agents are clipped to minimum weight 0.1, so accuracy gaming has limited effect.
- For production: encrypt the memory database with SQLCipher.

---

## Threat 15: Honeypot Markets

**Threat**: A market is deliberately structured to appear profitable but
resolves adversarially (e.g., ruled invalid or resolved by a corrupt oracle).

**Mitigation**:
- SecurityAgent flags markets with extreme price skew (>0.95) as potential honeypots.
- Risk Manager requires a minimum liquidity of $1,000 before analysis.
- Contrarian specifically looks for "too easy" opportunities and flags them.

---

## Threat 16: HMAC Key Rotation

If `PORTFOLIO_HMAC_KEY` is compromised:

1. Stop the trading loop.
2. Generate a new key: `python3 -c "import secrets; print(secrets.token_hex(32))"`
3. **Do not simply replace the key** — the existing portfolio file will fail verification.
4. Export portfolio state to a JSON backup before changing the key.
5. Re-sign the backup with the new key using `sign_state()`.
6. Update `PORTFOLIO_HMAC_KEY` in `.env`.
7. Restart the loop.

---

## Threat 17: Eval / Code Injection

**Threat**: Malicious JSON from Claude's response is executed as code.

**Mitigation**:
- `json.loads()` is the only parser used — never `eval()`, `exec()`, or `pickle`.
- All agent outputs go through `_parse_opinion()` which validates every field.
- Invalid JSON → `SKIP` (never crash).

---

## Reporting Security Issues

If you discover a security vulnerability, please open a private issue or contact
the maintainers directly. Do not post vulnerability details publicly until patched.
