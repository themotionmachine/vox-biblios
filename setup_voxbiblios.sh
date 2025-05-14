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
    echo "curl -fsS https://install.python-poetry.org | python3 -"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo -e "${BLUE}Creating virtual environment...${NC}"
    uv venv
fi

# Install dependencies using uv
echo -e "${BLUE}Installing dependencies...${NC}"
uv pip install -e .

echo -e "${GREEN}Setup complete! Vox Biblios is ready to use.${NC}"
echo -e "${BLUE}Activate the virtual environment with:${NC}"
echo "source .venv/bin/activate"
echo -e "${BLUE}Run Vox Biblios with:${NC}"
echo "vox-biblios [command]"