#!/bin/bash
set -e

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Running setup first..."
    ./setup_voxbiblios.sh
    echo "Setup complete. Now running Vox Biblios..."
fi

# Activate virtual environment and run command
source .venv/bin/activate
vox-biblios "$@"