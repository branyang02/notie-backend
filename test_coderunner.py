import pytest
from unittest.mock import patch

from flask import Flask
from coderunner import run_code, _run_python, _run_generic, _split_output, MATPLOTLIB_SENTINEL, MATPLOTLIB_PREAMBLE
from piston import ExecutionResult


@pytest.fixture
def app():
    return Flask(__name__)


@pytest.fixture
def app_context(app):
    with app.app_context():
        yield


def _result(stdout="", stderr="", exit_code=0, compile_stderr=None):
    return ExecutionResult(
        stdout=stdout, stderr=stderr, exit_code=exit_code, compile_stderr=compile_stderr
    )


class TestSplitOutput:
    """Unit tests for sentinel parsing — no Flask or Piston needed."""

    def test_no_sentinel(self):
        text, image = _split_output("Hello\n")
        assert text == "Hello\n"
        assert image == ""

    def test_sentinel_stripped_from_output(self):
        text, image = _split_output(f"line1\n{MATPLOTLIB_SENTINEL}abc123\nline2\n")
        assert MATPLOTLIB_SENTINEL not in text
        assert "line1\n" in text
        assert "line2\n" in text

    def test_sentinel_base64_extracted(self):
        _, image = _split_output(f"{MATPLOTLIB_SENTINEL}abc123\n")
        assert image == "abc123"

    def test_last_sentinel_wins(self):
        _, image = _split_output(
            f"{MATPLOTLIB_SENTINEL}first\n{MATPLOTLIB_SENTINEL}second\n"
        )
        assert image == "second"

    def test_empty_stdout(self):
        text, image = _split_output("")
        assert text == ""
        assert image == ""


class TestRunCode:
    """Tests for the run_code dispatch function."""

    @patch("coderunner._run_python")
    def test_routes_python(self, mock_py, app_context):
        run_code("print('hi')", "python")
        mock_py.assert_called_once_with("print('hi')")

    @patch("coderunner._run_generic")
    def test_routes_c(self, mock_generic, app_context):
        run_code("#include<stdio.h>", "c")
        mock_generic.assert_called_once_with("#include<stdio.h>", "c")

    @patch("coderunner._run_generic")
    def test_routes_cpp(self, mock_generic, app_context):
        run_code("#include<iostream>", "cpp")
        mock_generic.assert_called_once_with("#include<iostream>", "cpp")

    @patch("coderunner._run_generic")
    def test_routes_rust(self, mock_generic, app_context):
        run_code("fn main() {}", "rust")
        mock_generic.assert_called_once_with("fn main() {}", "rust")

    @patch("coderunner._run_generic")
    def test_routes_java(self, mock_generic, app_context):
        run_code("class Main {}", "java")
        mock_generic.assert_called_once_with("class Main {}", "java")


class TestRunPython:
    @patch("coderunner.execute_code")
    def test_successful_execution(self, mock_exec, app_context):
        mock_exec.return_value = _result(stdout="Hello\n")
        data = _run_python("print('Hello')").get_json()
        assert data["output"] == "Hello\n"
        assert data["image"] == ""

    @patch("coderunner.execute_code")
    def test_runtime_error_returned_as_output(self, mock_exec, app_context):
        mock_exec.return_value = _result(stderr="NameError: x", exit_code=1)
        data = _run_python("x").get_json()
        assert "NameError" in data["output"]

    @patch("coderunner.execute_code")
    def test_matplotlib_preamble_injected_for_plt(self, mock_exec, app_context):
        mock_exec.return_value = _result(stdout="")
        _run_python("plt.show()")
        submitted = mock_exec.call_args[0][1]
        assert MATPLOTLIB_PREAMBLE in submitted

    @patch("coderunner.execute_code")
    def test_preamble_not_injected_for_plain_code(self, mock_exec, app_context):
        mock_exec.return_value = _result(stdout="2\n")
        _run_python("print(1+1)")
        submitted = mock_exec.call_args[0][1]
        assert MATPLOTLIB_PREAMBLE not in submitted

    @patch("coderunner.execute_code")
    def test_figure_sentinel_parsed(self, mock_exec, app_context):
        mock_exec.return_value = _result(
            stdout=f"some text\n{MATPLOTLIB_SENTINEL}abc123\n"
        )
        data = _run_python("plt.show()").get_json()
        assert data["image"] == "abc123"
        assert MATPLOTLIB_SENTINEL not in data["output"]
        assert "some text\n" in data["output"]

    @patch("coderunner.execute_code")
    def test_import_os_allowed(self, mock_exec, app_context):
        """Previously blocked by BLOCKED_PATTERNS; now allowed (Piston sandboxes it)."""
        mock_exec.return_value = _result(stdout="ok\n")
        _run_python("import os; print('ok')")
        assert mock_exec.called

    @patch("coderunner.execute_code")
    def test_exception_returns_500(self, mock_exec, app_context):
        import requests
        mock_exec.side_effect = requests.ConnectionError("Piston unreachable")
        response = _run_python("print('x')")
        assert response[1] == 500


class TestRunGeneric:
    @patch("coderunner.execute_code")
    def test_successful_c_execution(self, mock_exec, app_context):
        mock_exec.return_value = _result(stdout="hi")
        data = _run_generic('#include<stdio.h>\nint main(){printf("hi");}', "c").get_json()
        assert data["output"] == "hi"

    @patch("coderunner.execute_code")
    def test_compile_error_returned(self, mock_exec, app_context):
        mock_exec.return_value = _result(
            exit_code=1, compile_stderr="undefined reference to main"
        )
        data = _run_generic("bad code", "c").get_json()
        assert "undefined reference" in data["output"]

    @patch("coderunner.execute_code")
    def test_unsupported_language_returns_400(self, mock_exec, app_context):
        mock_exec.side_effect = ValueError("Unsupported language: 'brainfuck'")
        response = _run_generic("+++", "brainfuck")
        assert response[1] == 400

    @patch("coderunner.execute_code")
    def test_network_error_returns_500(self, mock_exec, app_context):
        import requests
        mock_exec.side_effect = requests.ConnectionError("unreachable")
        response = _run_generic("print('x')", "python")
        assert response[1] == 500
