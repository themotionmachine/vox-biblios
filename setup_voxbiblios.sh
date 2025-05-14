#!/bin/bash
set -e

# Colors for better output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Setting up Vox Biblios with uv...${NC}"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo -e "${RED}uv is not installed. Please install it first:${NC}"
    echo "curl -fsS https://github.com/astral-sh/uv/releases/download/0.1.24/uv-installer.sh | bash"
    exit 1
fi

# Check Python version
python_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if (( $(echo "$python_version < 3.10" | bc -l) )); then
    echo -e "${RED}Python 3.10 or higher is required (found $python_version).${NC}"
    echo "Please install Python 3.10+ and try again."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo -e "${BLUE}Creating virtual environment...${NC}"
    python3 -m venv .venv
fi

# Install dependencies using uv
echo -e "${BLUE}Installing dependencies...${NC}"
source .venv/bin/activate
uv pip install -e .

echo -e "${GREEN}Setup complete! Vox Biblios is ready to use.${NC}"
echo -e "${BLUE}Activate the virtual environment with:${NC}"
echo "source .venv/bin/activate"
echo -e "${BLUE}Run Vox Biblios with:${NC}"
echo "vox-biblios [command]"