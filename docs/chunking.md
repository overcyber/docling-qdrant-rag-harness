# Chunking configuration

The harness supports exactly three Docling chunking modes. Defaults are controlled through `.env`; each upload can override them through the multipart `processing_options` JSON field.

## 1. Hybrid

Recommended default for general RAG.

It starts from structure-aware hierarchical chunks and then applies tokenizer-aware refinement. It can split oversized chunks and merge compatible undersized neighboring chunks.

```json
{
  "chunking": {
    "type": "hybrid",
    "tokenizer_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "max_tokens": 120,
    "merge_peers": true,
    "repeat_table_header": true,
    "omit_header_on_overflow": false,
    "always_emit_headings": false
  }
}
```

Important parameters:

| Field | Meaning |
|---|---|
| `max_tokens` | target maximum chunk token count |
| `merge_peers` | merge compatible small chunks |
| `repeat_table_header` | preserve table header context across split table chunks |
| `omit_header_on_overflow` | allow a row to omit repeated header when it would overflow |
| `always_emit_headings` | emit heading-only sections when necessary |

## 2. Hierarchical

Best when preserving the original document hierarchy matters more than enforcing a uniform token window.

```json
{
  "chunking": {
    "type": "hierarchical",
    "merge_list_items": true,
    "always_emit_headings": false
  }
}
```

`merge_list_items` exists for compatibility with current Docling behavior but is deprecated upstream. Avoid building new application logic that depends on it.

## 3. Line based

Best for logs, tables, source code and other line-oriented technical content.

```json
{
  "chunking": {
    "type": "line_based",
    "tokenizer_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "max_tokens": 120,
    "prefix": "",
    "omit_prefix_on_overflow": true
  }
}
```

This chunker attempts to keep each line intact and only splits a line when it cannot fit by itself.

### Provenance note

Current Docling `LineBasedTokenChunker` serializes the complete document before line splitting. Consequently, chunk-level page provenance is less precise than hybrid/hierarchical provenance. The API reports `page_provenance="document"` for line-based chunks so downstream agents do not mistake document-wide pages for exact chunk pages.

## Per-upload example

```bash
curl -X POST http://localhost:8000/v1/documents \
  -H 'X-Tenant-ID: engineering' \
  -F 'file=@manual.pdf' \
  -F 'processing_options={
    "chunking": {
      "type":"hybrid",
      "max_tokens":120,
      "merge_peers":true
    },
    "pdf": {
      "do_ocr":true,
      "do_table_structure":true,
      "do_cell_matching":true
    },
    "conversion": {
      "max_num_pages":1500,
      "page_range":[1,250]
    },
    "deduplicate":true
  }'
```

## Choosing a strategy

| Corpus | Recommended |
|---|---|
| reports, papers, policies, manuals | `hybrid` |
| highly structured documents where sections/items matter | `hierarchical` |
| logs, code, CSV-like text, wide tables | `line_based` |
| unknown mixed corpus | start with `hybrid` and measure retrieval quality |


## Comparing the three chunkers with the same file

The default deduplicator is processing-aware: the fingerprint includes file content, parser/chunking configuration and user metadata. This means the same source can be uploaded once per chunking strategy without `deduplicate:false`. Identical repeated uploads with the same profile are still suppressed.

For controlled experiments, keep metadata and parser options fixed and vary only `chunking.type`/chunk parameters. You can filter retrieval directly with `{"chunker_type":"hybrid"}`. For richer experiment tracking, also store an experiment label in metadata, for example `{"chunk_experiment":"hybrid-120"}`.

## Token budget must match the embedding model

The token window used by the chunker must not exceed the effective input window of the dense embedding model, otherwise the embedder may silently truncate text and the vector no longer represents the complete chunk.

The default model, `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, has a Sentence Transformers `max_seq_length` of 128. The harness therefore uses `CHUNK_MAX_TOKENS=120` by default to leave a small budget for structural context/headings.

If you change `DENSE_MODEL`, review its actual tokenizer/model limit and set both `CHUNK_TOKENIZER_MODEL` and `CHUNK_MAX_TOKENS` accordingly. For hybrid RAG, tokenizer alignment is part of the retrieval design, not merely a performance setting.
