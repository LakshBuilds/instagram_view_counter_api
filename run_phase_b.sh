#!/bin/bash
# Mac-side runner: uploads phase_b_vm.sh to the VM and executes it.
set -e
KEY="$HOME/oracle.key"
VM="ubuntu@144.24.148.8"

echo "=== uploading Phase B script ==="
scp -i "$KEY" "$(dirname "$0")/phase_b_vm.sh" "$VM:phase_b.sh"

echo
echo "=== running Phase B on VM (this may take 1-3 min) ==="
ssh -i "$KEY" -t "$VM" "bash ~/phase_b.sh"
