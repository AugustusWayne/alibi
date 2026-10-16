# .RECIPEPREFIX lets recipes use '>' instead of a literal tab, which survives
# copy-paste between editors. Needs GNU Make 3.82+. Delete this line and convert
# to tabs if your make is older.
.RECIPEPREFIX = >
.PHONY: up down spikes test verify eval demo fmt

# Pin the image. An unpinned tag means FalkorDB behaviour can change under you
# mid-build, which would invalidate every spike result.
FALKOR_IMAGE ?= falkordb/falkordb:latest

up:
> docker compose up -d
> @echo "waiting for falkordb..."
> @until docker compose exec -T falkordb redis-cli PING >/dev/null 2>&1; do sleep 1; done
> @echo "falkordb up"

down:
> docker compose down

spikes:
> python -m scripts.spikes

test:
> pytest backend/tests -q

fmt:
> ruff check backend --fix
> ruff format backend

# The gate. A milestone is not done until this passes and you have seen it pass.
verify:
> ruff check backend
> pytest backend/tests -q
> @echo "VERIFY OK"

eval:
> python -m scripts.run_eval --seeds eval/seeds.json

demo:
> python -m scripts.record_demo
