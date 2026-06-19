#!/bin/bash
# Test script for Collection ID/Name mapping
# Tests: create, rename, list, delete, and API consistency

set -e

BASE_URL="http://localhost:18920"
PASS=0
FAIL=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

pass() {
  echo -e "${GREEN}✓ $1${NC}"
  ((PASS++))
}

fail() {
  echo -e "${RED}✗ $1${NC}"
  ((FAIL++))
}

echo "=========================================="
echo "Collection ID/Name Mapping Tests"
echo "=========================================="
echo ""

# Test 1: Create collection
echo "Test 1: Create collection"
RESPONSE=$(curl -s -X POST "$BASE_URL/api/collections" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Collection", "dimensions": 1024}')
COL_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])" 2>/dev/null)

if [ -n "$COL_ID" ] && [[ "$COL_ID" == col_* ]]; then
  pass "Created collection with ID: $COL_ID"
else
  fail "Failed to create collection: $RESPONSE"
fi

# Test 2: List collections - verify ID and name are present
echo ""
echo "Test 2: List collections"
COLLECTIONS=$(curl -s "$BASE_URL/api/collections")
HAS_ID=$(echo "$COLLECTIONS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
found = any(c['id'] == '$COL_ID' and c['name'] == 'Test Collection' for c in data)
print('true' if found else 'false')
" 2>/dev/null)

if [ "$HAS_ID" = "true" ]; then
  pass "Collection listed with correct ID and name"
else
  fail "Collection not found or incorrect ID/name mapping"
fi

# Test 3: Rename collection
echo ""
echo "Test 3: Rename collection"
RENAME_RESPONSE=$(curl -s -X PUT "$BASE_URL/api/collections/$COL_ID/rename" \
  -H "Content-Type: application/json" \
  -d '{"name": "Renamed Collection"}')

if echo "$RENAME_RESPONSE" | grep -q "renamed"; then
  pass "Collection renamed successfully"
else
  fail "Failed to rename: $RENAME_RESPONSE"
fi

# Test 4: Verify rename - ID should stay same, name should change
echo ""
echo "Test 4: Verify rename persistence"
COLLECTIONS=$(curl -s "$BASE_URL/api/collections")
VERIFY=$(echo "$COLLECTIONS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
found = any(c['id'] == '$COL_ID' and c['name'] == 'Renamed Collection' for c in data)
print('true' if found else 'false')
" 2>/dev/null)

if [ "$VERIFY" = "true" ]; then
  pass "Rename persisted correctly (ID unchanged, name updated)"
else
  fail "Rename not persisted correctly"
fi

# Test 5: Rename again - ID should still stay same
echo ""
echo "Test 5: Multiple renames"
curl -s -X PUT "$BASE_URL/api/collections/$COL_ID/rename" \
  -H "Content-Type: application/json" \
  -d '{"name": "Final Name"}' > /dev/null

COLLECTIONS=$(curl -s "$BASE_URL/api/collections")
VERIFY=$(echo "$COLLECTIONS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
found = any(c['id'] == '$COL_ID' and c['name'] == 'Final Name' for c in data)
print('true' if found else 'false')
" 2>/dev/null)

if [ "$VERIFY" = "true" ]; then
  pass "Multiple renames work correctly"
else
  fail "Multiple renames failed"
fi

# Test 6: Config API uses ID correctly
echo ""
echo "Test 6: Config API uses ID"
CONFIG_RESPONSE=$(curl -s "$BASE_URL/api/collections/$COL_ID/config")
if [ -n "$CONFIG_RESPONSE" ] && ! echo "$CONFIG_RESPONSE" | grep -q "error"; then
  pass "Config API works with collection ID"
else
  fail "Config API failed with ID: $CONFIG_RESPONSE"
fi

# Test 7: Update config uses ID correctly
echo ""
echo "Test 7: Update config uses ID"
UPDATE_RESPONSE=$(curl -s -X PUT "$BASE_URL/api/collections/$COL_ID/config" \
  -H "Content-Type: application/json" \
  -d '{"search_mode": "hybrid"}')

if echo "$UPDATE_RESPONSE" | grep -q "updated"; then
  pass "Config update works with collection ID"
else
  fail "Config update failed: $UPDATE_RESPONSE"
fi

# Test 8: Info API uses ID correctly
echo ""
echo "Test 8: Info API uses ID"
INFO_RESPONSE=$(curl -s "$BASE_URL/api/collections/$COL_ID/info")
if [ -n "$INFO_RESPONSE" ] && ! echo "$INFO_RESPONSE" | grep -q "error"; then
  pass "Info API works with collection ID"
else
  fail "Info API failed: $INFO_RESPONSE"
fi

# Test 9: Delete collection
echo ""
echo "Test 9: Delete collection"
DELETE_RESPONSE=$(curl -s -X DELETE "$BASE_URL/api/collections/$COL_ID")

if echo "$DELETE_RESPONSE" | grep -q "deleted"; then
  pass "Collection deleted successfully"
else
  fail "Failed to delete: $DELETE_RESPONSE"
fi

# Test 10: Verify deletion
echo ""
echo "Test 10: Verify deletion"
COLLECTIONS=$(curl -s "$BASE_URL/api/collections")
DELETED=$(echo "$COLLECTIONS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
found = any(c['id'] == '$COL_ID' for c in data)
print('false' if not found else 'true')
" 2>/dev/null)

if [ "$DELETED" = "false" ]; then
  pass "Collection removed from list after deletion"
else
  fail "Collection still appears after deletion"
fi

# Test 11: No duplicate entries
echo ""
echo "Test 11: No duplicate entries"
COLLECTIONS=$(curl -s "$BASE_URL/api/collections")
DUPLICATES=$(echo "$COLLECTIONS" | python3 -c "
import sys, json
from collections import Counter
data = json.load(sys.stdin)
ids = [c['id'] for c in data]
duplicates = {k: v for k, v in Counter(ids).items() if v > 1}
print(len(duplicates))
" 2>/dev/null)

if [ "$DUPLICATES" = "0" ]; then
  pass "No duplicate collection IDs"
else
  fail "Found $DUPLICATES duplicate IDs"
fi

# Test 12: Legacy collection handling
echo ""
echo "Test 12: Legacy collection handling"
COLLECTIONS=$(curl -s "$BASE_URL/api/collections")
ALL_HAVE_ID=$(echo "$COLLECTIONS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
all_have = all('id' in c and 'name' in c for c in data)
print('true' if all_have else 'false')
" 2>/dev/null)

if [ "$ALL_HAVE_ID" = "true" ]; then
  pass "All collections have id and name fields"
else
  fail "Some collections missing id or name"
fi

# Summary
echo ""
echo "=========================================="
echo "Test Results: $PASS passed, $FAIL failed"
echo "=========================================="

if [ $FAIL -eq 0 ]; then
  echo -e "${GREEN}All tests passed!${NC}"
  exit 0
else
  echo -e "${RED}Some tests failed!${NC}"
  exit 1
fi
