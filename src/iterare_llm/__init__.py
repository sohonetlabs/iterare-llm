from importlib.metadata import version, PackageNotFoundError

# Read version from package metadata (injected by hatchling during build)
try:
    __version__ = version("iterare-llm")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0-dev"
