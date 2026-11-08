# Local AI on a Small PC

Measured, reproducible baselines for running a 35B mixture-of-experts coding model
(Ornith-1.5-35B-A3B) with llama.cpp on a 16 GB consumer GPU: stock vs tuned server configurations
at 32K, 64K and 128K context, plus harness setup for OpenCode and dsh.

**Status: work in progress.**

## Model

| Item | Value |
|---|---|
| Repository | `ornith-ai/Ornith-1.5-35B-A3B-GGUF` |
| Revision | `f60452672689e0040be350560267a614cc172a18` (2026-08-24) |
| File | `Ornith-1.5-35B-Q4_K_M.gguf`, 21,713,463,040 bytes |
| SHA-256 | `42739874cc2ccfdb8523b23fbe52e29b2a7555c8176737ca9ca0b5d59859d41f` |
| License | MIT (as stated on the repository) |

The file lives in `models/` (not tracked by git). To download it again and verify it:

```bash
HF_HOME="$PWD/models/.hf-home" uvx --from huggingface_hub==2.4.0 hf download \
  ornith-ai/Ornith-1.5-35B-A3B-GGUF Ornith-1.5-35B-Q4_K_M.gguf \
  --revision f60452672689e0040be350560267a614cc172a18 --local-dir "$PWD/models"
sha256sum models/Ornith-1.5-35B-Q4_K_M.gguf   # must match the SHA-256 above
```

Revision, sampling settings and chat template are recorded in `configs/model.toml`. The MTP-head
screen (`uv run python -m smallpc.gguf_check models/Ornith-1.5-35B-Q4_K_M.gguf`) writes
`data/health/model-check.json`; a PASS means only "no known broken-head signature".
