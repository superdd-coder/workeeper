#!/bin/bash
# Simple test script for Collection ID/Name mapping

BASE_URL="http://localhost:18920"

echo "=========================================="
echo "Collection ID/Name Mapping Tests"
echo "=========================================="
echo ""

# Test 1: Create collection
echo "Test 1: Create collection"
RESPONSE=$(curl -s -X POST "$BASE_URL/api/collections" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Simple", "dimensions": 1024}')
echo "  Response: $RESPONSE"
COL_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
echo "  Created ID: $COL_ID"
echo ""

# Test 2: List - verify ID and name
echo "Test 2: List collections"
curl -s "$BASE_URL/api/collections" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for c in data:
    print(f\"  {c['id']}: {c['name']}\")
" 2>&1
echo ""

# Test 3: Rename
echo "Test 3: Rename collection"
curl -s -X PUT "$BASE_URL/api/collections/$COL_ID/rename" \
  -H "Content-Type: application/json" \
  -d '{"name": "Renamed Test"}'
echo ""

# Test 4: Verify rename
echo "Test 4: Verify rename"
curl -s "$BASE_URL/api/collections" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for c in data:
    if c['id'] == '$COL_ID':
        print(f\"  ID: {c['id']}\")
        print(f\"  Name: {c['name']}\")
        print(f\"  Match: {c['name'] == 'Renamed Test'}\")
" 2>&1
echo ""

# Test 5: Config API
echo "Test 5: Config API"
CONFIG=$(curl -s "$BASE_URL/api/collections/$COL_ID/config")
echo "  Response: $CONFIG" | head -c 100
echo "..."
echo ""

# Test 6: Delete
echo "Test 6: Delete collection"
curl -s -X DELETE "$BASE_URL/api/collections/$COL_ID"
echo ""

# Test 7: Verify deletion
echo "Test 7: Verify deletion"
curl -s "$BASE_URL/api/collections" | python3 -c "
import sys, json
data = json.load(sys.stdin)
found = any(c['id'] == '$COL_ID' for c in data)
print(f\"  Still exists: {found}\")
" 2>&1
echo ""

echo "=========================================="
echo "Tests completed!"
echo "=========================================="
