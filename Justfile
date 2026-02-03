set dotenv-load := true

venv := ".venv"
python := venv + "/bin/python"
uvicorn := venv + "/bin/uvicorn"

default: run

install:
	python3 -m venv {{venv}}
	{{python}} -m pip install -r requirements.txt

run:
	{{uvicorn}} app.main:app --reload --port 8000

test:
	{{python}} -m pytest -q

lint:
	{{python}} -m compileall app
