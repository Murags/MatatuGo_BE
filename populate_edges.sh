#!/bin/bash
# Convenience script to populate edges table

echo "Populating edges table from stop_times data..."
cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "Activated virtual environment"
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "Activated virtual environment"
fi

# Run the populate script
python -m api.app.scripts.populate_edges

echo "Done!"
