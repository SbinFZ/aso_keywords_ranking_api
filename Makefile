.PHONY: install run test lint

VENV ?= .venv
PYTHON := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn

install:
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install -r requirements.txt

run:
	$(UVICORN) app.main:app --reload --port 8000

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m compileall app
