#!/bin/bash
cd /Users/lex/repos/hanak-search

# Load existing descriptions
JSON_FILE="image-descriptions.json"
TEMP_FILE="image-descriptions-new.json"
LOG_FILE="describe-progress.log"

# Get list of already described images
EXISTING=$(python3 -c "import json; d=json.load(open('$JSON_FILE')); print('\n'.join(d.keys()))")

# Find all images >20KB, filter out already described
COUNT=0
BATCH=0
TOTAL_NEW=0

# Create temp merge script
cat > /tmp/merge_descriptions.py << 'PYEOF'
import json, sys

existing_file = sys.argv[1]
new_entries_file = sys.argv[2]

with open(existing_file) as f:
    data = json.load(f)

with open(new_entries_file) as f:
    for line in f:
        line = line.strip()
        if line:
            entry = json.loads(line)
            data.update(entry)

with open(existing_file, 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Total entries now: {len(data)}")
PYEOF

# Temp file for batch entries
BATCH_FILE="/tmp/hanak_batch.jsonl"
> "$BATCH_FILE"

echo "$(date): Starting image description run" >> "$LOG_FILE"

find site/www.hanak-nabytek.cz -type f \( -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" -o -name "*.webp" \) -size +20k | sort | while read -r img; do
    # Normalize path (remove leading ./ if any)
    REL_PATH="$img"
    
    # Check if already described
    if echo "$EXISTING" | grep -qF "$REL_PATH"; then
        continue
    fi
    
    # Check file size (<5MB)
    FSIZE=$(stat -f%z "$img" 2>/dev/null || stat -c%s "$img" 2>/dev/null)
    if [ "$FSIZE" -gt 5242880 ]; then
        echo "SKIP (>5MB): $img" >> "$LOG_FILE"
        continue
    fi
    
    TOTAL_NEW=$((TOTAL_NEW + 1))
    
    # Base64 encode
    B64=$(base64 -i "$img" | tr -d '\n')
    
    # Call Ollama
    RESPONSE=$(curl -s --max-time 30 http://100.124.94.31:11434/api/chat \
        -d "{\"model\":\"qwen2.5vl:7b\",\"messages\":[{\"role\":\"user\",\"content\":\"Popiš tento obrázek nábytku/interiéru česky. Zaměř se na: typ nábytku, materiály, barvy, styl designu, prostor. Max 2-3 věty.\",\"images\":[\"$B64\"]}],\"stream\":false}" 2>/dev/null)
    
    # Extract description
    DESC=$(echo "$RESPONSE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['message']['content'])" 2>/dev/null)
    
    if [ -z "$DESC" ]; then
        echo "FAIL: $img" >> "$LOG_FILE"
        continue
    fi
    
    # Escape for JSON
    DESC_JSON=$(python3 -c "import json; print(json.dumps({\"$REL_PATH\": $(echo "$DESC" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))")}))")
    echo "$DESC_JSON" >> "$BATCH_FILE"
    
    COUNT=$((COUNT + 1))
    BATCH=$((BATCH + 1))
    echo "OK ($COUNT): $img" >> "$LOG_FILE"
    
    # Save every 20
    if [ "$BATCH" -ge 20 ]; then
        python3 /tmp/merge_descriptions.py "$JSON_FILE" "$BATCH_FILE"
        echo "$(date): Saved batch, total processed: $COUNT" >> "$LOG_FILE"
        > "$BATCH_FILE"
        BATCH=0
    fi
done

# Final save
if [ -s "$BATCH_FILE" ]; then
    python3 /tmp/merge_descriptions.py "$JSON_FILE" "$BATCH_FILE"
fi

echo "$(date): Done. Processed $COUNT images." >> "$LOG_FILE"
echo "Done. Processed $COUNT new images."
