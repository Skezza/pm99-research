"""Reverse‑engineering‑aware Codex loop script for PM99

This script drives the OpenAI Codex model to generate **reverse‑engineering**
code snippets that are directly useful for the *Premier Manager 99* database
editor.  Each iteration feeds a **development objective** together with the
previously generated snippet back to Codex, preserving context such as
byte‑offset handling, XOR‑encoded fields, and record layout knowledge.

The prompt is deliberately crafted to remind Codex of the project's low‑level
concerns (e.g. *"handle a 2‑byte little‑endian team‑ID at offset 0x00"*).  This
helps the model produce code that respects the binary format rather than a
high‑level abstraction.

Usage example::

    python scripts/ralph_wiggum_codex_loop.py \
        --objectives \
            "Parse team ID (2‑byte little‑endian) at offset 0x00" \
            "Decode XOR‑encoded player name strings with length prefix" \
            "Update directory offsets after variable‑length name change" \
        --delay 1.0

The script requires the ``openai`` package and an ``OPENAI_API_KEY``
environment variable.

Requirements
------------
* Python 3.8+
* ``openai`` package (`pip install openai`)
* An OpenAI API key exported as the ``OPENAI_API_KEY`` environment variable.

Usage
-----
Run the script directly:

```bash
python scripts/ralph_wiggum_codex_loop.py --iterations 5
```

The ``--iterations`` argument controls how many times Codex is called. The
generated code is printed to stdout after each iteration.
"""

import os
import sys
import argparse
import time
from typing import List

try:
    import openai
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "The 'openai' package is required. Install it with 'pip install openai'."
    ) from exc


def build_prompt(objective: str, previous_code: str = "") -> str:
    """Create a concise prompt for a single development objective.

    The prompt now optionally includes the *previously generated* snippet so that
    Codex can build on earlier work.  This mirrors the original intent of the
    script – a feedback loop – while still keeping the prompt short enough for
    the ``code-davinci-002`` model.
    """
    core_context = (
        "You are an expert Python developer working on the Premier Manager 99 "
        "database editor. The game stores data in binary FDI files with 2‑byte "
        "little‑endian offsets, length‑prefixed XOR‑encoded strings, and a "
        "directory that must be updated when record sizes change."
    )
    # Include the previous snippet if provided – this helps Codex maintain
    # continuity across iterations.
    if previous_code:
        context = (
            f"Previously generated code:\n```
{previous_code}
```\n"
        )
    else:
        context = ""
    return f"{core_context}\n\n{context}Generate a short, PEP‑8‑compliant Python snippet that {objective}."


def call_codex(prompt: str, max_tokens: int = 150) -> str:
    """Call the Codex model and return the generated code.

    Parameters
    ----------
    prompt: str
        The prompt to send to the model.
    max_tokens: int, optional
        Maximum number of tokens to generate. Defaults to 150.
    """
    response = openai.Completion.create(
        engine="code-davinci-002",
        prompt=prompt,
        temperature=0.7,
        max_tokens=max_tokens,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        stop=None,
    )
    return response.choices[0].text.strip()


def write_generated_code(filename: str, code: str) -> None:
    """Write a generated snippet to ``generated/<filename>``.

    The function creates the ``generated`` directory if it does not exist and
    writes the code to the specified file, overwriting any previous content.
    """
    out_dir = os.path.join(os.getcwd(), "generated")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"✅ Written generated snippet to {out_path}")


def main(objectives: List[str], delay: float) -> None:
    """Run the Codex loop over a list of development objectives.

    Parameters
    ----------
    objectives: List[str]
        Ordered list of tasks for Codex to implement.
    delay: float
        Seconds to wait between calls (helps avoid rate limits).
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit(
            "Please set the OPENAI_API_KEY environment variable with your OpenAI API key."
        )
    openai.api_key = api_key

    previous_code: str = ""
    for idx, obj in enumerate(objectives, start=1):
        prompt = build_prompt(obj, previous_code)
        print(f"--- Objective {idx}/{len(objectives)}: {obj} ---")
        print("Prompt sent to Codex:\n", prompt)
        generated = call_codex(prompt)
        print("\nGenerated code:\n", generated)
        # Save the snippet; filename is derived from the objective slugified
        safe_name = "_".join(obj.lower().split())[:50] + ".py"
        write_generated_code(safe_name, generated)
        previous_code = f"{previous_code}\n{generated}" if previous_code else generated
        if idx < len(objectives):
            time.sleep(delay)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ralph Wiggum Codex loop script")
    parser.add_argument(
        "--objectives",
        nargs="*",
        default=[
            "Add nationality parsing to PlayerRecord",
            "Implement team‑ID linking between PlayerRecord and TeamRecord",
            "Create a bulk‑rename helper for player names",
        ],
        help="List of development objectives for Codex (default: three core tasks)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay in seconds between calls (default: 1.0)",
    )
    args = parser.parse_args()
    main(args.objectives, args.delay)
