class BusinessException(Exception):
    def __init__(self, code: int = 500, message: str = "操作失败"):
        self.code = code
        self.message = message
