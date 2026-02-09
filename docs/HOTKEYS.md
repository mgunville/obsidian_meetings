# Hotkey Reference

Version: 0.1
Platform: macOS with Keyboard Maestro

## Default Hotkeys

| Action | Default Hotkey | Symbol | Notes |
|--------|---------------|---------|-------|
| **Start Meeting** | Control+Command+S | `⌃⌘S` | Primary workflow |
| **Stop Meeting** | Control+Command+Shift+S | `⌃⌘⇧S` | Triggers post-processing |
| **Check Status** | Control+Option+S | `⌃⌥S` | Non-intrusive check |
| **Ad-hoc Recording** | Control+Command+Option+S | `⌃⌘⌥S` | No calendar required |
| **Auto-detect** | (Application trigger) | — | Disabled by default |

## Hotkey Design Rationale

### Mnemonics
- **S** = Session/Start/Status/Stop
- All macros use `S` as base key for consistency
- Modifier combinations distinguish actions

### Modifier Patterns
- `⌃⌘` = Primary actions (Start)
- `⌃⌘⇧` = Primary + Shift = Opposite (Stop)
- `⌃⌥` = Query/Status (non-destructive)
- `⌃⌘⌥` = Advanced/Ad-hoc

### Avoiding Conflicts

**System shortcuts to avoid:**
- `⌘S` (Save) - globally used
- `⌘⇧S` (Save As) - globally used
- `⌃⌘Space` (Character Viewer)
- `⌃⌘Q` (Lock Screen)

**App shortcuts to avoid:**
- Zoom: `⌘⇧A` (Mute), `⌘⇧V` (Video)
- Teams: `⌘⇧M` (Mute), `⌘⇧O` (Video)
- Chrome: `⌘T` (New Tab), `⌘W` (Close Tab)

## Customizing Hotkeys

### How to Change Hotkeys

1. Open **Keyboard Maestro Editor**
2. Navigate to **Meeting Automation** macro group
3. Select the macro you want to customize
4. Double-click the **Hot Key Trigger** at bottom
5. Press your desired key combination
6. Click **OK** to save

### Recommended Alternatives

#### Option A: Function Keys
Good for dedicated meeting workflow:

| Action | Alternative |
|--------|-------------|
| Start | `F13` |
| Stop | `F14` |
| Status | `F15` |
| Ad-hoc | `F16` |

**Pros:** No conflicts, easy to remember, physical keys
**Cons:** MacBook touch bar remapping may be needed

#### Option B: Hyper Key
Use [Karabiner-Elements](https://karabiner-elements.pqrs.org) to create Hyper key (Caps Lock → ⌃⌥⌘⇧):

| Action | Alternative |
|--------|-------------|
| Start | `Hyper+S` |
| Stop | `Hyper+X` |
| Status | `Hyper+I` |
| Ad-hoc | `Hyper+A` |

**Pros:** Dedicated modifier, no conflicts
**Cons:** Requires Karabiner-Elements setup

#### Option C: Palette Trigger
Use Keyboard Maestro palette instead of hotkeys:

1. Change all macro triggers to **No Trigger**
2. Add **Palette Trigger** to macro group
3. Set palette hotkey (e.g., `⌃⌘M`)
4. Press palette hotkey, then select action

**Pros:** Single hotkey to remember, visual menu
**Cons:** Two-step activation

## Conflict Resolution

### Finding Conflicts

1. **System Preferences**
   - System Preferences > Keyboard > Shortcuts
   - Review all categories for conflicts

2. **Keyboard Maestro**
   - View > Show Conflict Palette
   - Lists all conflicting hotkeys across apps

3. **App-specific shortcuts**
   - Check Zoom, Teams, Chrome settings
   - Disable or remap conflicting shortcuts

### Handling Conflicts

If your chosen hotkey conflicts:

1. **Disable system shortcut** (if unused)
   - System Preferences > Keyboard > Shortcuts
   - Uncheck conflicting item

2. **Change app shortcut** (if app-specific)
   - Open app preferences
   - Remap or disable shortcut

3. **Use scope in Keyboard Maestro**
   - Edit macro trigger
   - Set "Available in:" to specific apps
   - Hotkey only works in those apps

## Testing Your Hotkeys

After customization:

1. **Test each macro individually**
   ```bash
   # Verify CLI still works
   source ~/.venv-meetingctl/bin/activate
   meetingctl status --json
   ```

2. **Test in different apps**
   - Try hotkeys in Zoom, Teams, Chrome, Obsidian
   - Ensure no conflicts or unexpected behavior

3. **Test Do Not Disturb scenarios**
   - Enable DND
   - Verify notifications still appear (or adjust settings)

## Accessibility Notes

### For users with limited keyboard use

1. **Stream Deck integration** (Future)
   - Buttons can trigger KM macros
   - Visual feedback on hardware

2. **Voice Control** (macOS built-in)
   - "Press Control Command S"
   - Requires voice control calibration

3. **BTT (BetterTouchTool) gestures** (Future)
   - Trackpad gestures → KM macros
   - Touchbar buttons → macros

### For users who prefer mouse

1. **Add to menu bar**
   - Use apps like Bartender or Hidden Bar
   - Or create custom menu bar app (Future)

2. **Keyboard Maestro Status Menu**
   - KM Editor > Preferences > General
   - Enable "Show Status Menu"
   - Add macros to status menu

## Reference: Keyboard Maestro Triggers

The Meeting Automation macros use these trigger types:

### Hot Key Triggers
- Most common for meeting workflows
- Instant activation
- Requires memorization

### Palette Triggers
- Alternative to multiple hotkeys
- Visual selection menu
- Good for discovery

### Application Triggers (Auto-detect only)
- Activates when app launches/activates
- Used in optional auto-detect macro
- Disabled by default to avoid disruption

## Modifier Key Reference

| Symbol | Name | Mac Keyboard |
|--------|------|--------------|
| `⌘` | Command | cmd |
| `⌃` | Control | control |
| `⌥` | Option | option/alt |
| `⇧` | Shift | shift |
| `⇪` | Caps Lock | caps lock |
| `Fn` | Function | fn |

## Getting Help

If hotkeys stop working:

1. Check Keyboard Maestro is running
2. Verify accessibility permissions (System Preferences > Security & Privacy)
3. Look for conflicts: View > Show Conflict Palette
4. Test with `meetingctl` CLI directly to isolate issue
5. Review Keyboard Maestro Engine log: Help > Open Logs Folder
