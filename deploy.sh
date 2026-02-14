#!/bin/bash
# Hanak Search — deploy from local (master) to Azure VM
# Usage: ./deploy.sh [--site] [--code] [--all]
#   --site  sync site/ (images, HTML, assets)
#   --code  sync api/, search-ui/, configs + restart Docker
#   --all   both (default)

set -e

VM="azureuser@4.225.202.55"
REMOTE_DIR="~/hanak-search"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

MODE="${1:---all}"

echo "🚀 Hanak Search Deploy"
echo "   Local: $LOCAL_DIR"
echo "   VM:    $VM:$REMOTE_DIR"
echo ""

if [[ "$MODE" == "--site" || "$MODE" == "--all" ]]; then
    echo "📦 Syncing site/..."
    rsync -avz --delete "$LOCAL_DIR/site/" "$VM:$REMOTE_DIR/site/"
    echo ""
fi

if [[ "$MODE" == "--code" || "$MODE" == "--all" ]]; then
    echo "📦 Syncing code..."
    rsync -avz "$LOCAL_DIR/api/" "$VM:$REMOTE_DIR/api/"
    rsync -avz "$LOCAL_DIR/search-ui/" "$VM:$REMOTE_DIR/search-ui/"
    rsync -avz "$LOCAL_DIR/docker-compose.yml" "$VM:$REMOTE_DIR/docker-compose.yml"
    rsync -avz "$LOCAL_DIR/docker-compose.prod.yml" "$VM:$REMOTE_DIR/docker-compose.prod.yml" 2>/dev/null || true
    rsync -avz "$LOCAL_DIR/nginx.conf" "$VM:$REMOTE_DIR/nginx.conf"
    rsync -avz "$LOCAL_DIR/inject-search.py" "$VM:$REMOTE_DIR/inject-search.py"

    echo ""
    echo "🔄 Re-injecting search UI..."
    ssh "$VM" "cd $REMOTE_DIR && python3 inject-search.py"

    echo ""
    echo "🐳 Rebuilding & restarting Docker..."
    ssh "$VM" "cd $REMOTE_DIR && docker compose up -d --build"
    
    echo ""
    echo "⏳ Waiting for API..."
    sleep 10
    
    echo ""
    echo "✅ Health check:"
    curl -s "https://hanak.goden.ai/api/health"
    echo ""
fi

echo ""
echo "✅ Deploy complete!"
