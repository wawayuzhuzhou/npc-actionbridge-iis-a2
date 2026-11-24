# Qwen configuration

The shared adapter retains the upstream NPC prompt, action vocabulary and history
policy. [Offline reproduction](../../docs/REPRODUCTION.md) uses mocks and fixtures.

For optional live use, supply the following through your own external dotenv
file or environment: `A2_PROXY_BASE_URL` (provider base URL), `A2_PROXY_API_KEY`
and `A2_PROXY_MODEL`. The recorded chat model was `qwen3.7-flash`; embeddings use
`text-embedding-v4` and 1024 dimensions. Thinking defaults to false. A trusted
FAISS index must match the embedding configuration. The index is not included.

For B also set `A2_UPSTREAM_DB_PATH` to a separate runtime DB and
`A2_QWEN_FAISS_PATH` to the trusted index. The existing entry points are:

```powershell
python -m adapter.qwen_baseline.run --dotenv "<external-config>"
python -m adapter.actionbridge.run --dotenv "<external-config>" --db "<A-runtime-db>" --faiss-path "<trusted-index>" --port 8001
```

B serves port 8000; A serves 8001. Game copies are prepared by the reproduction
procedure. Credentials, index and databases stay outside this repository.
Live dialogue and index creation contact the provider and incur usage; they are
not part of offline verification. Preserve the [upstream MIT notice](../../notices/UPSTREAM_MIT.txt)
for the reused prompt, facts and API contract.
