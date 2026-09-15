SHELL := /bin/bash

.PHONY: init up down logs ps smoke validate docs monitoring events ollama llama-cpp vllm clean

init:
	@test -f .env || cp .env.example .env

up: init
	docker compose up -d --build

docs: init
	docker compose --profile documentation up -d docs

monitoring: init
	docker compose --profile monitoring up -d flower

events: init
	docker compose --profile events up -d nats

ollama: init
	docker compose --profile ollama up -d ollama

llama-cpp: init
	docker compose --profile llama-cpp up -d llama-cpp

vllm: init
	docker compose --profile vllm up -d vllm

validate:
	bash scripts/validate.sh

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

smoke:
	bash scripts/smoke_test.sh

clean:
	docker compose down -v --remove-orphans
