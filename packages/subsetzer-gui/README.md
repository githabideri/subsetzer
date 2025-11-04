# Subsetzer GUI

Subsetzer GUI is a lightweight Tk wrapper around the `subsetzer` CLI. It keeps
the same features—local LLM subtitle translation, chunk planning, and output
templating—but presents them in a single window.

## Installation

```bash
pipx install subsetzer-gui
# or
pip install subsetzer-gui
```

This installs both the GUI and the core library. The GUI entry point is
available as `subsetzer-gui` (on Windows it is exposed as a GUI script so no
console window pops up).

## Dependencies

- Python 3.9 or newer.
- Tk bindings (`tkinter`). Many Linux distros package them separately, e.g.

  ```bash
  sudo apt install python3-tk
  ```

- An accessible Ollama-compatible server (defaults to `http://127.0.0.1:11434`).

## Usage

```bash
subsetzer-gui
```

- Pick an input subtitle file (`.srt`, `.vtt`, or `.tsv`).
- Choose the output directory and optional template placeholders.
- Configure the LLM server, model, chunk sizes, and translation flags.
- Click “Build/Update chunks” to plan work, then “Translate ALL”.

You can also launch the GUI with preset CLI-style arguments, for example:

```bash
subsetzer-gui --in demo.srt --out ./out --target "German"
```

## License

GPL-3.0-or-later — see `LICENSE` for the full text.

