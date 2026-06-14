# Local Model Data Flywheel

This module converts successful agent execution traces into a fine-tuning dataset format for training or tuning a local language model.

## Dataset Generation

To generate the dataset from successful traces, run:

```bash
python flywheel/extract_dataset.py
```

This will scan the trace files, locate traces of successful agent runs, extract request-response pairs, filter/redact sensitive API keys or tokens, and output them as messages format in `dataset.jsonl`.

## Fine-Tuning Out of Scope

The execution of the fine-tuning job itself is out of scope for this automated process. A human operator or a higher-tier agent must run the actual fine-tuning using tools like Ollama or Axolotl.
