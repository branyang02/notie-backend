import os
import pytest
from unittest.mock import patch, Mock

from piston import execute_code, _parse_response, ExecutionResult, LANGUAGE_VERSIONS


class TestParseResponse:
    """Unit tests for _parse_response — no network needed."""

    def test_successful_run(self):
        data = {"run": {"stdout": "Hello\n", "stderr": "", "code": 0}}
        result = _parse_response(data)
        assert result.stdout == "Hello\n"
        assert result.success
        assert result.compile_stderr is None
        assert result.error_output == ""

    def test_runtime_error(self):
        data = {"run": {"stdout": "", "stderr": "NameError: name 'x'", "code": 1}}
        result = _parse_response(data)
        assert not result.success
        assert result.error_output == "NameError: name 'x'"
        assert result.compile_stderr is None

    def test_compile_error_takes_priority(self):
        data = {
            "compile": {"stdout": "", "stderr": "undefined reference to main", "code": 1},
            "run": {"stdout": "", "stderr": "", "code": 0},
        }
        result = _parse_response(data)
        assert result.compile_stderr == "undefined reference to main"
        assert result.error_output == "undefined reference to main"

    def test_no_compile_block(self):
        data = {"run": {"stdout": "ok", "stderr": "", "code": 0}}
        result = _parse_response(data)
        assert result.compile_stderr is None

    def test_compile_block_with_warnings_only(self):
        # compile.code == 0 and stderr non-empty = warning, still treated as error
        data = {
            "compile": {"stdout": "", "stderr": "warning: unused variable", "code": 0},
            "run": {"stdout": "ok", "stderr": "", "code": 0},
        }
        result = _parse_response(data)
        assert result.compile_stderr == "warning: unused variable"


class TestExecuteCode:
    @patch("piston.requests.post")
    def test_correct_payload_shape(self, mock_post):
        mock_resp = Mock()
        mock_resp.json.return_value = {"run": {"stdout": "2\n", "stderr": "", "code": 0}}
        mock_resp.raise_for_status = Mock()
        mock_post.return_value = mock_resp

        execute_code("python", "print(1+1)")

        call_json = mock_post.call_args.kwargs["json"]
        assert call_json["language"] == "python"
        assert call_json["version"] == LANGUAGE_VERSIONS["python"]
        assert call_json["files"][0]["content"] == "print(1+1)"

    @patch("piston.requests.post")
    def test_returns_execution_result(self, mock_post):
        mock_resp = Mock()
        mock_resp.json.return_value = {"run": {"stdout": "hi", "stderr": "", "code": 0}}
        mock_resp.raise_for_status = Mock()
        mock_post.return_value = mock_resp

        result = execute_code("python", "print('hi')")

        assert isinstance(result, ExecutionResult)
        assert result.stdout == "hi"

    def test_unsupported_language_raises(self):
        with pytest.raises(ValueError, match="Unsupported language"):
            execute_code("brainfuck", "+++")

    @patch("piston.requests.post")
    def test_http_error_propagates(self, mock_post):
        import requests as req
        mock_resp = Mock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("500 Server Error")
        mock_post.return_value = mock_resp

        with pytest.raises(req.HTTPError):
            execute_code("python", "print('x')")


@pytest.mark.skipif(
    not os.getenv("PISTON_URL"),
    reason="Requires running Piston instance (set PISTON_URL env var)",
)
class TestLiveExecution:
    def test_python_hello_world(self):
        result = execute_code("python", "print('hello')")
        assert result.stdout.strip() == "hello"
        assert result.success

    def test_c_hello_world(self):
        result = execute_code(
            "c", '#include<stdio.h>\nint main(){printf("hi");return 0;}'
        )
        assert result.stdout.strip() == "hi"
        assert result.success

    def test_cpp_hello_world(self):
        result = execute_code(
            "cpp",
            '#include<iostream>\nint main(){std::cout<<"hi";return 0;}',
        )
        assert result.stdout.strip() == "hi"
        assert result.success

    def test_c_compile_error(self):
        result = execute_code("c", "this is not c code")
        assert not result.success
        assert result.compile_stderr

    def test_python_runtime_error(self):
        result = execute_code("python", "raise ValueError('oops')")
        assert not result.success
        assert "ValueError" in result.stderr
