"""Controlled errors raised by the Sprint 1 pipeline."""


class PipelineError(Exception):
    """Base error with the information required by the API and Firestore."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        stage: str,
        http_status: int,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.stage = stage
        self.http_status = http_status
        self.retryable = retryable


class PipelineValidationError(PipelineError):
    """The user's request is invalid and should not be retried unchanged."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "INVALID_TEXT",
        http_status: int = 422,
    ) -> None:
        super().__init__(
            message,
            error_code=error_code,
            stage="input_preparation",
            http_status=http_status,
            retryable=False,
        )


class PipelineComponentError(PipelineError):
    """A required analysis component failed or is not available."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        stage: str,
        retryable: bool = True,
        http_status: int = 503,
    ) -> None:
        super().__init__(
            message,
            error_code=error_code,
            stage=stage,
            http_status=http_status,
            retryable=retryable,
        )


class PipelineContractError(PipelineError):
    """A component returned data that violates the shared interface."""

    def __init__(self, message: str, *, stage: str) -> None:
        super().__init__(
            message,
            error_code="PIPELINE_CONTRACT_ERROR",
            stage=stage,
            http_status=500,
            retryable=False,
        )


class PipelinePersistenceError(PipelineError):
    """The completed result could not be stored safely."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="RESULT_STORAGE_FAILED",
            stage="result_storage",
            http_status=503,
            retryable=True,
        )

