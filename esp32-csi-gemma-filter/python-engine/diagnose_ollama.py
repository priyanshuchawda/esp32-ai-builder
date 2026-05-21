import requests
import json
import time

url = "http://localhost:11434/api/chat"
model = "gemma4:e2b"

payload = {
    "model": model,
    "messages": [
        {
            "role": "system",
            "content": "You are a local Wi-Fi CSI noise filtering advisor. Return JSON only. No markdown."
        },
        {
            "role": "user",
            "content": "Recommend a filter for: outlier_ratio: 0.15, signal_std: 1.2"
        }
    ],
    "stream": False,
    "options": {
        "temperature": 0.0
    }
}

print(f"Connecting to local Ollama API to test model '{model}'...")
print("This may take up to 30-60 seconds on the first run as the model loads into RAM/VRAM...")

start_time = time.time()
try:
    response = requests.post(url, json=payload, timeout=60.0)
    elapsed = time.time() - start_time
    
    if response.status_code == 200:
        result = response.json()
        content = result.get("message", {}).get("content", "")
        print(f"\n[SUCCESS] Response received in {elapsed:.2f} seconds!")
        print("Raw Content Output:")
        print("-" * 40)
        print(content)
        print("-" * 40)
        
        # Test parsing
        clean_content = content.strip()
        if clean_content.startswith("```"):
            lines = clean_content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_content = "\n".join(lines).strip()
            
        try:
            parsed = json.loads(clean_content)
            print("Successfully parsed response JSON:")
            print(json.dumps(parsed, indent=2))
        except Exception as parse_err:
            print(f"[WARNING] Could not parse output as JSON: {parse_err}")
    else:
        print(f"\n[ERROR] Ollama returned status code {response.status_code}")
        print(response.text)
except requests.exceptions.RequestException as e:
    print(f"\n[ERROR] Connection failed. Is Ollama running? Error: {e}")
