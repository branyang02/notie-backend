import base64
import os
import subprocess

from flask import Flask, request, jsonify
from flask_cors import CORS

from pyston import PystonClient, File
import asyncio


app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    python_path = subprocess.run(["which", "python"], text=True, capture_output=True).stdout.strip()
    return 'Hello World using ' + python_path


@app.route("/api/coderunner", methods=["POST"])
def code_runner():
    data = request.get_json()

    if not data and ("language" not in data or "code" not in data):
        return jsonify({"error": "No language or code provided"}), 400

    language = data["language"]
    code = data["code"]

    try:
        output = run_code(code, language)
    except Exception as e:
        return str(e)
    finally:
        return output
    
def run_code(code, language):
    if language == "python":
        return run_python(code)
    elif language == "c":
        return run_c(code)
    else:
        return run_any(code, language)
    
def run_python(code):
    # List of potentially dangerous modules or functions
    blocked_keywords = {
        "open",
        "file",
        "exec",
        "eval",
        "subprocess",
        "os.system",
        "import os",
        "__import__",
        "sys",
    }

    # Check for dangerous keywords
    if any(keyword in code for keyword in blocked_keywords):
        print("Operation not allowed")
        return jsonify({"output": "Error: Operation not allowed"})

    pre_code = """
import matplotlib.pyplot as plt
import numpy as np
def get_image(fig):
    filename="image.png"
    fig.savefig(filename)
"""
    print(pre_code + code)
    encoded_string = ""
    try:
        result = subprocess.run(
            ["python3", "-c", pre_code + code],
            text=True,
            capture_output=True,
            check=True,
        )
        output = result.stdout
        # Check if the image file exists and encode it
        if os.path.exists("image.png"):
            with open("image.png", "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
            os.remove("image.png")
    except subprocess.CalledProcessError as e:
        output = e.stderr
    finally:
        return jsonify({"output": output, "image": encoded_string})

def run_c(code):
    try:
        output = run_c_code_sync(code)
    except Exception as e:
        output = str(e)
    finally:
        return jsonify({"output": output})
    
def run_any(code, language):
    try:
        output = run_any_code_sync(code, language)
    except Exception as e:
        output = str(e)
    finally:
        return jsonify({"output": output})
    
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
        client = PystonClient()
        output = await client.execute(language, [File(code)])
        result = output

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main_loop())
    finally:
        loop.close()

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
        return 1;
    }}

    system("./thread_example");

    return 0;
}}
"""

    return modified_code

