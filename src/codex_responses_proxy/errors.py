"""Failure vocabulary shared by installation and native service boundaries."""

from __future__ import annotations


class ProductError(RuntimeError):
    """Report one bounded public product failure with a precise next action."""

    code = "product_error"

    def __init__(self, message: str, *, next_command: str) -> None:
        """Bind one public message to one executable next command."""

        super().__init__(message)
        self.next_command = next_command


class UnsupportedPlatformError(ProductError):
    """Report that no service adapter exists for the current operating system."""

    code = "unsupported_platform"

    def __init__(self, message: str) -> None:
        """Describe the unsupported host and direct users to public help."""

        super().__init__(message, next_command="codex-responses-proxy --help")


class InstallError(ProductError):
    """Report a fail-closed installation, route, or lifecycle contract violation."""

    code = "lifecycle_error"

    def __init__(
        self,
        message: str,
        *,
        next_command: str = "codex-responses-proxy doctor",
    ) -> None:
        """Describe one lifecycle failure and its safest next command."""

        super().__init__(message, next_command=next_command)


class InstallInputError(InstallError):
    """Report that release installation input is absent or unverifiable."""

    code = "install_input_invalid"

    def __init__(self, message: str) -> None:
        """Direct invalid release inputs to the installation contract."""

        super().__init__(message, next_command="codex-responses-proxy install --help")


class NotInstalledError(InstallError):
    """Report that an operation requires an installed product."""

    code = "not_installed"

    def __init__(self, message: str = "Codex Responses Proxy is not installed") -> None:
        """Direct an operation that needs an installation to install help."""

        super().__init__(message, next_command="codex-responses-proxy install --help")


class RecoveryRequiredError(InstallError):
    """Report that a valid retained transaction must be recovered first."""

    code = "recovery_required"

    def __init__(self, message: str) -> None:
        """Direct a blocked mutation to the exact recovery command."""

        super().__init__(message, next_command="codex-responses-proxy recover")


class RecoveryStateError(InstallError):
    """Report retained transaction evidence that cannot be changed safely."""

    code = "recovery_state_invalid"

    def __init__(self, message: str) -> None:
        """Direct unverifiable recovery evidence to read-only status."""

        super().__init__(message, next_command="codex-responses-proxy status --json")


class ProductAssemblyError(ProductError):
    """Report that a released executable is missing an internal product component."""

    code = "product_assembly_invalid"

    def __init__(self, message: str) -> None:
        """Direct an incomplete executable to verified installation inputs."""

        super().__init__(
            message,
            next_command="codex-responses-proxy install --help",
        )


class ManualStartRequiredError(ProductError):
    """Report that durable service persistence could not be established."""

    code = "manual_start_required"

    def __init__(self, message: str) -> None:
        """Direct a host without durable supervision to observed status."""

        super().__init__(message, next_command="codex-responses-proxy status")
