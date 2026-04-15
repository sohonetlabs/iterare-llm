"""Fetch Claude Code credentials via interactive Docker session."""

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

import typer

from iterare_llm.config import DEFAULT_DOCKER_IMAGE
from iterare_llm.docker import get_docker_client, get_image_user, image_exists
from iterare_llm.exceptions import DockerError, ImageNotFoundError, IterareError
from iterare_llm.logging import get_logger
from iterare_llm.paths import get_app_config_dir, get_tmp_dir

logger = get_logger(__name__)


@contextmanager
def credentials_temp_dir():
    """
    Context manager for a temporary directory used during credential capture.

    Creates a temp dir under the application cache directory with a
    `.claude/` subdirectory and an empty `.claude.json` file. Permissions
    are set to 0o777 so the container's `node` user (UID 1000) can write.
    The directory is cleaned up on exit regardless of success or failure.

    Yields
    ------
    Path
        Path to the temporary directory
    """
    cache_dir = get_tmp_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    temp_dir = Path(tempfile.mkdtemp(prefix="credentials-", dir=cache_dir))
    logger.debug(f"Created temp directory: {temp_dir}")

    # Create .claude/ subdirectory
    claude_dir = temp_dir / ".claude"
    claude_dir.mkdir()

    # Write valid empty JSON so Docker mounts it as a file (not a directory)
    # and Claude Code can parse it without error on startup
    claude_json = temp_dir / ".claude.json"
    claude_json.write_text("{}")

    # Set permissions so container user can write
    temp_dir.chmod(0o777)
    claude_dir.chmod(0o777)

    logger.debug("Prepared temp directory with .claude/ and .claude.json")
    try:
        yield temp_dir
    finally:
        try:
            shutil.rmtree(temp_dir)
            logger.debug(f"Cleaned up temp directory: {temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up temp directory {temp_dir}: {e}")


def build_credentials_docker_command(
    image_name: str, temp_dir: Path, container_user: str
) -> list[str]:
    """
    Build docker run command for credential capture.

    Uses ``--entrypoint claude`` to bypass the normal entrypoint (which sets up
    firewall and expects a prompt). No ``--cap-add NET_ADMIN`` is needed since
    the firewall is not configured.

    Parameters
    ----------
    image_name : str
        Docker image name
    temp_dir : Path
        Path to the temporary directory with `.claude/` and `.claude.json`
    container_user : str
        User the container runs as (determines home directory)

    Returns
    -------
    list[str]
        Docker run command as list of arguments
    """
    if container_user == "root":
        home_dir = "/root"
    else:
        home_dir = f"/home/{container_user}"

    claude_dir_mount = f"{home_dir}/.claude"
    claude_json_mount = f"{home_dir}/.claude.json"

    cmd = [
        "docker",
        "run",
        "-it",
        "--rm",
        "--entrypoint",
        "claude",
        "-v",
        f"{temp_dir / '.claude'}:{claude_dir_mount}:rw",
        "-v",
        f"{temp_dir / '.claude.json'}:{claude_json_mount}:rw",
        image_name,
    ]

    logger.debug(f"Built credentials docker command for user '{container_user}'")
    return cmd


def extract_credentials(temp_dir: Path, dest_dir: Path) -> tuple[Path, Path]:
    """
    Extract credentials from temp directory to destination.

    Parameters
    ----------
    temp_dir : Path
        Temporary directory containing captured credentials
    dest_dir : Path
        Destination directory for credential files

    Returns
    -------
    tuple[Path, Path]
        Paths to the copied credentials file and config file

    Raises
    ------
    FileNotFoundError
        If login was not completed (credentials files missing or empty)
    """
    credentials_file = temp_dir / ".claude" / ".credentials.json"
    claude_json = temp_dir / ".claude.json"

    if not credentials_file.exists():
        raise FileNotFoundError("Credentials file not found. Login was not completed.")

    if not claude_json.exists() or claude_json.read_text().strip() in ("", "{}"):
        raise FileNotFoundError(
            "Claude config file not found or empty. Login was not completed."
        )

    # Create destination directory if needed
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Copy credentials files
    dest_credentials = dest_dir / ".credentials.json"
    dest_claude_json = dest_dir / ".claude.json"

    shutil.copy2(credentials_file, dest_credentials)
    shutil.copy2(claude_json, dest_claude_json)

    logger.info(f"Extracted credentials to {dest_dir}")
    return dest_credentials, dest_claude_json


def check_existing_credentials(config_dir: Path) -> bool:
    """
    Check if credentials already exist.

    Parameters
    ----------
    config_dir : Path
        Configuration directory to check

    Returns
    -------
    bool
        True if both `.credentials.json` and `.claude.json` exist
    """
    credentials_file = config_dir / ".credentials.json"
    claude_json = config_dir / ".claude.json"
    return credentials_file.exists() and claude_json.exists()


def credentials(
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing credentials"
    ),
    image: str = typer.Option(
        DEFAULT_DOCKER_IMAGE, "--image", "-i", help="Docker image to use"
    ),
) -> None:
    """
    Fetch Claude Code credentials via interactive Docker session.

    Launches a minimal Docker container with Claude Code so you can log in.
    After login, credential files are extracted to the iterare config directory.

    Examples
    --------
    First-time setup:
        iterare credentials

    Re-authenticate (overwrite existing):
        iterare credentials --force

    Use a custom Docker image:
        iterare credentials --image my-image:latest
    """
    logger = get_logger(__name__)
    logger.info("Credentials command invoked")

    try:
        # 1. Determine destination directory
        config_dir = get_app_config_dir()
        logger.debug(f"Credentials destination: {config_dir}")

        # 2. Check for existing credentials
        if not force and check_existing_credentials(config_dir):
            typer.echo("Credentials already exist.")
            typer.echo(f"  Location: {config_dir}")
            typer.echo("\nUse --force to overwrite existing credentials.")
            return

        # 3. Connect to Docker and validate image
        logger.info("Connecting to Docker")
        client = get_docker_client()
        if not image_exists(client, image):
            raise ImageNotFoundError(
                f"Docker image '{image}' not found. "
                "Please build the Docker image first."
            )

        # 4. Get container user for home directory mapping
        container_user = get_image_user(client, image)
        logger.info(f"Container will run as user: {container_user}")

        # 5. Run in temp directory context
        with credentials_temp_dir() as temp_dir:
            logger.info(f"Prepared temp directory: {temp_dir}")

            # 6. Build docker command
            docker_cmd = build_credentials_docker_command(image, temp_dir, container_user)

            # 7. Display instructions
            typer.echo("\nStarting Claude Code for authentication...")
            typer.echo("Log in to Claude, then exit (type /exit or Ctrl+D).\n")

            # 8. Run interactive container
            logger.info(f"Running: {' '.join(docker_cmd)}")
            result = subprocess.run(docker_cmd)
            logger.info(f"Container exited with code: {result.returncode}")

            # 9. Extract credentials
            dest_credentials, dest_claude_json = extract_credentials(temp_dir, config_dir)

        # 10. Display success
        typer.echo("\nCredentials saved successfully!")
        typer.echo(f"  Credentials: {dest_credentials}")
        typer.echo(f"  Config:      {dest_claude_json}")

    except KeyboardInterrupt:
        typer.echo("\n\nAuthentication interrupted.", err=True)
        raise typer.Exit(130)

    except FileNotFoundError as e:
        typer.echo(f"\nError: {e}", err=True)
        typer.echo(
            "Please log in to Claude Code before exiting the session.",
            err=True,
        )
        raise typer.Exit(1)

    except ImageNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        typer.echo(
            "\nTo build the Docker image, run:\n  make build",
            err=True,
        )
        raise typer.Exit(1)

    except DockerError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    except IterareError as e:
        typer.echo(f"Error: {e}", err=True)
        logger.exception("Credentials command failed")
        raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error during credentials command")
        raise typer.Exit(1)
