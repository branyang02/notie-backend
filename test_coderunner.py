import pytest
from unittest.mock import patch, MagicMock


from flask import Flask
from coderunner import run_code, run_python, BLOCKED_PATTERNS


@pytest.fixture
def app():
    """Create a Flask app context for testing."""
    app = Flask(__name__)
    return app


@pytest.fixture
def app_context(app):
    """Provide app context for tests that need jsonify."""
    with app.app_context():
        yield


class TestBlockedPatterns:
    """Tests for the security pattern blocking in run_python."""

    def test_blocked_patterns_exist(self):
        """Verify BLOCKED_PATTERNS set contains expected dangerous patterns."""
        assert "exec" in BLOCKED_PATTERNS
        assert "eval" in BLOCKED_PATTERNS
        assert "subprocess" in BLOCKED_PATTERNS
        assert "import os" in BLOCKED_PATTERNS
        assert "__builtins__" in BLOCKED_PATTERNS

    @pytest.mark.parametrize(
        "dangerous_code",
        [
            "exec('print(1)')",
            "eval('1+1')",
            "import os",
            "from os import path",
            "import subprocess",
            "__builtins__",
            "open('file.txt')",
            "import socket",
            "getattr(obj, 'attr')",
            "globals()",
            "locals()",
        ],
    )
    def test_dangerous_code_blocked(self, app_context, dangerous_code):
        """Test that dangerous code patterns are blocked."""
        result = run_python(dangerous_code)
        data = result.get_json()
        assert "Error: Operation not allowed" in data["output"]

    def test_safe_code_allowed(self, app_context):
        """Test that safe code patterns are allowed to execute."""
        safe_code = "print(1 + 1)"
        with patch("coderunner.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "2\n"
            mock_run.return_value = mock_result

            result = run_python(safe_code)  # noqa: F841
            # Verify subprocess.run was called (code wasn't blocked)
            assert mock_run.called

    def test_case_insensitive_blocking(self, app_context):
        """Test that blocking is case-insensitive."""
        # These should all be blocked
        variants = ["EXEC('x')", "Eval('x')", "IMPORT OS", "Import Subprocess"]
        for code in variants:
            result = run_python(code)
            data = result.get_json()
            assert "Error: Operation not allowed" in data["output"], (
                f"Failed to block: {code}"
            )


class TestRunCode:
    """Tests for the run_code routing function."""

    @patch("coderunner.run_python")
    def test_routes_python_code(self, mock_run_python):
        """Test that Python code is routed to run_python."""
        mock_run_python.return_value = MagicMock()
        run_code("print('hello')", "python")
        mock_run_python.assert_called_once_with("print('hello')")

    @patch("coderunner.run_c")
    def test_routes_c_code(self, mock_run_c):
        """Test that C code is routed to run_c."""
        mock_run_c.return_value = MagicMock()
        run_code("#include <stdio.h>", "c")
        mock_run_c.assert_called_once_with("#include <stdio.h>")

    @patch("coderunner.run_any")
    def test_routes_other_languages(self, mock_run_any):
        """Test that other languages are routed to run_any."""
        mock_run_any.return_value = MagicMock()
        run_code("console.log('hi')", "javascript")
        mock_run_any.assert_called_once_with("console.log('hi')", "javascript")


class TestRunPythonExecution:
    """Tests for Python code execution behavior."""

    @patch("coderunner.subprocess.run")
    @patch("coderunner.os.path.exists", return_value=False)
    def test_successful_execution(self, mock_exists, mock_run, app_context):
        """Test successful code execution returns output."""
        mock_result = MagicMock()
        mock_result.stdout = "Hello, World!\n"
        mock_run.return_value = mock_result

        result = run_python("print('Hello, World!')")
        data = result.get_json()

        assert data["output"] == "Hello, World!\n"
        assert data["image"] == ""

    @patch("coderunner.subprocess.run")
    @patch("coderunner.os.path.exists", return_value=False)
    def test_timeout_handling(self, mock_exists, mock_run, app_context):
        """Test that timeout is properly handled."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="python", timeout=60)

        result = run_python("print('test')")
        data = result.get_json()

        assert "timed out" in data["output"]
        assert "60 seconds" in data["output"]

    @patch("coderunner.subprocess.run")
    @patch("coderunner.os.path.exists", return_value=False)
    def test_error_handling(self, mock_exists, mock_run, app_context):
        """Test that execution errors are captured."""
        import subprocess

        error = subprocess.CalledProcessError(1, "python")
        error.stderr = "SyntaxError: invalid syntax"
        mock_run.side_effect = error

        result = run_python("print(")
        data = result.get_json()

        assert "SyntaxError" in data["output"]


class TestImageHandling:
    """Tests for matplotlib image generation."""

    @patch("coderunner.subprocess.run")
    @patch("coderunner.os.path.exists")
    @patch("coderunner.os.remove")
    @patch("builtins.open", create=True)
    def test_image_encoding(
        self, mock_open, mock_remove, mock_exists, mock_run, app_context
    ):
        """Test that images are properly encoded to base64."""
        import base64

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        # First call checks if image exists, second is in finally block
        mock_exists.side_effect = [True, False]

        # Mock file reading
        test_image_data = b"fake_image_data"
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = test_image_data
        mock_open.return_value = mock_file

        result = run_python(
            "import matplotlib.pyplot as plt; plt.plot([1,2,3]); get_image(plt.gcf())"
        )
        data = result.get_json()

        expected_base64 = base64.b64encode(test_image_data).decode("utf-8")
        assert data["image"] == expected_base64
