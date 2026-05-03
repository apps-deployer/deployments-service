# Deployments Service

FastAPI и Celery-сервис для deployment runs, build jobs, deploy jobs, сборки container images, применения Kubernetes manifests и хранения deployment artifacts.

## Компоненты

- API container из `Dockerfile.api`.
- Worker container из `Dockerfile.worker`.
- Celery build worker queue: `build`.
- Celery deploy worker queue: `deploy`.
- Celery beat process для cleanup зависших jobs.

## Назначение

- Создает deployment runs.
- Получает project, environment, deploy config и variables из `projects-service`.
- Собирает application images через Kaniko.
- Пушит images в настроенный container registry.
- Применяет Kubernetes manifests для пользовательских приложений.
- Хранит artifact image и URL.
- Согласованно переводит build/deploy jobs в failed при ошибках.

## HTTP API

- `GET /healthz` - проверка состояния сервиса.
- Публичный API расположен под `/api/v1/deployments`.
- Внутренний API расположен под `/internal`.

Важные внутренние endpoints:

- `PUT /internal/jobs/{job_id}/status`
- `POST /internal/deployments/{run_id}/artifact`
- `PATCH /internal/deployments/{run_id}/artifact`
- `POST /internal/cleanup`

## Конфигурация

Настройки читаются из переменных окружения с префиксом `DEPLOY_`. Для вложенных полей используется разделитель `__`.

Основные переменные:

- `DEPLOY_DB__HOST`
- `DEPLOY_DB__PORT`
- `DEPLOY_DB__USER`
- `DEPLOY_DB__NAME`
- `DEPLOY_DB__PASSWORD`
- `DEPLOY_REDIS__URL`
- `DEPLOY_GRPC__PROJECTS_SERVICE_ADDR`
- `DEPLOY_SERVER__PORT`
- `DEPLOY_SERVER__SERVICE_URL`
- `DEPLOY_SERVER__FRONTEND_URL`
- `DEPLOY_REGISTRY__URL`
- `DEPLOY_REGISTRY__USER_APPS_URL`
- `DEPLOY_DEPLOY__BASE_DOMAIN`
- `DEPLOY_AUTH__JWT_SECRET`
- `DB_ADMIN_URL` - используется Alembic-миграциями.
- `K8S_NAMESPACE` - namespace для Kaniko jobs, по умолчанию `apps-deployer`.

## Имена образов

Имя образа формируется из registry, project id, project slug и commit SHA:

```text
<registry>/<project-id-prefix>/<project-slug>:<commit-sha>
```

Так не возникает коллизий между разными пользователями или проектами с одинаковым отображаемым именем.

## Локальный запуск

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Локальный запуск workers:

```bash
celery -A src.workers.celery_app worker -Q build -l info
celery -A src.workers.celery_app worker -Q deploy -l info
celery -A src.workers.celery_app beat -l info
```

Запуск тестов:

```bash
pytest -q
```

## Миграции

```bash
alembic upgrade head
```

## Деплой

Helm chart находится в `charts/deployments-service`. Он деплоит API, workers, beat process, secrets, service и ingress.
