#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Run the switcher in the background
nohup python3 beats_switcher.py > beats_switcher.log 2>&1 &
echo "Beats Switcher started! Look for the 🎧 icon in your menu bar."
