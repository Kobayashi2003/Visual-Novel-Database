# Services

The layer that carries an application's work. An application that runs it on
Celery may name that layer `tasks/`.

## 1. Every service

- Know nothing about HTTP: no request, no status code, no response.
- Keep a service independent of its peers where you reasonably can.

## 2. Services on Celery

- Keep every task callable synchronously.
- Keep arguments and return values JSON-serialisable.
- Read whatever a task acts on when the task runs, not when it is queued.
