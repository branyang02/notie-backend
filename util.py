from openai import OpenAI
from pyston import PystonClient, File
import asyncio

client = OpenAI()


def get_word_details(word):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo-1106",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant designed to output JSON.",
            },
            {
                "role": "user",
                "content": f"Give me the language of origin, definition, and example usage for the word '{word}' in the format: {{'word': '{word}', 'language_of_origin': '...', 'definition': '...', 'example_usage': '...'}}.",
            },
        ],
    )

    return eval(response.choices[0].message.content)


def get_audio(text):
    """Converts text to speech using OpenAI's API and returns the file path."""
    response = client.audio.speech.create(
        model="tts-1", voice="alloy", input=text, response_format="mp3"
    )
    return response


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
        client = PystonClient()
        try:
            output = await client.execute(language, [File(code)])
            result = output
        finally:
            await client.close_session()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(asyncio.wait_for(main_loop(), timeout=30))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
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
