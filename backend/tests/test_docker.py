import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_dockerfile_builds():
    result = subprocess.run(
        ["docker", "build", "-t", "python-server-test", "-f", "Dockerfile", "."],
        capture_output=True, text=True, cwd=ROOT, timeout=180,
    )
    assert result.returncode == 0, f"Docker build failed:\n{result.stderr[-2000:]}"


def test_docker_compose_validate(tmp_path):
    env_file = ROOT / ".env"
    existed = env_file.exists()
    if not existed:
        env_file.write_text("APP_NAME=python-server\nAPP_TAG=test\n")
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.yml", "config"],
            capture_output=True, text=True, cwd=ROOT,
        )
        assert result.returncode == 0, f"docker compose config failed:\n{result.stderr}"
    finally:
        if not existed:
            env_file.unlink()


def test_docker_image_starts():
    result = subprocess.run(
        ["docker", "run", "--rm", "python-server-test", "uv", "run", "python", "-c",
         "from app.main import app; print(app.title)"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"Container start failed:\n{result.stderr}"
    assert "flowchart-toolbox" in result.stdout
