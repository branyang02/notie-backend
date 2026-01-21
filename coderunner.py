import base64
import os
import subprocess
import uuid
from flask import jsonify

from util import run_c_code_sync, run_any_code_sync


def run_code(code, language):
    if language == "python":
        return run_python(code)
    elif language == "c":
        return run_c(code)
    else:
        return run_any(code, language)


PYTHON_TIMEOUT_SECONDS = 30

# Patterns that indicate potentially dangerous code
BLOCKED_PATTERNS = {
    # Direct dangerous functions
    "exec",
    "eval",
    "compile",
    # File operations
    "open(",
    "file(",
    # OS/system access
    "subprocess",
    "os.system",
    "os.popen",
    "os.spawn",
    "import os",
    "from os",
    "__import__",
    "import sys",
    "from sys",
    "import shutil",
    "from shutil",
    # Builtins manipulation
    "__builtins__",
    "__globals__",
    "__code__",
    "__subclasses__",
    "__bases__",
    "__mro__",
    # Attribute access tricks
    "getattr",
    "setattr",
    "delattr",
    # Other dangerous modules
    "import socket",
    "from socket",
    "import requests",
    "from requests",
    "import urllib",
    "from urllib",
    "import http",
    "from http",
    "import ftplib",
    "from ftplib",
    "import telnetlib",
    "from telnetlib",
    "import pickle",
    "from pickle",
    "import marshal",
    "from marshal",
    "import ctypes",
    "from ctypes",
    "import multiprocessing",
    "from multiprocessing",
    # Code introspection
    "globals(",
    "locals(",
    "vars(",
    "dir(",
    "type.__",
}


def run_python(code):
    # Check for dangerous patterns
    code_lower = code.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern.lower() in code_lower:
            print(f"Operation not allowed: {pattern}")
            return jsonify({"output": "Error: Operation not allowed"})

    image_filename = f"image_{uuid.uuid4().hex}.png"
    pre_code = f"""
import matplotlib.pyplot as plt
import numpy as np
def get_image(fig):
    filename="{image_filename}"
    fig.savefig(filename)
"""
    encoded_string = ""
    output = ""
    try:
        result = subprocess.run(
            ["python", "-c", pre_code + code],
            text=True,
            capture_output=True,
            check=True,
            timeout=PYTHON_TIMEOUT_SECONDS,
        )
        output = result.stdout
        # Check if the image file exists and encode it
        if os.path.exists(image_filename):
            with open(image_filename, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
            os.remove(image_filename)
    except subprocess.TimeoutExpired:
        output = (
            f"Error: Code execution timed out after {PYTHON_TIMEOUT_SECONDS} seconds"
        )
    except subprocess.CalledProcessError as e:
        output = e.stderr
    finally:
        # Ensure cleanup of image file even on timeout/error
        if os.path.exists(image_filename):
            os.remove(image_filename)
        return jsonify({"output": output, "image": encoded_string})


def run_c(code):
    try:
        output = run_c_code_sync(code)
        return jsonify({"output": output})
    except Exception as e:
        return jsonify({"output": str(e)})


def run_any(code, language):
    try:
        output = run_any_code_sync(code, language)
        return jsonify({"output": output})
    except Exception as e:
        return jsonify({"output": str(e)})
