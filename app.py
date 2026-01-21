import subprocess

from flask import Flask, jsonify, request, Response
from util import get_word_details, get_audio
from flask_cors import CORS
from coderunner import run_code


app = Flask(__name__)
CORS(app)


# Cache git info at module load to avoid subprocess calls on each request
_git_info = None


def get_git_info():
    global _git_info
    if _git_info is None:
        try:
            commit_hash = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip()
            commit_message = subprocess.check_output(
                ["git", "log", "-1", "--pretty=%B"], text=True
            ).strip()
            _git_info = {"commit_hash": commit_hash, "commit_message": commit_message}
        except subprocess.CalledProcessError:
            _git_info = {"error": "Could not retrieve git info"}
    return _git_info


@app.route("/")
def health():
    return jsonify(status="ok")


@app.route("/info")
def info():
    return jsonify(get_git_info())


@app.route("/echo", methods=["POST"])
def echo():
    return jsonify(request.get_json(silent=True) or {})


@app.route("/api/word-details/<word>", methods=["GET"])
def word_details(word):
    if not word:
        return jsonify({"error": "No word provided"}), 400

    try:
        word_details = get_word_details(word)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify(word_details)


@app.route("/api/text-to-speech", methods=["POST"])
def text_to_speech():
    data = request.get_json()
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        response = get_audio(text)
        return Response(
            response.content, mimetype="audio/mpeg"
        )  # adjust mimetype based on the format

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/coderunner", methods=["POST"])
def code_runner():
    data = request.get_json()

    if not data or "language" not in data or "code" not in data:
        return jsonify({"error": "No language or code provided"}), 400

    language = data["language"]
    code = data["code"]

    try:
        output = run_code(code, language)
        return output
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
