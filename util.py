import asyncio

from pyston import PystonClient, File

# Global event loop and PystonClient for connection reuse
_loop = None
_pyston_client = None


def _get_loop():
    """Get or create a reusable event loop."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def _get_pyston_client():
    """Get or create a reusable PystonClient."""
    global _pyston_client
    if _pyston_client is None:
        _pyston_client = PystonClient()
    return _pyston_client


def create_thread_input(code):
    # Prepare the code by escaping backslashes and double quotes
    escaped_code = code.replace("\\", "\\\\").replace('"', '\\"')
    lines = escaped_code.split("\n")
    for i in range(len(lines)):
        line = lines[i]
        lines[i] = '"' + line + '\\n"'

    formatted_code = "\n".join(lines)

    modified_code = f"""
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>


int main() {{

    const char* code = \n{formatted_code};

    // Write the above code to a file
    FILE* file = fopen("thread_example.c", "w");
    if (file == NULL) {{
        perror("Failed to open file");
        return 1;
    }}
    fputs(code, file);
    fclose(file);

    int result = system("gcc -o thread_example thread_example.c -pthread");
    if (result != 0) {{
        fprintf(stderr, "Compilation failed\\n");
        remove("thread_example.c");
        return 1;
    }}

    system("./thread_example");

    // Clean up temporary files
    remove("thread_example.c");
    remove("thread_example");

    return 0;
}}
"""

    return modified_code


def run_c_code_sync(code):
    # check if we are using <pthread.h> in the code
    if "#include <pthread.h>" in code:
        print("Using pthread")
        code = create_thread_input(code)

    return run_any_code_sync(code, "c")


def run_any_code_sync(code, language):
    result = None

    async def main_loop():
        nonlocal result
        pyston_client = _get_pyston_client()
        output = await pyston_client.execute(language, [File(code)])
        result = output

    loop = _get_loop()
    loop.run_until_complete(asyncio.wait_for(main_loop(), timeout=30))

    result = result.raw_json
    print("-------------------")
    print(result)
    print("-------------------")

    if "compile" in result and (
        result["compile"]["code"] != 0 or result["compile"]["stderr"] != ""
    ):
        raise Exception(result["compile"]["stderr"])
    if result["run"]["code"] != 0 or result["run"]["stderr"] != "":
        raise Exception(result["run"]["stderr"])

    return result["run"]["stdout"]
