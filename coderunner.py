from flask import jsonify

from piston import execute_code

MATPLOTLIB_SENTINEL = "__NOTIE_FIGURE__:"

# Injected before user code when matplotlib usage is detected.
# Patches plt.show() and Figure.savefig() to print base64-encoded PNG to stdout
# with a sentinel prefix, which _split_output() then strips and returns separately.
MATPLOTLIB_PREAMBLE = """\
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as _plt
import matplotlib.figure as _mfig
import io as _io
import base64 as _b64

_orig_show = _plt.show
def _patched_show(*a, **kw):
    for i in _plt.get_fignums():
        buf = _io.BytesIO()
        _plt.figure(i).savefig(buf, format='png')
        print("__NOTIE_FIGURE__:" + _b64.b64encode(buf.getvalue()).decode())
    _plt.close('all')
_plt.show = _patched_show

_orig_savefig = _mfig.Figure.savefig
def _patched_savefig(self, fname, *a, **kw):
    if isinstance(fname, str):
        buf = _io.BytesIO()
        _orig_savefig(self, buf, *a, **kw)
        print("__NOTIE_FIGURE__:" + _b64.b64encode(buf.getvalue()).decode())
    else:
        _orig_savefig(self, fname, *a, **kw)
_mfig.Figure.savefig = _patched_savefig

import numpy as np
"""


def _needs_plotting(code: str) -> bool:
    return any(t in code for t in ("plt.", "matplotlib", "savefig"))


def _split_output(stdout: str) -> tuple[str, str]:
    """Separate normal stdout from sentinel-encoded figure data.

    Returns (text_output, last_base64_image_or_empty_string).
    """
    lines, image = [], ""
    for line in stdout.splitlines(keepends=True):
        if line.startswith(MATPLOTLIB_SENTINEL):
            image = line[len(MATPLOTLIB_SENTINEL):].rstrip("\n")
        else:
            lines.append(line)
    return "".join(lines), image


def run_code(code: str, language: str):
    if language == "python":
        return _run_python(code)
    else:
        return _run_generic(code, language)


def _run_python(code: str):
    full_code = (MATPLOTLIB_PREAMBLE + code) if _needs_plotting(code) else code
    try:
        result = execute_code("python", full_code)
        output, image = _split_output(result.stdout)
        if not result.success:
            output = result.error_output
        return jsonify({"output": output, "image": image})
    except Exception as e:
        return jsonify({"output": str(e), "image": ""}), 500


def _run_generic(code: str, language: str):
    try:
        result = execute_code(language, code)
        output = result.stdout if result.success else result.error_output
        return jsonify({"output": output})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
