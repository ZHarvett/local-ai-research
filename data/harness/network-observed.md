# Harness network and file-write behaviour (WP7)

OpenCode 1.19.5 and dsh 0.2.1-rc.5, observed on 2026-11-08. Sources: the installed packages' own
documentation and embedded source, `--help` / `--dump-*` / `debug` output, and runs through
`scripts/_sandbox.sh` with a deny-all logging proxy (`smallpc.netproxy`). Raw evidence is in
`discovery/` (proxy logs and warning lines of each discovery run) and in the `probe-*` and
`attempt-*` directories of the smoke runs.

## What a proxy can and cannot show
A proxy sees only traffic from clients that honour `HTTP(S)_PROXY`. Traffic that ignores the
settings is invisible to it, and `strace` is not installed here. Two things limit that blind spot:
the smoke runs additionally sit in a private network namespace (`_sandbox.sh --bridge`) that has
**only** the llama-server port and the proxy port bridged in, so anything else fails with
"Network is unreachable" instead of leaving the machine (tested: `tests/test_sandbox.py`, and a
`curl --noproxy '*'` step in the dsh probe); and the control runs below show that OpenCode's own
HTTP client does go through the proxy. Whether a *particular* code path ignores the proxy is "not
verified" by observation; the namespace is what contains it.

## OpenCode 1.19.5
| Behaviour | Seen | Setting | In the smoke runs |
|---|---|---|---|
| Model catalogue GET `https://models.opencode.ai/api.json` (3 attempts, a few seconds after start) | proxy control run `control-slow` | `OPENCODE_DISABLE_MODELS_FETCH=1` | not attempted (`flags-off` run, smoke runs) |
| Background dependency install of `@opencode-ai/plugin` into the config dir (GET `registry.npmjs.org`), for every config directory, unconditionally | `control-slow`, `flags-off`, `flags-pure`, every smoke run | **no switch found** (embedded source: no flag check; `OPENCODE_PURE=1` does not stop it) | attempted once per run, **refused by the proxy**; OpenCode logs a WARN and carries on; nothing downloaded |
| Update check / self-update | not attempted in any run (`opencode run`) | `autoupdate: false` and `OPENCODE_DISABLE_AUTOUPDATE=1` | off |
| Session sharing | not attempted | `share: "disabled"` | off |
| Default plugin installs | not seen | `OPENCODE_DISABLE_DEFAULT_PLUGINS=1` | off |
| LSP server download | not seen; log says "all LSPs are disabled" in `opencode run` | `OPENCODE_DISABLE_LSP_DOWNLOAD=1` | off |
| `@ai-sdk/openai-compatible` | **bundled** ("llm runtime selected llm.runtime=ai-sdk"); it worked with registry access refused | none needed | no download |
| Other providers (Zen etc.) | none | `enabled_providers: ["llamacpp"]` | local only |
| Telemetry | none found (no OTel export in any run) | n/a | none |
| Title request | yes: one extra model call per run, `agent=title small=true` (falls back to the main model) | stock behaviour, left on | on, see request-pattern.json |
| Reads of `~/.claude/*` fallbacks, `~/.config/opencode` | HOME redirected, `/home` is an empty tmpfs | isolation | none possible |

Files written (all under `third_party/harness-state/opencode/`): `data/opencode/opencode.db` and
`log/`, `data/opencode/snapshot/<project>/...` (OpenCode's own git-based snapshot repositories),
`config/opencode/.gitignore`, `tmp/`. No cache directory was created (the catalogue was never
fetched). Nothing was written under `~`.

## dsh 0.2.1-rc.5
| Behaviour | Seen | Setting | In the smoke runs |
|---|---|---|---|
| Session telemetry (OTLP logs to `https://dsh-otel-collector.deepseeksvc.com/v1/logs`) | configured in the shipped profile; per its README it uploads only after explicit feedback (default `FEEDBACK_ONLY`) | `DSH_TELEMETRY_MODE=DISABLED` (no transport constructed) | off; no connection to any host in any run |
| Web search / fetch tools (DeepSeek API, HTTP) | in the shipped profile | `disabled: true` for `tool-web`, `web-search-deepseek`, `web-deepseek-api`, `web-fetch-http` in the profile patch | off |
| Update checks, auto-downloads | none seen; headless boots offline (no pnpm needed; the profile's `package.json` has no dependencies) | n/a | none |
| Approvals | shipped policy `ask`; headless has no answerer, so it fails closed ("requires approval, but no approval channel is available", probed) | kept | fail closed |
| File sandbox | `DSH_PERMISSION_MODE=workspace-write`: writes outside the workspace are refused, **but** `/tmp` writes and bash network access are not restricted by dsh | `_sandbox.sh` (read-only file system, private `/tmp`, network namespace) | contains both |
| Title request | yes (`session-title-first-prompt-llm`): one extra model call without tools | shipped | on |
| Reads outside the workspace | allowed by dsh (the probe read `/etc/hostname`) | `_sandbox.sh` hides `/home`; the hostname in transcripts is scrubbed | `smallpc.scrub` |

Files written: `third_party/harness-state/dsh/dsh-home/` (`profiles/headless` copied from the shipped
template, `sessions/`, `storages/`) and `third_party/harness-state/dsh/tmp/` (a native-module
cache of `node-addon-require-builtin`). Nothing under `~`.

## Discovery runs (`discovery/`)
| Run | Isolation | Setup | Proxy saw |
|---|---|---|---|
| `control` | sandbox, deny-all proxy | defaults, run exits in about 1 s | nothing (too short for the background tasks) |
| `posctl-webfetch` | same | the fake model failed to start, so the run lasted 90 s | `models.opencode.ai` x3, `registry.npmjs.org`: proves the proxy sees OpenCode's HTTP client |
| `control-slow` | same | defaults, model answers after 8 s | `models.opencode.ai` x3, `registry.npmjs.org` |
| `flags-off` | same | four `OPENCODE_DISABLE_*` flags | `registry.npmjs.org` only |
| `flags-pure` | same | plus `OPENCODE_PURE=1` | `registry.npmjs.org` only |
| `probe-oc`, `probe-ask`, `dsh-basic`, `probe-dsh`, `probe-dsh2` | sandbox + proxy (the network namespace was added during this stage, so the earliest runs have the proxy only) | scripted fake model | the probe's own `curl`, and `registry.npmjs.org` for OpenCode |
