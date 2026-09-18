FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libxml2-dev libxslt1-dev curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
# ProbLog may need to fetch/compile its knowledge-compilation binaries.
# Do it at BUILD time, never at request time, and fail the build if ProbLog can't evaluate.
RUN problog install || true
RUN python -c "from problog.program import PrologString; \
from problog import get_evaluatable; \
print(get_evaluatable().create_from(PrologString('0.5::a. query(a).')).evaluate())"
COPY . .
# Smoke-test OUR model too (flexible probabilities, negation, explain) so a bad rule fails the build.
RUN python -c "from reasoner import engine; engine.warm(); \
from app.day import plan_day; r = plan_day('margaret', at='08:00'); \
assert r['cards'][0]['state'] == 'ok', r['cards'][0]; print('model ok', r['timings_ms']['total'], 'ms')"
# Cloud Run injects $PORT (8080). Binding to 8000 is the #1 Cloud Run failure.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
