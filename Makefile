.PHONY: install test init collect-static collect-dynamic api scheduler docker-up docker-down

install:
	python -m pip install -e ".[dev]"

test:
	pytest -q

init:
	mobie-uptime init-db

collect-static:
	mobie-uptime collect-static

collect-dynamic:
	mobie-uptime collect-dynamic

api:
	uvicorn mobie_uptime.api:app --reload

scheduler:
	mobie-uptime scheduler

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down
