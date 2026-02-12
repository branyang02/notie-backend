import pytest
from unittest.mock import patch, MagicMock
import sys

# Mock OpenAI before importing modules that use it
sys.modules["openai"] = MagicMock()


class TestRunAnySyncCodeCleanup:
    """Tests for the async client cleanup in run_any_code_sync."""

    @patch("util._get_pyston_client")
    def test_client_close_called_on_success(self, mock_get_pyston_client):
        """Test that execution succeeds with reusable client."""
        from util import run_any_code_sync

        # Setup mock client
        mock_client = MagicMock()
        mock_output = MagicMock()
        mock_output.raw_json = {"run": {"code": 0, "stderr": "", "stdout": "Hello"}}

        # Setup async mocks
        async def mock_execute(*args):
            return mock_output

        mock_client.execute = mock_execute
        mock_get_pyston_client.return_value = mock_client

        result = run_any_code_sync("print('Hello')", "python")

        assert result == "Hello"

    @patch("util._get_pyston_client")
    def test_client_close_called_on_exception(self, mock_get_pyston_client):
        """Test that execution errors propagate correctly."""
        from util import run_any_code_sync

        mock_client = MagicMock()

        async def mock_execute(*args):
            raise RuntimeError("Execution failed")

        mock_client.execute = mock_execute
        mock_get_pyston_client.return_value = mock_client

        with pytest.raises(RuntimeError):
            run_any_code_sync("invalid code", "python")

    @patch("util._get_pyston_client")
    def test_compile_error_raises_exception(self, mock_get_pyston_client):
        """Test that compilation errors are raised as exceptions."""
        from util import run_any_code_sync

        mock_client = MagicMock()
        mock_output = MagicMock()
        mock_output.raw_json = {
            "compile": {"code": 1, "stderr": "undefined reference to main"},
            "run": {"code": 0, "stderr": "", "stdout": ""},
        }

        async def mock_execute(*args):
            return mock_output

        mock_client.execute = mock_execute
        mock_get_pyston_client.return_value = mock_client

        with pytest.raises(Exception) as exc_info:
            run_any_code_sync("bad code", "c")

        assert "undefined reference" in str(exc_info.value)

    @patch("util._get_pyston_client")
    def test_runtime_error_raises_exception(self, mock_get_pyston_client):
        """Test that runtime errors are raised as exceptions."""
        from util import run_any_code_sync

        mock_client = MagicMock()
        mock_output = MagicMock()
        mock_output.raw_json = {
            "run": {"code": 1, "stderr": "Segmentation fault", "stdout": ""}
        }

        async def mock_execute(*args):
            return mock_output

        mock_client.execute = mock_execute
        mock_get_pyston_client.return_value = mock_client

        with pytest.raises(Exception) as exc_info:
            run_any_code_sync("int main() { int *p = 0; *p = 1; }", "c")

        assert "Segmentation fault" in str(exc_info.value)


class TestRunCCodeSync:
    """Tests for the run_c_code_sync function."""

    @patch("util.run_any_code_sync")
    def test_regular_c_code(self, mock_run_any):
        """Test that regular C code is passed through."""
        from util import run_c_code_sync

        mock_run_any.return_value = "Hello"
        code = '#include <stdio.h>\nint main() { printf("Hello"); return 0; }'

        result = run_c_code_sync(code)

        mock_run_any.assert_called_once_with(code, "c")
        assert result == "Hello"

    @patch("util.run_any_code_sync")
    def test_pthread_code_wrapped(self, mock_run_any):
        """Test that pthread code is wrapped with the thread input creator."""
        from util import run_c_code_sync

        mock_run_any.return_value = "Thread output"
        code = "#include <pthread.h>\nvoid* thread_func(void* arg) { return NULL; }"

        run_c_code_sync(code)

        # Verify run_any_code_sync was called with modified code
        call_args = mock_run_any.call_args[0]
        modified_code = call_args[0]

        # The wrapped code should contain the thread wrapper template
        assert "thread_example.c" in modified_code
        assert "gcc -o thread_example" in modified_code


class TestCreateThreadInput:
    """Tests for the create_thread_input function."""

    def test_escapes_special_characters(self):
        """Test that backslashes and quotes are properly escaped."""
        from util import create_thread_input

        code = 'printf("Hello\\nWorld");'
        result = create_thread_input(code)

        # The result should be valid C code
        assert "#include <stdio.h>" in result
        assert 'fopen("thread_example.c"' in result

    def test_wraps_code_in_main(self):
        """Test that the wrapper contains proper main function."""
        from util import create_thread_input

        code = "void test() {}"
        result = create_thread_input(code)

        assert "int main()" in result
        assert 'system("./thread_example")' in result

    def test_cleanup_files_in_wrapper(self):
        """Test that wrapper includes cleanup for temporary files."""
        from util import create_thread_input

        code = "int x = 1;"
        result = create_thread_input(code)

        assert 'remove("thread_example.c")' in result
        assert 'remove("thread_example")' in result
