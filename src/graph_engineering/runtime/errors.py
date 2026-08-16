"""Runtime-specific failures that do not change the public protocol surface."""


class RuntimeInvariantError(RuntimeError):
    """Raised when persisted state violates the deterministic state machine."""


class TransitionError(RuntimeInvariantError):
    """Raised when a requested state transition is not allowed."""


class RecoveryError(RuntimeInvariantError):
    """Raised when a persisted run cannot be safely recovered."""
