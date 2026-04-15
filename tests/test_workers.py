"""Tests for worker utility functions."""
import pytest

from src.workers.deploy import _sanitize_name, _render_env_block
from src.workers.build import _generate_dockerfile, _job_name


# ── _sanitize_name ────────────────────────────────────────────────────────────

def test_sanitize_name_lowercase():
    assert _sanitize_name("MyProject") == "myproject"


def test_sanitize_name_spaces_to_dashes():
    assert _sanitize_name("my project") == "my-project"


def test_sanitize_name_special_chars():
    assert _sanitize_name("My_Project.v2!") == "my-project-v2"


def test_sanitize_name_strips_leading_trailing_dashes():
    assert _sanitize_name("--my-app--") == "my-app"


def test_sanitize_name_truncates_at_63():
    long = "a" * 100
    result = _sanitize_name(long)
    assert len(result) == 63


def test_sanitize_name_combined():
    assert _sanitize_name("My Project-ENV") == "my-project-env"


# ── _job_name ─────────────────────────────────────────────────────────────────

def test_job_name_no_trailing_dash():
    # UUID position 24 falls on a dash — result must not end with one
    job_id = "019d925e-f5c9-7d42-9e58-84dee211a1d6"
    name = _job_name(job_id)
    assert not name.endswith("-")
    assert name.startswith("kaniko-")


def test_job_name_only_alphanumeric_and_dash():
    import re
    job_id = "019d925e-f5c9-7d42-9e58-84dee211a1d6"
    name = _job_name(job_id)
    assert re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$', name)


# ── _render_env_block ─────────────────────────────────────────────────────────

def test_render_env_block_empty():
    result = _render_env_block([])
    assert "[]" in result


def test_render_env_block_single():
    result = _render_env_block([{"key": "FOO", "value": "bar"}])
    assert "FOO" in result
    assert "bar" in result


def test_render_env_block_multiple():
    vars_ = [{"key": "A", "value": "1"}, {"key": "B", "value": "2"}]
    result = _render_env_block(vars_)
    assert "A" in result
    assert "B" in result


# ── _generate_dockerfile ──────────────────────────────────────────────────────

def test_generate_dockerfile_with_run_cmd():
    cfg = {
        "base_image": "python:3.12-alpine",
        "root_dir": ".",
        "output_dir": ".",
        "install_cmd": "pip install -r requirements.txt",
        "build_cmd": "",
        "run_cmd": "python main.py",
    }
    df = _generate_dockerfile(cfg)
    assert "FROM python:3.12-alpine AS build" in df
    assert "pip install -r requirements.txt" in df
    assert "CMD python main.py" in df
    # second stage uses same base image when run_cmd is set
    assert df.count("FROM python:3.12-alpine") == 2


def test_generate_dockerfile_nodejs_run_cmd_copies_full_app():
    # Node.js template: output_dir=dist, run_cmd set — second stage must copy full /app
    cfg = {
        "base_image": "node:20-alpine",
        "root_dir": ".",
        "output_dir": "dist",
        "install_cmd": "npm install",
        "build_cmd": "npm run build",
        "run_cmd": "node dist/index.js",
    }
    df = _generate_dockerfile(cfg)
    assert "FROM node:20-alpine AS build" in df
    assert "COPY --from=build /app ." in df
    assert "CMD node dist/index.js" in df
    # must NOT use nginx
    assert "nginx" not in df
    # must NOT copy only the dist subfolder
    assert "COPY --from=build /app/dist" not in df


def test_generate_dockerfile_static_uses_nginx():
    cfg = {
        "base_image": "node:20-alpine",
        "root_dir": ".",
        "output_dir": "dist",
        "install_cmd": "npm install",
        "build_cmd": "npm run build",
        "run_cmd": "",
    }
    df = _generate_dockerfile(cfg)
    assert "FROM node:20-alpine AS build" in df
    assert "FROM nginx:alpine" in df
    assert "COPY --from=build /app/dist ." in df
    assert "WORKDIR /usr/share/nginx/html" in df


def test_generate_dockerfile_no_build_cmd():
    cfg = {
        "base_image": "python:3.12",
        "root_dir": ".",
        "output_dir": ".",
        "install_cmd": "",
        "build_cmd": "",
        "run_cmd": "python app.py",
    }
    df = _generate_dockerfile(cfg)
    assert "RUN" not in df
