#!/bin/bash
# ABOUTME: Integration smoke tests for meetingctl start-stop-process loop
# ABOUTME: Tests both happy paths and error paths with detailed output

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Test state directory (use temp for isolation)
TEST_STATE_DIR="/tmp/meetingctl-smoke-test-$$"
TEST_QUEUE_FILE="$TEST_STATE_DIR/process_queue.jsonl"
TEST_PROCESSED_FILE="$TEST_STATE_DIR/processed_jobs.jsonl"
TEST_RECORDINGS_DIR="$TEST_STATE_DIR/recordings"
TEST_VAULT_DIR="$TEST_STATE_DIR/vault"
TEST_NOTE_PATH="$TEST_VAULT_DIR/meeting-note.md"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$PROJECT_ROOT/.venv/bin/python}"
SMOKE_REAL_MACHINE="${SMOKE_REAL_MACHINE:-0}"

meetingctl_cli() {
    PYTHONPATH="$PROJECT_ROOT/src" "$PYTHON_BIN" -m meetingctl.cli "$@"
}

echo -e "${BOLD}=== meetingctl Integration Smoke Tests ===${NC}\n"

# Setup test environment
setup_test_env() {
    echo -e "${YELLOW}Setting up test environment...${NC}"
    mkdir -p "$TEST_STATE_DIR"
    mkdir -p "$TEST_RECORDINGS_DIR"
    mkdir -p "$TEST_VAULT_DIR"
    export MEETINGCTL_STATE_FILE="$TEST_STATE_DIR/current.json"
    export MEETINGCTL_PROCESS_QUEUE_FILE="$TEST_QUEUE_FILE"
    export MEETINGCTL_PROCESSED_JOBS_FILE="$TEST_PROCESSED_FILE"
    export RECORDINGS_PATH="$TEST_RECORDINGS_DIR"
    export VAULT_PATH="$TEST_VAULT_DIR"

    cat > "$TEST_NOTE_PATH" <<EOF
# Smoke Note
<!-- MINUTES_START -->
> _Pending_
<!-- MINUTES_END -->
<!-- DECISIONS_START -->
> _Pending_
<!-- DECISIONS_END -->
<!-- ACTION_ITEMS_START -->
> _Pending_
<!-- ACTION_ITEMS_END -->
<!-- TRANSCRIPT_START -->
> _Pending_
<!-- TRANSCRIPT_END -->
EOF

    echo -e "${GREEN}✓ Test environment created at $TEST_STATE_DIR${NC}\n"
}

# Cleanup test environment
cleanup_test_env() {
    echo -e "\n${YELLOW}Cleaning up test environment...${NC}"
    rm -rf "$TEST_STATE_DIR"
    echo -e "${GREEN}✓ Test environment cleaned${NC}"
}

# Test helper functions
run_test() {
    local test_name="$1"
    local test_cmd="$2"
    TESTS_TOTAL=$((TESTS_TOTAL + 1))

    echo -e "${BOLD}Test $TESTS_TOTAL: $test_name${NC}"

    if declare -F "$test_cmd" >/dev/null 2>&1; then
        if "$test_cmd"; then
            echo -e "${GREEN}✓ PASS${NC}\n"
            TESTS_PASSED=$((TESTS_PASSED + 1))
            return 0
        fi
    else
        if bash -lc "$test_cmd"; then
            echo -e "${GREEN}✓ PASS${NC}\n"
            TESTS_PASSED=$((TESTS_PASSED + 1))
            return 0
        fi
    fi
    echo -e "${RED}✗ FAIL${NC}\n"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    return 1
}

assert_json_field() {
    local json="$1"
    local field="$2"
    local expected="$3"
    local actual

    actual=$(echo "$json" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('$field', 'NULL'))")

    if [ "$actual" = "$expected" ]; then
        echo "  ✓ Field '$field' = '$expected'"
        return 0
    else
        echo "  ✗ Field '$field' expected '$expected', got '$actual'"
        return 1
    fi
}

assert_file_exists() {
    local filepath="$1"
    if [ -f "$filepath" ]; then
        echo "  ✓ File exists: $filepath"
        return 0
    else
        echo "  ✗ File not found: $filepath"
        return 1
    fi
}

assert_file_not_exists() {
    local filepath="$1"
    if [ ! -f "$filepath" ]; then
        echo "  ✓ File does not exist: $filepath"
        return 0
    else
        echo "  ✗ File exists but should not: $filepath"
        return 1
    fi
}

assert_file_contains() {
    local filepath="$1"
    local needle="$2"
    if grep -q -- "$needle" "$filepath"; then
        echo "  ✓ File contains '$needle': $filepath"
        return 0
    else
        echo "  ✗ File missing '$needle': $filepath"
        return 1
    fi
}

# === Test Suite ===

# Test 1: CLI availability
test_cli_available() {
    [ -x "$PYTHON_BIN" ]
}

# Test 2: Status when idle (no active recording)
test_status_idle() {
    local result
    result=$(meetingctl_cli status --json)
    assert_json_field "$result" "recording" "False" && \
    assert_json_field "$result" "meeting_id" "None" && \
    assert_json_field "$result" "title" "None"
}

# Test 3: Start recording with minimal args
test_start_minimal() {
    local result
    result=$(meetingctl_cli start --title "Test Meeting" --meeting-id "test-001" --note-path "$TEST_NOTE_PATH" --json)
    assert_json_field "$result" "recording" "True" && \
    assert_json_field "$result" "meeting_id" "test-001" && \
    assert_json_field "$result" "title" "Test Meeting"
}

# Test 4: Status shows active recording
test_status_active() {
    local result
    result=$(meetingctl_cli status --json)
    assert_json_field "$result" "recording" "True" && \
    assert_json_field "$result" "meeting_id" "test-001" && \
    assert_json_field "$result" "title" "Test Meeting"
}

# Test 5: State file exists
test_state_file_exists() {
    assert_file_exists "$MEETINGCTL_STATE_FILE"
}

# Test 6: Stop recording
test_stop_recording() {
    local result
    result=$(meetingctl_cli stop --json)
    assert_json_field "$result" "recording" "False" && \
    assert_json_field "$result" "meeting_id" "test-001" && \
    assert_json_field "$result" "processing_triggered" "True"
}

# Test 7: Status returns to idle after stop
test_status_idle_after_stop() {
    local result
    result=$(meetingctl_cli status --json)
    assert_json_field "$result" "recording" "False"
}

# Test 8: Process queue file created
test_process_queue_created() {
    assert_file_exists "$TEST_QUEUE_FILE"
}

test_prepare_processing_artifacts() {
    echo "fake wav" > "$TEST_RECORDINGS_DIR/test-001.wav"
    assert_file_exists "$TEST_RECORDINGS_DIR/test-001.wav"
}

test_process_queue_executes_pipeline() {
    local result
    result=$(meetingctl_cli process-queue --max-jobs 1 --json)
    assert_json_field "$result" "processed_jobs" "1" && \
    assert_json_field "$result" "failed_jobs" "0" && \
    assert_json_field "$result" "remaining_jobs" "0"
}

test_artifact_chain_outputs() {
    assert_file_exists "$TEST_RECORDINGS_DIR/test-001.txt" && \
    assert_file_exists "$TEST_RECORDINGS_DIR/test-001.mp3" && \
    assert_file_not_exists "$TEST_RECORDINGS_DIR/test-001.wav" && \
    assert_file_contains "$TEST_NOTE_PATH" "Decision" && \
    assert_file_contains "$TEST_NOTE_PATH" "mp3_path" && \
    assert_file_contains "$TEST_NOTE_PATH" "status: complete"
}

test_queue_drained() {
    if [ ! -f "$TEST_QUEUE_FILE" ]; then
        echo "  ✓ Queue file removed (drained)"
        return 0
    fi
    local lines
    lines=$(grep -c '.*' "$TEST_QUEUE_FILE" || true)
    if [ "$lines" = "0" ]; then
        echo "  ✓ Queue file empty"
        return 0
    fi
    echo "  ✗ Queue still has $lines item(s)"
    return 1
}

# Test 9: State file cleared after stop
test_state_cleared() {
    # State file may be deleted or contain empty state
    if [ -f "$MEETINGCTL_STATE_FILE" ]; then
        local state_content
        state_content=$(cat "$MEETINGCTL_STATE_FILE")
        if [ "$state_content" = "{}" ] || [ "$state_content" = "" ]; then
            echo "  ✓ State file cleared"
            return 0
        else
            echo "  ✗ State file not cleared: $state_content"
            return 1
        fi
    else
        echo "  ✓ State file deleted"
        return 0
    fi
}

# Test 10: Stop when no recording (error path)
test_stop_no_recording() {
    local result
    result=$(meetingctl_cli stop --json)
    assert_json_field "$result" "recording" "False" && \
    echo "$result" | grep -q "warning" && echo "  ✓ Warning message present"
}

# Test 11: Fallback platform handling
test_fallback_platform() {
    local result
    result=$(meetingctl_cli start --title "Test Fallback" --meeting-id "test-002" --platform "unknown-platform" --json)
    assert_json_field "$result" "fallback_used" "True" && \
    assert_json_field "$result" "platform" "system"
}

# Test 12: Stop fallback recording
test_stop_fallback() {
    local result
    result=$(meetingctl_cli stop --json)
    assert_json_field "$result" "recording" "False"
}

# Test 13: Duration tracking
test_duration_tracking() {
    # Start recording
    meetingctl_cli start --title "Duration Test" --meeting-id "test-003" --json > /dev/null

    # Wait 2 seconds
    sleep 2

    # Check status
    local result
    result=$(meetingctl_cli status --json)
    local duration
    duration=$(echo "$result" | python3 -c "import sys, json; print(json.load(sys.stdin).get('duration_human', ''))")

    # Duration should be "0m" or similar (not empty)
    if [ -n "$duration" ]; then
        echo "  ✓ Duration tracked: $duration"
        # Cleanup
        meetingctl_cli stop --json > /dev/null
        return 0
    else
        echo "  ✗ Duration not tracked"
        meetingctl_cli stop --json > /dev/null
        return 1
    fi
}

# Test 14: JSON output validity
test_json_validity() {
    local result
    result=$(meetingctl_cli status --json)

    # Validate JSON parses correctly
    echo "$result" | python3 -c "import sys, json; json.load(sys.stdin)" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "  ✓ JSON output is valid"
        return 0
    else
        echo "  ✗ JSON output is invalid"
        return 1
    fi
}

# Test 15: CLI help commands
test_help_commands() {
    meetingctl_cli --help > /dev/null 2>&1 && \
    meetingctl_cli start --help > /dev/null 2>&1 && \
    meetingctl_cli stop --help > /dev/null 2>&1 && \
    meetingctl_cli status --help > /dev/null 2>&1 && \
    echo "  ✓ All help commands work"
}

# === Run Tests ===

main() {
    setup_test_env
    trap cleanup_test_env EXIT
    if [ "$SMOKE_REAL_MACHINE" = "1" ]; then
        echo -e "${YELLOW}Running in real-machine mode (Audio Hijack commands enabled).${NC}"
    else
        export MEETINGCTL_RECORDING_DRY_RUN=1
        export MEETINGCTL_PROCESSING_TRANSCRIBE_DRY_RUN=1
        export MEETINGCTL_PROCESSING_SUMMARY_JSON='{"minutes":"Smoke summary","decisions":["Decision"],"action_items":["Action"]}'
        export MEETINGCTL_PROCESSING_CONVERT_DRY_RUN=1
        echo -e "${YELLOW}Running in local incremental mode (MEETINGCTL_RECORDING_DRY_RUN=1).${NC}"
    fi

    echo -e "${BOLD}=== Basic CLI Tests ===${NC}\n"
    run_test "CLI is available in PATH" test_cli_available
    run_test "Help commands work" test_help_commands

    echo -e "${BOLD}=== Happy Path: Start-Stop Flow ===${NC}\n"
    run_test "Status shows idle when no recording" test_status_idle
    run_test "Start recording with minimal args" test_start_minimal
    run_test "Status shows active recording" test_status_active
    run_test "State file created" test_state_file_exists
    run_test "Stop recording" test_stop_recording
    run_test "Status returns to idle after stop" test_status_idle_after_stop
    run_test "Process queue file created" test_process_queue_created
    run_test "Prepare processing artifacts" test_prepare_processing_artifacts
    run_test "Process queue executes real chain" test_process_queue_executes_pipeline
    run_test "Artifact chain produced (txt/mp3/note patch)" test_artifact_chain_outputs
    run_test "Queue drained after processing" test_queue_drained
    run_test "State cleared after stop" test_state_cleared

    echo -e "${BOLD}=== Error Path Tests ===${NC}\n"
    run_test "Stop when no recording shows warning" test_stop_no_recording

    echo -e "${BOLD}=== Feature Tests ===${NC}\n"
    run_test "Fallback platform handling" test_fallback_platform
    run_test "Stop fallback recording" test_stop_fallback
    run_test "Duration tracking works" test_duration_tracking
    run_test "JSON output is valid" test_json_validity

    echo -e "${BOLD}=== KM Contract Tests (E6-S2) ===${NC}\n"
    run_test "KM stop macro references stop JSON command and confirmation text" "PYTHONPATH=\"$PROJECT_ROOT/src\" \"$PYTHON_BIN\" -m pytest -q \"$PROJECT_ROOT/tests/test_km_macro_package.py::test_e6_s2_stop_macro_has_immediate_confirmation_path\""

    # Summary
    echo -e "\n${BOLD}=== Test Summary ===${NC}"
    echo -e "Total tests: $TESTS_TOTAL"
    echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"

    if [ $TESTS_FAILED -gt 0 ]; then
        echo -e "${RED}Failed: $TESTS_FAILED${NC}"
        echo -e "\n${RED}${BOLD}SMOKE TESTS FAILED${NC}"
        exit 1
    else
        echo -e "${GREEN}Failed: $TESTS_FAILED${NC}"
        echo -e "\n${GREEN}${BOLD}ALL SMOKE TESTS PASSED${NC}"
        exit 0
    fi
}

# Run if executed directly
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi
