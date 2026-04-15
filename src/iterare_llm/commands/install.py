"""Install command for setting up global config directory."""

from pathlib import Path

import typer

from iterare_llm.logging import get_logger
from iterare_llm.paths import get_app_config_dir, get_logs_dir, get_tmp_dir

logger = get_logger(__name__)


def create_app_directories() -> tuple[Path, Path, Path]:
    """
    Create application directories.

    Creates:
    - Config directory for .credentials.json and .claude.json
    - Logs directory for future logging
    - Tmp directory for temporary files like domains file

    Returns
    -------
    tuple[Path, Path, Path]
        Tuple of (config_dir, logs_dir, tmp_dir)

    Raises
    ------
    OSError
        If unable to create directories
    PermissionError
        If insufficient permissions to create directories
    """
    config_dir = get_app_config_dir()
    logs_dir = get_logs_dir()
    tmp_dir = get_tmp_dir()

    logger.debug(f"Creating config directory: {config_dir}")
    logger.debug(f"Creating logs directory: {logs_dir}")
    logger.debug(f"Creating tmp directory: {tmp_dir}")

    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Successfully created application directories")
        return config_dir, logs_dir, tmp_dir
    except PermissionError as e:
        logger.error(f"Permission denied while creating directories: {e}")
        raise PermissionError(
            f"Permission denied: Unable to create application directories. "
            f"Check your permissions for {config_dir.parent}"
        ) from e
    except OSError as e:
        logger.error(f"Error creating directories: {e}")
        raise OSError(f"Failed to create application directories: {e}") from e


def install() -> None:
    """
    Install iterare by creating global config directory.

    Creates the following directories:
    - Config directory: Stores .credentials.json and .claude.json
    - Logs directory: Will be used for application logs (future feature)
    - Tmp directory: Used for temporary files like firewall domains

    The config directory should contain:
    - .credentials.json: Claude API credentials
    - .claude.json: Claude session configuration

    After running install, update your .iterare/config.toml to point to
    the config directory.
    """
    try:
        logger.info("Starting installation")

        config_dir, logs_dir, tmp_dir = create_app_directories()

        typer.echo("Installation complete!")
        typer.echo("\nCreated directories:")
        typer.echo(f"  Config: {config_dir}")
        typer.echo(f"  Logs:   {logs_dir}")
        typer.echo(f"  Tmp:    {tmp_dir}")
        typer.echo(
            f"\nNext steps:\n"
            f"  1. Copy your Claude credentials to {config_dir}/\n"
            f"     - .credentials.json\n"
            f"     - .claude.json\n"
            f"     Note. Claude uses the keychain on macOS for credentials"
            f"           Please use the credential command to launch an interactive"
            f"           session to fetch those files."
            f"  2. Update .iterare/config.toml to use:\n"
            f'     credentials_path = "{config_dir}"\n'
        )

    except PermissionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except OSError as e:
        typer.echo(f"Error during installation: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        logger.exception("Unexpected error during installation")
        typer.echo(f"Error during installation: {e}", err=True)
        raise typer.Exit(1)
