#!/bin/bash
# Convenience script to update route_id data into the edges table

echo "Updating edges table with route_id..."
cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "Activated virtual environment"
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "Activated virtual environment"
fi

python -m api.app.scripts.import_route_ids_to_edges

echo "✅ Done updating route_id in edges!"
