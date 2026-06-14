import os
import sys
import glob
import json
import re
from pathlib import Path

# Add project root to python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

TRACES_DIR = Path(config.BASE_DIR) / "data" / "traces"
DATASET_FILE = Path(config.BASE_DIR) / "flywheel" / "dataset.jsonl"

def redact_prompt(prompt_text: str) -> tuple[str, bool]:
    """
    Checks each line of the prompt. If a line contains 'key', 'token', or 'secret'
    (case-insensitive) and an API key pattern (30+ alphanumeric/hyphen/underscore characters),
    it redacts that line to [REDACTED].
    """
    if not prompt_text:
        return "", False
        
    lines = prompt_text.splitlines()
    redacted_lines = []
    is_redacted = False
    
    key_regex = re.compile(r'(key|token|secret)', re.IGNORECASE)
    pattern_regex = re.compile(r'[A-Za-z0-9_\-]{30,}')
    
    for line in lines:
        if key_regex.search(line) and pattern_regex.search(line):
            redacted_lines.append("[REDACTED]")
            is_redacted = True
        else:
            redacted_lines.append(line)
            
    return "\n".join(redacted_lines), is_redacted

def main():
    print("Starting dataset extraction from successful traces...")
    
    os.makedirs(os.path.dirname(DATASET_FILE), exist_ok=True)
    
    trace_files = glob.glob(os.path.join(TRACES_DIR, "*.jsonl"))
    
    scanned_count = 0
    extracted_count = 0
    redacted_count = 0
    
    # Open dataset.jsonl for writing
    with open(DATASET_FILE, "w", encoding="utf-8") as out_f:
        for filepath in trace_files:
            scanned_count += 1
            
            # Read and parse events
            events = []
            has_success = False
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.strip():
                            event = json.loads(line)
                            events.append(event)
                            if event.get("event_type") == "trace_ended" and event.get("payload", {}).get("outcome") == "success":
                                has_success = True
            except Exception as e:
                print(f"Error reading {filepath}: {e}")
                continue
                
            if not has_success:
                continue
                
            # Extract llm_request/llm_response pairs
            requests = []
            for event in events:
                e_type = event.get("event_type")
                payload = event.get("payload", {})
                
                if e_type == "llm_request":
                    requests.append(payload)
                elif e_type == "llm_response" and requests:
                    req_payload = requests.pop(0)
                    
                    # Extract prompt and response text
                    prompt = req_payload.get("prompt")
                    response = payload.get("response")
                    
                    if prompt and response:
                        # Apply redaction
                        redacted_prompt_text, is_redacted = redact_prompt(prompt)
                        if is_redacted:
                            redacted_count += 1
                            
                        # Format into target JSONL structure
                        record = {
                            "messages": [
                                {"role": "user", "content": redacted_prompt_text},
                                {"role": "assistant", "content": response}
                            ]
                        }
                        out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        extracted_count += 1
                        
    print("\nDataset Extraction Summary:")
    print(f"  Traces scanned:   {scanned_count}")
    print(f"  Pairs extracted:  {extracted_count}")
    print(f"  Pairs redacted:   {redacted_count}")
    print(f"Saved dataset to {DATASET_FILE}")

if __name__ == "__main__":
    main()
