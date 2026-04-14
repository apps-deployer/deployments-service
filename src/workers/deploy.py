import logging
import subprocess
import tempfile
from pathlib import Path
from string import Template

import httpx

from src.workers.celery_app import celery, settings

logger = logging.getLogger(__name__)

_DEPLOYMENT_TEMPLATE = Template("""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: $app_name
  namespace: $namespace
  labels:
    app: $app_name
spec:
  replicas: 1
  selector:
    matchLabels:
      app: $app_name
  template:
    metadata:
      labels:
        app: $app_name
    spec:
      containers:
        - name: $app_name
          image: $image
          ports:
            - containerPort: 8080
          env:
$env_block
""")

_SERVICE_TEMPLATE = Template("""\
apiVersion: v1
kind: Service
metadata:
  name: $app_name
  namespace: $namespace
spec:
  selector:
    app: $app_name
  ports:
    - port: 80
      targetPort: 8080
""")

_NAMESPACE_TEMPLATE = Template("""\
apiVersion: v1
kind: Namespace
metadata:
  name: $namespace
""")

_INGRESS_TEMPLATE = Template("""\
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: $app_name
  namespace: $namespace
  annotations:
    cert-manager.io/cluster-issuer: yc-clusterissuer
spec:
  ingressClassName: traefik
  tls:
    - hosts:
        - $domain
      secretName: $app_name-tls
  rules:
    - host: $domain
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: $app_name
                port:
                  number: 80
""")


def _callback(path: str, **json_body):
    url = f"{settings.server.base_url}{path}"
    resp = httpx.put(url, json=json_body)
    resp.raise_for_status()


def _render_env_block(env_vars: list[dict]) -> str:
    if not env_vars:
        return "            []"
    lines = []
    for var in env_vars:
        lines.append(f"            - name: {var['key']}")
        lines.append(f'              value: "{var["value"]}"')
    return "\n".join(lines)


def _generate_manifests(
    app_name: str,
    namespace: str,
    image: str,
    domain: str,
    env_vars: list[dict],
    dest: Path,
):
    env_block = _render_env_block(env_vars)
    ctx = dict(
        app_name=app_name,
        namespace=namespace,
        image=image,
        domain=domain,
        env_block=env_block,
    )

    manifests = [
        _NAMESPACE_TEMPLATE.substitute(ctx),
        _DEPLOYMENT_TEMPLATE.substitute(ctx),
        _SERVICE_TEMPLATE.substitute(ctx),
    ]
    if domain:
        manifests.append(_INGRESS_TEMPLATE.substitute(ctx))

    manifest_path = dest / "manifest.yaml"
    manifest_path.write_text("---\n".join(manifests))
    return manifest_path


def _kubectl_apply(manifest_path: Path):
    subprocess.run(
        ["kubectl", "apply", "-f", str(manifest_path)],
        check=True,
        capture_output=True,
    )


@celery.task(name="src.workers.deploy.run_deploy")
def run_deploy(
    deployment_run_id: str,
    deploy_job_id: str,
    image: str,
    project_name: str,
    env_name: str,
    domain_name: str,
    env_vars: list[dict],
):
    try:
        _callback(f"/internal/jobs/{deploy_job_id}/status", status="running")
        app_name = f"{project_name}-{env_name}"
        namespace = project_name

        if not domain_name and settings.deploy.base_domain:
            domain_name = f"{app_name}.{settings.deploy.base_domain}"

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            manifest_path = _generate_manifests(
                app_name=app_name,
                namespace=namespace,
                image=image,
                domain=domain_name,
                env_vars=env_vars,
                dest=dest,
            )
            _kubectl_apply(manifest_path)

        _callback(f"/internal/jobs/{deploy_job_id}/status", status="success")

    except Exception as exc:
        logger.exception("Deploy failed for run %s", deployment_run_id)
        _callback(
            f"/internal/jobs/{deploy_job_id}/status",
            status="failed",
            error=str(exc),
        )
        raise
