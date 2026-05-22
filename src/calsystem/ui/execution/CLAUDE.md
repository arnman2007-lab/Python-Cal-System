# Execution Tab - Developer Notes

## Manual Setup Feature

### Overview
The `manual_setup` flag allows test points to skip calibrator output for physical configurations (shorts, nulls, button presses, etc.). The calibrator is put into STANDBY mode and no OUTPUT/OPERATE commands are sent.

### Architecture

#### Data Flow
1. **Database** → `test_points.manual_setup` (BOOLEAN)
2. **CSP Export** → `TestPointData.manual_setup` (procedure_data.py)
3. **CSP File** → JSON: `"manual_setup": true/false`
4. **CSP Import** → `TestPointData.manual_setup` (csp_file.py)
5. **Execution Load** → `tp['manual_setup']` dict entry (execution_tab.py)
6. **Execution Logic** → Checks `tp.get('manual_setup')` to skip calibrator

#### Key Functions (execution_tab.py)

**`_update_current_display(row)`** - Called when navigating to a test point
- Lines ~3590-3622: Manual setup handling
- Puts calibrator in STANDBY if manual_setup=True
- For pass/fail: Calls `_set_calibrator_output()` to trigger dialog
- For measurements: Shows manual setup dialog, does NOT call `_set_calibrator_output()`

**`_set_calibrator_output(tp)`** - Sends calibrator commands OR executes special test flows
- Lines ~3831-3890: Main calibrator output logic
- CRITICAL: Contains `_execute_pass_fail_test()` call for pass/fail tests
- When manual_setup=True:
  - Puts calibrator in STANDBY (again, for safety)
  - For pass/fail: Falls through to execute pass/fail dialog
  - For other types: Returns early, skips calibrator commands
- When manual_setup=False:
  - Sends OUTPUT/OPERATE commands normally

**`_on_get_remote_reading()`** - Called when "Get Remote" button clicked
- Lines ~4235+: Remote reading via VISA
- Must check manual_setup and put calibrator in STANDBY
- Bug history: Initially missing manual_setup check (fixed in 6e02e09)

**`_execute_pass_fail_test(tp)`** - Shows PassFailDialog
- Lines ~4515+: Pass/fail test execution
- Called FROM `_set_calibrator_output()` - this is critical!
- Shows red FAIL / green PASS buttons
- Handles both manual and DMM-automated pass/fail tests

### Common Bugs & Fixes

#### Bug #1: PassFailDialog Not Showing for Manual Setup Tests
**Symptoms:**
- Pass/fail test with manual_setup=True shows normal reading input
- No red/green FAIL/PASS buttons appear
- User has to manually type a value

**Root Cause:**
`_set_calibrator_output()` was never called for pass/fail tests with manual_setup=True, so `_execute_pass_fail_test()` never ran.

**Location:** `_update_current_display()` around line 3590
**Fix:** For pass/fail with manual_setup, MUST call `_set_calibrator_output()`
```python
if test_type == 'pass_fail':
    self._set_calibrator_output(tp)  # Must call this!
else:
    # Show manual setup dialog for measurements
```

**Commits:** 6f9a207, 6267f8a, 88e3901

---

#### Bug #2: Calibrator Activates Despite Manual Setup
**Symptoms:**
- Test point has manual_setup=True in database
- Calibrator still sends OUTPUT/OPERATE commands
- Calibrator not in STANDBY

**Possible Causes:**

**A) CSP Export Missing Field**
- **File:** `src/calsystem/procedures/migration.py`
- **Function:** `_convert_test_point()`
- **Fix:** Add `manual_setup` to TestPointData initialization
- **Commit:** 9033ac1

**B) CSP Loading Missing Field**
- **File:** `src/calsystem/ui/execution/execution_tab.py`
- **Function:** `_load_test_points_from_csp()`
- **Fix:** Add `"manual_setup": tp.manual_setup or False` to dict
- **Commit:** 11c8039

**C) Get Remote Button Not Checking**
- **File:** `src/calsystem/ui/execution/execution_tab.py`
- **Function:** `_on_get_remote_reading()`
- **Fix:** Add manual_setup check at start of function, put calibrator in STANDBY
- **Commit:** 6e02e09

---

#### Bug #3: Double Dialogs for Pass/Fail
**Symptoms:**
- Pass/fail test shows manual setup dialog
- Then shows pass/fail dialog
- User sees two dialogs

**Root Cause:**
Both `_update_current_display()` (manual setup dialog) and `_execute_pass_fail_test()` (pass/fail dialog) were showing dialogs.

**Location:** `_update_current_display()` around line 3607
**Fix:** Skip manual setup dialog for pass/fail tests
```python
if test_type != 'pass_fail':
    # Only show manual setup dialog for measurements
    manual_prompt = tp.get('manual_setup_prompt')...
```

**Commit:** 88e3901

---

#### Bug #4: Pass/Fail Test Skipped, Next Test Runs Twice
**Symptoms:**
- Pass/fail test doesn't execute
- Navigation advances to next test
- Next test point runs twice

**Root Cause:**
`_set_calibrator_output()` returned early for manual_setup=True before reaching pass/fail execution code.

**Location:** `_set_calibrator_output()` around line 3850
**Fix:** Don't return early for pass/fail tests with manual_setup
```python
if tp.get('manual_setup'):
    # Put calibrator in STANDBY...
    if test_type != 'pass_fail':
        return  # Only return for non-pass/fail
    # Fall through to pass/fail execution below
```

**Commit:** 6267f8a

---

### Test Type Flow Chart

```
Test Point Loaded → _update_current_display(row)
                            ↓
                   Check manual_setup?
                            ↓
                    ┌───────┴───────┐
                    │               │
                 YES (manual)    NO (normal)
                    │               │
              Put CAL in STANDBY    │
                    │               │
              Check test_type       │
                    │               │
         ┌──────────┴──────────┐   │
         │                     │   │
    pass_fail            measurement│
         │                     │   │
    Call _set_calibrator_output()  │
         │              Show manual│
         │              setup dialog│
         │                     │   │
         └──────────┬──────────┘   │
                    │               │
              _set_calibrator_output(tp)
                    │
              Check manual_setup?
                    │
         ┌──────────┴──────────┐
         │                     │
      YES (manual)          NO (normal)
         │                     │
    Show status msg      Send OUTPUT cmd
    Skip calibrator      Send OPERATE cmd
         │                     │
    Check test_type            │
         │                     │
    pass_fail?                 │
         │                     │
    YES  │  NO                 │
         │   │                 │
    Continue │ Return          │
         │   │                 │
         └───┼─────────────────┘
             │
    _execute_pass_fail_test(tp)
             │
    Show PassFailDialog
```

### Critical Rules

1. **Pass/fail tests MUST call `_set_calibrator_output()`** even with manual_setup=True
   - This is where `_execute_pass_fail_test()` is called
   - Skipping this call means no PassFailDialog

2. **Manual setup checks must happen in BOTH places:**
   - `_update_current_display()` - Initial setup when navigating
   - `_set_calibrator_output()` - Safety check, skip calibrator commands

3. **CSP export/import must include manual_setup:**
   - `migration.py` → `_convert_test_point()` - Export
   - `execution_tab.py` → `_load_test_points_from_csp()` - Import
   - `procedure_data.py` → TestPointData class - Data structure

4. **All calibrator command paths must check manual_setup:**
   - `_set_calibrator_output()` - Main path
   - `_on_get_remote_reading()` - Get Remote button
   - `_execute_passfail_preconditioning()` - Already protected via `_set_calibrator_output()`

### Files to Check When Debugging

1. **execution_tab.py** - Main execution logic
   - `_update_current_display()` - Navigation, manual setup dialogs
   - `_set_calibrator_output()` - Calibrator commands, pass/fail trigger
   - `_on_get_remote_reading()` - Get Remote button
   - `_load_test_points_from_csp()` - CSP loading

2. **migration.py** - CSP export
   - `_convert_test_point()` - Database → CSP conversion

3. **procedure_data.py** - Data structures
   - `TestPointData` class - manual_setup field definition
   - `to_dict()` and `from_dict()` - Serialization

4. **procedures_tab.py** - Procedure editor
   - Manual setup checkbox UI
   - Auto-save functionality

### Debugging Tips

**If calibrator activates when it shouldn't:**
1. Check CSP file: Does it have `"manual_setup": true`?
   ```bash
   unzip -p procedure.csp procedure.json | grep -A5 manual_setup
   ```
2. Check `_load_test_points_from_csp()` - Is field copied to dict?
3. Check `_set_calibrator_output()` - Is manual_setup checked?
4. Check `_on_get_remote_reading()` - Is manual_setup checked?

**If PassFailDialog doesn't show:**
1. Check test_type in CSP: Is it `"pass_fail"`?
2. Check `_update_current_display()` - Does it call `_set_calibrator_output()` for pass/fail?
3. Check `_set_calibrator_output()` - Does it fall through to `_execute_pass_fail_test()` for manual_setup pass/fail?
4. Add debug logging:
   ```python
   logger.debug(f"Test type: {test_type}, manual_setup: {tp.get('manual_setup')}")
   ```

**If double dialogs appear:**
1. Check `_update_current_display()` - Should skip manual setup dialog for pass/fail
2. Check `_execute_pass_fail_test()` - Should only show once

### Related Commits
- f29ce81 - Skip section commands when manual setup enabled
- 6e02e09 - Prevent calibrator activation during manual setup mode
- d6272a6 - Add manual_setup fields to CSP export/import (dataclass)
- 9033ac1 - Add manual_setup to CSP export (migration.py)
- 11c8039 - Add manual_setup to CSP loading (execution_tab.py)
- 88e3901 - Skip manual setup dialog for pass/fail tests
- 6267f8a - Allow pass/fail tests to execute with manual_setup enabled
- 6f9a207 - Call _set_calibrator_output for pass/fail with manual_setup
- 3f8e891 - Add auto-save system to procedure editor
