"""Logging configuration for iterare."""

import logging
import sys


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging for the application.

    Parameters
    ----------
    verbose : bool, optional
        If True, set logging level to DEBUG. Otherwise, set to INFO.
        Default is False.

    Notes
    -----
    Logging output is sent to stderr with a timestamp, logger name, level,
    and message.
    """
    level = logging.DEBUG if verbose else logging.INFO

    # Configure root logger
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stderr)],
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.

    Parameters
    ----------
    name : str
        Name of the logger, typically __name__ of the module.

    Returns
    -------
    logging.Logger
        Configured logger instance.

    Examples
    --------
    >>> logger = get_logger(__name__)
    >>> logger.info("This is an info message")
    """
    return logging.getLogger(name)
