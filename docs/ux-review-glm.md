# Lorewrite UX Review Report

## Executive Summary

Lorewrite is a well-architected TUI fiction writing app with clean separation between core logic and UI. However, the current design targets technical users who already understand its concepts. For fiction writers (non-programmers), discoverability and onboarding need substantial improvements.

## Priority 0 (Do Now)

### 1. First-Run Tour (Onboarding)

**Problem**: New users see only the launch screen and help screen; no guided flow introduces core concepts.
**Why it matters**: Writers need to understand the `[[link]]` concept and their project structure immediately.
**Fix**: 
- Add a one-time tour modal on first launch (track in recents.json)
- 4 screens covering: project structure, markdown editing, wiki-links, entity notes
- Each screen shows only one concept with a concrete example
- ESC or space to advance,突出 的 actual UI elements (take control of the cursor)
**Files**: `tui/launch.py` (TourScreen modal), `core/recents.py` (tour state), `tui/app.py` (tour trigger)

### 2. Command Palette Categorization

**Problem**: Users report palette feels "just like a search bar" - flat list, no visual grouping
**Why it matters**: The palette is the primary action hub; without visual cues, writers can't learn capabilities
**Fix**:
- Add section headers (SCENES, ENTITIES, LINKS, ACTIONS)
- Color-code categories for quick recognition
- Add icons next to items using Unicode symbols (📄 for scenes, 👥 for entities, 🔗 for links, ⚙️ for actions)
- Show fewer items per category initially with "more..." reveal
**Files**: `tui/commands.py` (Provider categories, markups), `tui/app.py` (palette CSS styling)

### 3. Focus/Writer Mode

**Problem**: Persistent widgets distract from creative flow
**Why it matters**: Writers need to minimize visual clutter during immersive writing sessions
**Fix**:
- Add `ctrl+enter` to toggle Writer Mode: hide sidebar + panel + header + footer
- Pad editor with 2-character margins on both sides in Writer Mode
- Float minimal overlay showing current scene title and word count
- Any command palette action temporarily exits Writer Mode
**Files**: `tui/app.py` (Writer Mode state, bind), CSS overrides, optional overlay widget

### 4. Empty State Guidance

**Problem**: Empty panels give passive instructional text with no clear next action
**Why it matters**: Empty states are teaching moments; passive text is often ignored
**Fix**:
- Entity panel: when no link under cursor, show "Select characters in your text with `[[Name]]`" with live cursor following guidance
- Recent projects list: when empty, show a highlighted "New Project" button with example
- Scene list: highlight creation path when first launched
**Files**: `tui/panels.py` (empty state), `tui/launch.py` (empty list styling)

## Priority 1 (Next Sprint)

### 5. Quick Scene Navigation

**Problem**: No rapid way to flip between scenes during editing
**Why it matters**: Writers frequently reference earlier scenes for continuity
**Fix**:
- Add `ctrl+[` and `ctrl+]` to move to previous/next scene
- Visual flashing of sidebar scene list on scene change
- Scene title appears briefly in center-screen when switching
**Files**: `tui/app.py` (actions), CSS for flash animation

### 6. Scene Search & Filter

**Problem**: Long scene lists become unmanageable in sidebar
**Why it matters**: Novels often have 50+ scenes; linear navigation is painful
**Fix**:
- Add filter field above each sidebar list
- Real-time filtering as you type
- Preserve order when filter active
- Small visual element showing count/filtered count
**Files**: `tui/sidebar.py` (search widgets), CSS styling

### 7. Visual Editorial Feedback

**Problem**: Minimal status indicators leave users uncertain about system state
**Why it matters**: Writers need reassurance that their work is being saved and tracked
**Fix**:
- Add autosave indicator (● when dirty) to status bar
- Show "Saved" with timestamp in status for 5 seconds after explicit save
- Rebuild index shows progress: "Rebuilding... X/Y files"
- Word count includes chapter/scene totals not just current file
**Files**: `tui/app.py` (status updates), CSS for indicators

### 8. Enhanced Typography & Margins

**Problem**: Default Textual typography isn't optimized for long-form reading
**Why it matters**: Comfortable reading reduces fatigue during long writing sessions
**Fix**:
- Add font height preferences to project.toml (1.4 to 2.0 line height)
- Editor side padding controls (0-4 characters)
- Focus character highlighting on current line (subtle background)
- Make line numbers optional via setting
**Files**: `tui/editor.py` (render hook), `core/project.py` (preferences), CSS settings

## Priority 2 (Future)

### 9. Mouse-Driven Navigation

**Problem**: Limited mouse interactions force heavy keyboard reliance
**Why it matters**: Different writers have different comfort levels with keyboard vs mouse
**Fix**:
- Right-click menu on sidebar items (rename, delete, move)
- Double-click editor words to select whole words
- Hover tooltips for unresolved links showing "Create note"
- Drag reorderable scene list (confirm dialog)
**Files**: `tui/sidebar.py` (click handlers), `tui/editor.py` (select hook), additional CSS

### 10. Project Structure Visualization

**Problem**: Writers can't easily grasp their manuscript's narrative flow
**Why it matters**: Understanding story pace and structure helps with revision
**Fix**:
- Optional view showing scenes as histogram of word counts
- Chapter grouping (e.g., every 5 scenes form a chapter)
- Color-coded scene list by mentions density
**Files**: New `tui/outline.py` panel, sidebar toggles

### 11. Quick Entity Reference Cards

**Problem**: Opening full entity notes for quick checks disrupts flow
**Why it matters**: Writers need immediate context without leaving the scene
**Fix**:
- Alt-hover over links shows mini card with entity name, type, and first 100 characters
- Cards dismiss on any key press or after 10 seconds
- Supports aliases detection
**Files**: `tui/editor.py` (hover hook), new simple card widget

### 12. Writing Session Dashboard

**Problem**: No visibility into writing progress and patterns
**Why it matters**: Motivation and routine tracking help with consistency
**Fix**:
- Session word count with grand total
- Time spent writing today
- Days since last scene created
- Exportable simple progress report
**Files**: New `tui/session.py` module, optional status bar element

## Technical Implementation Notes

- All CSS changes should respect theme switching (test with both light/dark)
- New widgets must properly handle focus transitions
- Mouse additions should gracefully degrade if terminal lacks mouse support
- Preferences should be stored per-project, not globally
- All new keybindings must be added to the help screen automatically

## Recommended Implementation Order

1. Start with command palette categorization - highest impact, lowest risk
2. Add Writer Mode - critical for the core writing experience
3. Implement first-run tour - helps with every new user
4. Quick scene navigation - improves daily workflow
5. Progress through remaining P1 items before considering P2 features

The current codebase is well-structured for these changes. All UI components are already separated with clear messaging patterns. The spec's focus on plain text and minimal machine readability should remain paramount in any UI additions.