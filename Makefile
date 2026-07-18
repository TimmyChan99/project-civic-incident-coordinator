.PHONY: install lint format test run docker

install:
	python -m pip install --requirement requirements-dev.txt

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

test:
	pytest --cov=app --cov-report=term-missing

run:
	uvicorn app.api:app --reload --port 8000

docker:
	docker compose up --build
