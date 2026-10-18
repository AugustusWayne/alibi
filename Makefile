# Recipes use literal tabs. The original `.RECIPEPREFIX = >` form needs GNU Make
# 3.82+, and macOS ships 3.81 (`make --version`), where it is a syntax error.
# Tabs work on both, so the clean-clone setup check cannot trip over this.
.PHONY: venv up down spikes test verify eval fmt

# The image is pinned by tag AND digest in docker-compose.yml, not here. An
# unpinned tag means FalkorDB behaviour can change under you mid-build, which
# would invalidate every spike result recorded in PROGRESS.md.
PY = .venv/bin/python

# Local overrides (ports, mainly). Committed as .env.example; .env is gitignored.
# `export` with no arguments hands these to docker compose AND to the Python
# client, so the two can never disagree about which port FalkorDB is on.
-include .env
export

venv:
	python3.12 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt

up:
	docker compose up -d
	@echo "waiting for falkordb..."
	@until docker compose exec -T falkordb redis-cli PING >/dev/null 2>&1; do sleep 1; done
	@echo "falkordb up"

down:
	docker compose down

spikes:
	$(PY) -m scripts.spikes

test:
	$(PY) -m pytest backend/tests -q

fmt:
	$(PY) -m ruff check backend scripts --fix
	$(PY) -m ruff format backend scripts

# The gate. A milestone is not done until this passes and you have seen it pass.
verify:
	$(PY) -m ruff check backend scripts
	$(PY) -m pytest backend/tests -q
	@echo "VERIFY OK"

eval:
	$(PY) -m scripts.run_eval --seeds eval/seeds.json

