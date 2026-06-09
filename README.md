# Backend Engineering Technical Exercise

This bundle contains everything you need to start.

## Contents

- **`backend-engineer-exercise.pdf`** — the assignment. Read this first.
- **`docker-compose.yml`** + **`mosquitto.conf`** + **`worker/`** — the MQTT broker
  and the worker stub we ship. You boot these with `docker compose up -d`.
- **`data/seed.json`** — three users with API tokens, nine assets, the operation
  enum. Use these tokens for authenticated requests.
- **`verify.py`** — a self-assessment integration test harness. Run it after your
  service is up and it will report PASS / FAIL across ~23 scenarios covering
  every requirement in the spec.

## Quick start

1. Read `backend-engineer-exercise.pdf` end to end.
2. **Extract this bundle to a normal workspace path** (your home directory, project dir,
   or `~/Desktop`) — **not** `/tmp/`. On macOS, Docker Desktop will refuse to bind-mount
   `mosquitto.conf` from `/tmp/` and the broker won't start. Linux is unaffected.
3. Boot the broker + worker:
   ```bash
   docker compose up -d
   docker compose logs -f worker          # optional: watch the worker
   ```
4. Build your service (any HTTP framework, any database, your choice of layout).
5. Start your service so it listens on `http://localhost:8000`.
6. Verify your implementation:
   ```bash
   pip install httpx 'python-socketio[asyncio_client]'
   python3 verify.py
   ```

## How we evaluate

Primary check is **the output of `verify.py`** run against your service. The
target is `23/23 scenarios passed`. Submissions that fail one or two scenarios
will be evaluated case-by-case based on which scenarios failed and how close
they came; submissions that fail many scenarios will not advance.

We also read the code: see `§9 Evaluation Criteria` in the PDF for the full
rubric.

## Submission

Per `§8` of the PDF: source code + README + Makefile + sample `verify.py`
output, sent to the addresses on the cover page.
