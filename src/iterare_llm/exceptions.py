class IterareError(Exception):
    """Base exception for iterare."""

    pass


# Prompt exceptions
class PromptError(IterareError):
    """Base exception for prompt operations."""

    pass


class PromptNotFoundError(PromptError):
    """Prompt file not found."""

    pass


# Git exceptions
class GitError(IterareError):
    """Base exception for git operations."""

    pass


class NotGitRepositoryError(GitError):
    """Not a git repository."""

    pass


class WorktreeExistsError(GitError):
    """Worktree already exists."""

    pass


# Docker exceptions
class DockerError(IterareError):
    """Base exception for Docker operations."""

    pass


class ImageNotFoundError(DockerError):
    """Docker image not found."""

    pass


class ContainerAlreadyRunningError(DockerError):
    """Container already running."""

    pass


class NetworkNotFoundError(DockerError):
    """Docker network not found."""

    pass


# Conversation exceptions
class ConversationError(IterareError):
    """Base exception for conversation resume/continue operations."""

    pass


class ConversationNotFoundError(ConversationError):
    """Requested conversation does not exist in the project's store."""

    pass


class NoConversationsError(ConversationError):
    """No conversations exist for the project to continue or resume."""

    pass


# Config exceptions
class ConfigError(IterareError):
    """Base exception for configuration issues."""

    pass


class CredentialsNotFoundError(ConfigError):
    """Claude credentials not found."""

    pass
