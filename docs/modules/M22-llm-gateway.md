# M22 — Language Model Gateway

Module specification v1.0 · Owner area: Backend · Depends on: M10

---

## 1. Purpose

Give the narrative and copilot of ARCHITECTURE.md §12 a provider that is reachable and
affordable at hackathon scale, behind one interface, without letting a model anywhere near the
arithmetic.

`NarrativeService` today calls one vendor directly and returns the deterministic narrative when
no credential is present. That is the right shape and the wrong coupling: the provider is a
deployment decision, and a tool that must run on a free tier in one environment and a corporate
account in another needs the choice to be configuration rather than an import.

## 2. Scope

**In scope.** A provider-agnostic chat client over the OpenAI-compatible surface every candidate
provider exposes; the provider registry and its free-tier characteristics; configuration from
the environment; failover order and the circuit breaker; quota accounting before exhaustion
rather than after; caching bound to a run; what may and may not leave the tool in a prompt.

**Out of scope.** Producing numbers — §12.1 and non-negotiable 2, restated in §5.1 and enforced
mechanically. Retrieval and chunking, which are M10's and unchanged. Fine-tuning, model hosting,
and any local inference: this is a client.

## 3. Dependencies

**Upstream.** None. The gateway is a leaf.

**Downstream.** M10's `NarrativeService` and copilot. `biet_engine` never calls it and must not
be able to — `test_layering.py` already forbids the engine importing `httpx`, and the gateway
lives in `biet_api/services/`, which the engine cannot import either.

## 4. Contracts

```python
class LlmProvider(StrEnum):
    ALIBABA_MODEL_STUDIO = "alibaba_model_studio"    # Qwen, international endpoint
    MODELSCOPE = "modelscope"                        # Qwen, DeepSeek, GLM, MiniMax
    HUGGING_FACE = "hugging_face"
    ANTHROPIC = "anthropic"                          # the existing path, unchanged
    NONE = "none"                                    # deterministic narrative only


class ProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: LlmProvider
    base_url: str
    model: str
    daily_call_budget: int
    per_model_daily_budget: int | None = None
    timeout_s: float = LLM_TIMEOUT_DEFAULT_S
    #: Never populated from a config file or a database row. Environment only.
    api_key_env_var: str


class LlmRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    system: str
    user: str
    max_tokens: int
    temperature: float = LLM_TEMPERATURE_DEFAULT     # 0.2 — prose varies, facts do not
    #: Every number the response is permitted to contain. Never empty for a narrative.
    numeric_context: tuple[float, ...]


class LlmOutcome(StrEnum):
    OK = "ok"
    REJECTED_FABRICATED = "rejected_fabricated"
    QUOTA_EXHAUSTED = "quota_exhausted"
    UNREACHABLE = "unreachable"
    NOT_CONFIGURED = "not_configured"
    DISABLED_BY_SCENARIO = "disabled_by_scenario"


class LlmResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome: LlmOutcome
    text: str | None
    provider: LlmProvider | None
    model: str | None
    calls_remaining_today: int | None = None
    detail: str | None = None
```

```python
# biet_api/services/llm_gateway.py
class LlmGateway:
    def complete(self, request: LlmRequest) -> LlmResponse: ...
    def status(self) -> tuple[ProviderStatus, ...]: ...
```

Every caller handles `text is None`. That is not a defensive nicety — the deterministic
narrative is a complete deliverable on its own, and `NarrativeService` already treats a missing
model as an ordinary state rather than an error. The gateway keeps that property.

## 5. Logic specification

### 5.1 The boundary, made mechanical

The model rewrites text that is already correct. It does not compute, sum, average, convert or
infer any figure. This is already how `NarrativeService` works, and the gateway's job is to make
it impossible to use any other way:

- `LlmRequest.numeric_context` is required and is rejected empty for a narrative request. A
  caller who cannot say which numbers are permitted is not ready to call a model.
- Every response passes `biet_engine.narrative.validate_numbers(text, numeric_context)` before
  the gateway returns it. Text containing a number not in the context is discarded, the outcome
  is `REJECTED_FABRICATED`, and the caller falls back to its deterministic text.
- A rejection is recorded per provider and per model. A model that fabricates repeatedly is a
  configuration problem, and the tool should be able to say which one it was.

The validator lives in `biet_engine` and is pure. The engine cannot call the gateway; the
gateway calls the engine's validator. The dependency runs in the safe direction, and
`test_layering.py` enforces it.

### 5.2 The provider registry

Every candidate exposes an OpenAI-compatible chat completions endpoint, so one client covers all
of them and switching provider is a change of base URL, model and key.

| Provider | Base URL | Models | Free tier as reported | Role |
|---|---|---|---|---|
| Alibaba Model Studio | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | `qwen-plus`, `qwen-max` | Approx. 1 M tokens per model, approx. 90 days from activation | Primary |
| ModelScope | `https://api-inference.modelscope.cn/v1/` | Qwen, DeepSeek, GLM, MiniMax | Approx. 2,000 calls/day, approx. 200 per model | Secondary |
| Hugging Face Inference | Router endpoint | Qwen, DeepSeek, GLM | Small monthly credit | Tertiary |
| Anthropic | SDK default | Existing configuration | Paid | Existing path, unchanged |

**These quota figures are as reported in the HEOR review of 2026-08-25 and are not verified by
this project.** Free tiers move, and a number in a specification is stale the moment a provider
changes terms. They are recorded to explain the ordering, not relied upon: §5.5 counts actual
calls, and §5.4 treats exhaustion as a normal failover rather than a surprise. Confirm the
current terms against the provider's own documentation at configuration time.

Two deployment notes worth carrying: ModelScope's free inference requires a linked Alibaba Cloud
account with real-name verification, which is a real barrier for some teams and should be found
out before the demo rather than during it. For a deployment outside mainland China, Model
Studio's international endpoint is the correct one — the region is part of the base URL, and the
mainland endpoint will fail authentication with keys issued for the international console.

### 5.3 Configuration comes from the environment, and only from there

Non-negotiable 4. `.env.example` gains placeholders and no values:

```
# BIET_LLM_PROVIDER=alibaba_model_studio
# BIET_LLM_MODEL=qwen-plus
# BIET_LLM_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
# DASHSCOPE_API_KEY=
# MODELSCOPE_API_TOKEN=
# HF_TOKEN=
```

`ProviderConfig` names the environment variable holding the key; it never holds the key. No key
is written to the database, to a log line, to an error message or to an API response. The status
endpoint of §8 reports whether a provider is configured, never with what.

An unset provider is `LlmProvider.NONE` and is a supported configuration, not a degraded one.
The tool produces its full deliverable with no model available.

### 5.4 Failover, and when to stop trying

```
configured primary → configured secondary → deterministic text
```

- HTTP 429 or a provider's quota signal is `QUOTA_EXHAUSTED` and fails over immediately. It is
  not surfaced to the analyst as an error; the narrative simply comes from the deterministic
  path, which is the same narrative with less polished prose.
- A timeout or connection failure is `UNREACHABLE` and fails over.
- After `LLM_BREAKER_THRESHOLD` consecutive failures (default 3), a provider is skipped for
  `LLM_BREAKER_COOLDOWN_S` (default 300) rather than retried on every request. A demo does not
  have time to wait out three timeouts per narrative section.
- A `REJECTED_FABRICATED` result does **not** fail over to another provider. A second model is
  no more entitled to invent a number than the first, and retrying until something passes the
  validator is exactly the wrong instinct. It falls straight through to deterministic text.

### 5.5 Quota is counted before it is spent

A per-provider, per-model daily counter is checked before the call, not discovered at the 429.
A request that would exceed `daily_call_budget` fails over without being sent. The counter
resets on the provider's stated reset boundary in UTC, and is persisted so a restart does not
reset it — an in-memory counter that forgets on redeploy is how a free tier is burned through in
an afternoon.

The budget is deliberately configured below the provider's stated limit. Reserving headroom
means the tool still works when someone runs the demo twice.

### 5.6 Caching, because runs are immutable

A narrative is cached against `(run_id, section, provider, model, prompt_hash)`. Re-rendering a
completed run returns the same text it returned before. Non-negotiable 9 makes runs immutable,
and text bound to a run that changes each time it is read makes the run's record untrue —
including in a PDF exported twice.

A cache hit consumes no quota, which also makes repeated exports free.

### 5.7 What leaves the tool

A prompt carries the deterministic narrative draft, the retrieved guideline passages and the
numeric context. It does not carry an uploaded workbook, a scenario's full override set, a user
identity or any credential.

A scenario may set `no_external_llm`, which forces `DISABLED_BY_SCENARIO` and the deterministic
path for that scenario regardless of configuration. A confidential asset's price and launch plan
is exactly the kind of thing an organisation may not send to a third-party endpoint, and the
answer to that has to be a switch in the tool rather than a policy in a document. The flag is
recorded on the run, so a stored deliverable states whether a model saw the scenario.

## 6. Validation & edge cases

| Rule | Behaviour |
|---|---|
| No provider configured | `NOT_CONFIGURED`; deterministic narrative; not an error |
| API key environment variable unset for the configured provider | `NOT_CONFIGURED`, naming the variable, never its value |
| `numeric_context` empty on a narrative request | Rejected before any call is made |
| Response contains a number outside the context | `REJECTED_FABRICATED`; no failover; deterministic text |
| Response is not valid JSON where JSON was requested | Treated as unreachable for that provider; failover |
| Provider returns 429 | `QUOTA_EXHAUSTED`; immediate failover |
| Three consecutive failures | Provider skipped for the cooldown |
| Daily budget would be exceeded | Failover without sending the request |
| Scenario sets `no_external_llm` | `DISABLED_BY_SCENARIO`; no call attempted |
| Cache hit | Returned without a call and without consuming quota |
| A key appears in a log line | Test failure — §10 asserts it |

## 7. Data requirements

Creates `llm_call_log`: timestamp, provider, model, section, run id, outcome, latency,
token counts where the provider returns them, and — never — prompt or response text containing
a credential. Creates `llm_quota_counters`: provider, model, UTC date, calls, reset boundary.

`model_runs` gains `narrative_provider`, `narrative_model` and `no_external_llm`, so a stored
run says whether a model touched its text and which one.

## 8. API surface

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/ai/providers` | Configured, reachable, calls remaining. No keys, ever |

Narrative generation stays on M10's existing endpoints. The gateway is infrastructure, not a
feature with a surface of its own.

## 9. Frontend

No slice. One line in the assumption register and in the export footer stating whether the
narrative was model-assisted and by which provider and model, or that it was deterministic. A
reader of an exported deck is entitled to know which it was.

## 10. Test specification

| Class | Test |
|---|---|
| Unit | a response containing a number outside the context is rejected |
| Unit | a rounded form present in the context ("38.2 million" for 38,200,000) is accepted |
| Unit | a fabricated-figure rejection does not fail over to a second provider |
| Unit | no provider configured returns `NOT_CONFIGURED` and the caller still produces a narrative |
| Unit | an unset key names the environment variable and never a value |
| Unit | 429 fails over to the secondary provider |
| Unit | three consecutive failures open the breaker; a request during cooldown is not sent |
| Unit | a request that would exceed the daily budget is not sent |
| Unit | the quota counter survives a restart |
| Unit | `no_external_llm` prevents any outbound call |
| Unit | a cache hit consumes no quota and returns identical text |
| Unit | no log line, error message or API response contains a key — asserted against a fixture key |
| Layering | `biet_engine` imports no HTTP client and cannot reach the gateway |
| Integration | provider switched by environment variable alone, with no code change |
| Integration | every provider in the registry is exercised against a recorded transcript, not a live endpoint |

No test calls a live provider. A test suite that needs a free-tier quota to pass will fail on the
day the quota runs out, which is the day before the demo.

## 11. Acceptance criteria

- [ ] One OpenAI-compatible client serves every provider in the registry
- [ ] Provider, model, base URL and key come from the environment and nowhere else
- [ ] Every response is validated against its numeric context before it is returned
- [ ] A fabricated figure falls through to deterministic text and does not retry elsewhere
- [ ] Quota is counted before spending and persists across restarts
- [ ] Failover order is configured, with a circuit breaker and a cooldown
- [ ] Narrative text is cached per run and is stable across re-exports
- [ ] `no_external_llm` disables the gateway for a scenario
- [ ] No credential reaches a log, an error, a response or the database
- [ ] The tool produces its full deliverable with no provider configured

## 12. Assumptions & open questions

**Assumptions.** Every candidate provider maintains OpenAI-compatible chat completions; a
provider that stops doing so needs an adapter, not a redesign. Free-tier terms as reported in
the review are indicative and are not depended on. The deterministic narrative is good enough to
ship on its own — which is what makes every failure path in this module a graceful one rather
than an outage.

**Open questions.**
1. Whether the copilot should be allowed a provider the narrative is not. The copilot answers
   methodological questions where a fabricated *number* is the risk but a fabricated
   *interpretation* is subtler and the validator does not catch it.
2. Whether to route retrieval embeddings through the same gateway. They currently run locally
   through `fastembed`, which keeps the corpus off the network entirely — a property worth more
   than the latency it costs.
3. Whether a rejection rate above a threshold should disable a provider for narrative use
   automatically, rather than only being reported.
