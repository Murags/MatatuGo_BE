#!/bin/bash
# Convenience script to import trips data from trips.txt

echo "Importing trips data from trips.txt..."
cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "Activated virtual environment"
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "Activated virtual environment"
fi

# Run the import script
python -m api.app.scripts.import_trips

echo "Done!"
