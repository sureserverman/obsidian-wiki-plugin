# Candidate qualification — 2026-10-08

All runtime trials used synthetic documents on this Linux workstation. Full-corpus speed and quality remain unmeasured.

| Candidate | Release/license | Runtime and models | Measured access | Remaining proof |
|---|---|---|---|---|
| SQLite FTS5 | 3.45.1, public domain | Python 3.12.3; no models | Index/search/read synthetic PASS | Full corpus; lifecycle; recall |
| QMD | 2.8.3, MIT code | Node 22.19.0; 2,255,183,040 model bytes; CPU | Lexical/vector/hybrid with and without reranking PASS; four MCP tools | Full corpus; lifecycle; recall; native retention |
| GraphRAG | 3.2.0, MIT | Python 3.11–3.13; extraction/summarization LLMs | Documentation only | Conditional trigger; local execution/cost unmeasured |
| LightRAG | 1.5.7, MIT | Python >=3.10; configured embedding/extraction models | Documentation only | Conditional trigger; lifecycle/host unmeasured |

QMD 2.8.3 ordinary frontmatter is text, not typed metadata. Installed MCP tools are `query`, `get`, `multi_get`, and `status`; the current main README documents additional features absent from this release. Read-only annotations do not prevent cache writes. Database storage remains local; HTTP access has no built-in authentication.

An initial SDK embedding trial timed out after 300 seconds because the global chunk tokenizer resolved its default model separately from per-store model paths. Setting all three model environment paths to pinned local files fixed that route; native sources were unchanged. RSS snapshots are distinct from future peak measurements.

Other hosts are BLOCKED: no declared targets/access. Graph engines remain documentation-only until the frozen development failure trigger fires.

- [sqlite_fts5](https://sqlite.org/fts5.html)
- [sqlite_license](https://sqlite.org/copyright.html)
- [sqlite_network](https://sqlite.org/useovernet.html)
- [qmd_release](https://github.com/tobi/qmd/releases/tag/v2.8.3)
- [qmd_docs](https://github.com/tobi/qmd/blob/v2.8.3/README.md)
- [qmd_store](https://github.com/tobi/qmd/blob/v2.8.3/src/store.ts)
- [qmd_llm](https://github.com/tobi/qmd/blob/v2.8.3/src/llm.ts)
- [qmd_mcp](https://github.com/tobi/qmd/blob/v2.8.3/src/mcp/server.ts)
- [embedding_card](https://huggingface.co/google/embeddinggemma-300m)
- [reranker_card](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)
- [expansion_card](https://huggingface.co/tobil/qmd-query-expansion-1.7B-gguf)
- [graph_query](https://microsoft.github.io/graphrag/query/overview/)
- [graph_index](https://microsoft.github.io/graphrag/index/overview/)
- [graph_release](https://github.com/microsoft/graphrag/releases/tag/v3.2.0)
- [light_release](https://github.com/HKUDS/LightRAG/releases/tag/v1.5.7)
- [light_docs](https://github.com/HKUDS/LightRAG/tree/v1.5.7)
