import requests
from dataclasses import dataclass
from typing import Optional

PISTON_BASE_URL = "http://localhost:2000"
PISTON_TIMEOUT = 30

# Must match versions installed by scripts/setup_piston.sh exactly.
# To add a language: add it here, add it to the setup script, run ppman install on server.
LANGUAGE_VERSIONS = {
    "python": "3.12.0",
    "c":      "10.2.0",
    "cpp":    "10.2.0",
    "rust":   "1.73.0",
    "java":   "15.0.2",
}


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    compile_stderr: Optional[str]  # None if language has no compile step

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def error_output(self) -> str:
        """Return the most relevant error: compile error takes priority over stderr."""
        return self.compile_stderr if self.compile_stderr else self.stderr


def execute_code(language: str, code: str) -> ExecutionResult:
    """Submit code to the self-hosted Piston instance.

    Raises ValueError for unsupported languages.
    Raises requests.RequestException on network failure.
    """
    if language not in LANGUAGE_VERSIONS:
        raise ValueError(
            f"Unsupported language: {language!r}. "
            f"Supported: {list(LANGUAGE_VERSIONS)}"
        )
    resp = requests.post(
        f"{PISTON_BASE_URL}/api/v2/execute",
        json={
            "language": language,
            "version": LANGUAGE_VERSIONS[language],
            "files": [{"content": code}],
        },
        timeout=PISTON_TIMEOUT,
    )
    resp.raise_for_status()
    return _parse_response(resp.json())


def _parse_response(data: dict) -> ExecutionResult:
    run = data["run"]
    compile_block = data.get("compile")
    compile_stderr = None
    if compile_block and (compile_block["code"] != 0 or compile_block["stderr"]):
        compile_stderr = compile_block["stderr"]
    return ExecutionResult(
        stdout=run["stdout"],
        stderr=run["stderr"],
        exit_code=run["code"],
        compile_stderr=compile_stderr,
    )
