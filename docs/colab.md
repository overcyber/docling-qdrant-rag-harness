# Google Colab

The repository contains:

```text
colab/RAG_Harness_Colab.ipynb
```

The notebook demonstrates the same logical pipeline without depending on Docker-in-Docker:

```text
upload -> Docling -> selected chunker -> embeddings -> embedded/local Qdrant -> retrieval
```

It includes a `CHUNKER_TYPE` selector for:

- `hybrid`;
- `hierarchical`;
- `line_based`.

For a production-like deployment, use Docker Compose outside Colab. Colab should be treated as a functional demonstration and experimentation environment, not as persistent infrastructure.
