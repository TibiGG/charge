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

# ---- Deploy (localhost stays the demo plan; this is for the submission link) ----
# Backend: make api-image && make api-run   (test the container locally, every time)
api-image:
	docker build -t charge-api ./backend

api-run:
	docker run --rm -p 8080:8080 -e PORT=8080 charge-api

# Needs: gcloud auth login (done by you) + PROJECT=<id>
deploy-api:
	gcloud run deploy charge-api --source ./backend --project $(PROJECT) --region europe-west2 \
	  --allow-unauthenticated --min-instances=1 --cpu=2 --memory=2Gi --cpu-boost \
	  --timeout=30s --concurrency=10

deploy-web:
	cd frontend && npx -y vercel@latest --prod --yes
