from app.exceptions.business import BusinessException
from app.exceptions.handlers import _validation_error_code


class TestBusinessException:
    def test_default_values(self):
        exc = BusinessException()
        assert exc.code == 500
        assert exc.message == "操作失败"

    def test_custom_values(self):
        exc = BusinessException(code=404, message="商品不存在")
        assert exc.code == 404
        assert exc.message == "商品不存在"

    def test_is_exception(self):
        exc = BusinessException()
        assert isinstance(exc, Exception)

    def test_code_only(self):
        exc = BusinessException(code=1001)
        assert exc.code == 1001
        assert exc.message == "操作失败"

    def test_message_only(self):
        exc = BusinessException(message="库存不足")
        assert exc.code == 500
        assert exc.message == "库存不足"

    def test_error_code(self):
        exc = BusinessException(code=400, message="流程描述为空", error_code="PROMPT_EMPTY")
        assert exc.error_code == "PROMPT_EMPTY"


def test_prompt_validation_error_code_mapping():
    assert _validation_error_code([{"loc": ("body", "prompt"), "type": "string_too_long"}]) == "PROMPT_TOO_LONG"
    assert _validation_error_code([{"loc": ("body", "prompt"), "type": "value_error"}]) == "PROMPT_EMPTY"
    assert _validation_error_code([{"loc": ("body", "prompt"), "type": "string_type"}]) is None
