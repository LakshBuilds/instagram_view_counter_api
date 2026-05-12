#!/bin/bash
# Phase A — copy project + cloudflared credentials to the Oracle VM.
# Run from your Mac: bash deploy_to_vm.sh
set -e

KEY="$HOME/oracle.key"
VM="ubuntu@144.24.148.8"
PROJECT="/Users/buyhatke/Desktop/instagram_view_counter_api"

echo "=== sanity ==="
test -f "$KEY"     || { echo "missing key: $KEY"; exit 1; }
test -d "$PROJECT" || { echo "missing project dir: $PROJECT"; exit 1; }
test -f "$HOME/.cloudflared/cert.pem" || { echo "missing ~/.cloudflared/cert.pem"; exit 1; }
TUNNEL_JSON=$(ls "$HOME/.cloudflared/"*.json 2>/dev/null | head -1)
test -f "$TUNNEL_JSON" || { echo "no tunnel json in ~/.cloudflared/"; exit 1; }
echo "tunnel json: $TUNNEL_JSON"

echo
echo "=== rsync project ==="
rsync -avz -e "ssh -i $KEY" \
    --exclude=.git \
    --exclude=__pycache__ \
    --exclude='*.log' \
    --exclude='*.png' \
    --exclude='deploy_to_vm.sh' \
    "$PROJECT/" "$VM:instagram_view_counter_api/"

echo
echo "=== copy cloudflared credentials ==="
scp -i "$KEY" "$HOME/.cloudflared/cert.pem"  "$VM:cloudflared_cert.pem"
scp -i "$KEY" "$TUNNEL_JSON"                 "$VM:cloudflared_tunnel.json"

echo
echo "✅ Phase A done — files uploaded. Now run Phase B (the VM setup script)."
