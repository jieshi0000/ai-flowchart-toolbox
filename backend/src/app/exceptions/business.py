class BusinessException(Exception):
    def __init__(
        self,
        code: int = 500,
        message: str = "操作失败",
        error_code: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.error_code = error_code
