PY := $(CURDIR)/.venv/bin/python
.PHONY: demo api web test setup

setup:
	python3.11 -m venv .venv && .venv/bin/pip install -q -r backend/requirements.txt
	cd frontend && npm install

api:
	cd backend && $(PY) -m uvicorn app.main:app --port 8000 --reload

web:
	cd frontend && npm run dev -- --port 5173

# One command: API on :8000, UI on :5173
demo:
	@echo "Charge → http://localhost:5173"
	@trap 'kill 0' INT TERM; \
	(cd backend && $(PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000) & \
	(cd frontend && npm run dev -- --port 5173) & \
	wait

test:
	$(PY) -m pytest -q tests
