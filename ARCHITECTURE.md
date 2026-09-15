# Architecture

Canonical architecture documentation is maintained in [docs/architecture.md](docs/architecture.md).

The public surface is one FastAPI service on port 8000. Parsing, embedding, queueing and storage remain separate internal microservices/components.
