#!/bin/bash
# ============================================================================
# Obsidian Meetings - Development Environment Setup
# ============================================================================
# This script sets up the Python virtual environment for this project
# and installs project-specific dependencies.
#
# Prerequisites: Ollama + Aider should be installed system-wide
# Run: ~/Documents/Dev/agentic_Projects/projects/scripts/ollama-aider-setup.sh
# ============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

pick_python_bin() {
    local candidate
    candidate="$(which -a python3.11 2>/dev/null | grep -v '/.pyenv/shims/' | head -n 1 || true)"
    if [ -n "$candidate" ]; then
        echo "$candidate"
        return 0
    fi
    candidate="$(which -a python3 2>/dev/null | grep -v '/.pyenv/shims/' | head -n 1 || true)"
    if [ -n "$candidate" ]; then
        echo "$candidate"
        return 0
    fi
    return 1
}

# ============================================================================
# Setup Virtual Environment
# ============================================================================

log_info "Setting up virtual environment for Obsidian Meetings..."

PYTHON_BIN="$(pick_python_bin || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "A non-pyenv-shim python3.11 (preferred) or python3 (3.11+) is required."
    exit 1
fi

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    log_info "Creating virtual environment..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    log_success "Virtual environment created"
else
    log_info "Virtual environment already exists"
fi

# Activate venv
log_info "Activating virtual environment..."
VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# Upgrade pip
log_info "Upgrading pip..."
"$VENV_PY" -m pip install --upgrade pip setuptools wheel

# Install project dependencies
if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    log_info "Installing dependencies from requirements.txt..."
    "$VENV_PIP" install -r "$PROJECT_DIR/requirements.txt"
else
    log_info "No requirements.txt found. Installing common development dependencies..."
    "$VENV_PIP" install \
        python-dateutil \
        pytz \
        pyyaml \
        requests \
        black \
        pylint \
        pytest
fi

log_info "Installing Whisper CLI for transcription runs..."
"$VENV_PIP" install openai-whisper

if "$VENV_PY" -m whisper --help >/dev/null 2>&1; then
    log_success "Whisper CLI check: OK"
else
    echo "[WARN] Whisper CLI not available in .venv; transcription commands will fail."
fi

log_success "Development environment ready!"

cat << 'EOF'

╔════════════════════════════════════════════════════════════════════════╗
║              Obsidian Meetings - Dev Environment Ready                 ║
╚════════════════════════════════════════════════════════════════════════╝

📁 Project: Obsidian Meetings
🐍 Virtual Environment: .venv

🚀 To activate the environment:
   source .venv/bin/activate

🤖 To start coding with AI:
   source .venv/bin/activate
   aider --model ollama/qwen2.5-coder:8k

📝 Example Aider commands:
   # Work on specific files
   aider src/main.py

   # Add context
   aider
   > /add src/*.py

   # Use reasoning model for complex tasks
   aider --model ollama/deepseek-r1:8k

💡 Tip: The venv is project-specific, but Aider and Ollama are system-wide!

EOF
