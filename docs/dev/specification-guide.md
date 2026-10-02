# Lorewrite Specification Guide: M3–M8 Implementation

Last updated: 2026-09-27  
Purpose: A parallel-execution roadmap for AI coding agents implementing the remaining milestones of lorewrite.

## 1. Architecture & Parallel Execution Framework

### 1.1 Core Interface Contracts

These contracts MUST be respected by all implementations:

**Core Module APIs (`src/lorewrite/core/`)**:
- `entities.py`: `Entity` dataclass, `load_entity()`, `save_entity()`, `add_alias()`
- `project.py`: `Project` dataclass, `create()`, `open()`, scene/entity methods
- `index.py`: `Index` class, SQLite operations
- `links.py`: `Link` dataclass, `find_links()`, `link_at()`, offset utilities
- `settings.py`: `load_settings()`, `save_settings()`, `get()`, `set()`
- `recents.py`: `Recent` dataclass, `load/add/remove_recents()`

**AI Client Interface (`src/lorewrite/ai/`)**:
- `client.py`: `make_client()`, `get/set_api_key()`, model constants
- `links.py`: `suggest_links()` (signature already fixed)

**TUI Widget Patterns**:
- Modal screens inherit from `ModalScreen[T]` and use `compose()` + bindings
- Direct widget refs stored as `self._widget: Widget | None` in `app.py`
- All async work uses `@work(exclusive=True)` workers
- Rich markup must be wrapped in `Text()` for dynamic user content

### 1.2 Parallel Workstream Decomposition

```
M3 (Lore/Continuity + Contextual Tracker)
├── M3-Core: Continuity data structures + validation rules
├── M3-AI: Lore checking prompts + schemas
├── M3-TUI: Review modal + entity note accumulation
└── M3-Tests: Unit + integration tests

M4 (Style Tracker + Expansion)
├── M4-Core: Style guide storage + placeholder parsing
├── M4-AI: Style learning + generation prompts
├── M4-TUI: Expansion UI + visual AI text marking
└── M4-Tests: Mock generation + UI tests

M6 (Writing Aids)
├── M6-Core: Session tracking + spell/grammar integration
├── M6-TUI: Timer UI + session stats page
└── M6-Tests: Session persistence tests

M7 (Organization + Export)
├── M7-Core: LaTeX template system + export pipeline
├── M7-TUI: Drag-reorder + export modal
└── M7-Tests: Template rendering tests

M8 (Exploratory)
├── M8-Core: Entity system extension for figures/tables/equations
├── M8-TUI: Screenplay mode UI
└── M8-Tests: Specialized entity tests
```

### 1.3 File Ownership Boundaries

**Core-logic team**: `src/lorewrite/core/` (all modules), `src/lorewrite/ai/` (new modules)
**TUI team**: `src/lorewrite/tui/` (all except `app.py` integration points)
**Tests team**: `tests/` (all new test files, conftest updates)
**Integration team**: `src/lorewrite/tui/app.py` (integration points only)

### 1.4 Merge Strategy & Review Gates

1. **Sequential milestone merging**: M3→M4→M6→M7→M8 (never parallel milestones)
2. **Within-milestone parallel merging**: Core→AI→TUI→Tests (dependency order)
3. **Integration gate**: `app.py` changes only merged after all module contracts are validated
4. **Final gate**: Run `pytest` + `jev review` before reporting milestone complete

---

## 2. M3: Lore/Continuity Checking + Contextual Tracker

### 2.1 Core Logic (M3-Core)

**New file: `src/lorewrite/core/continuity.py`**

```python
"""Continuity checking: contradiction detection, note accumulation, waivers.

Data structures:
- contradiction Schema: {type, severity, evidence, suggested_fix, entities}
- waiver store: .lorewrite/waivers.json
- entity note accumulation: insert "Canon:" section markers
"""

# Key functions to implement:
def check_scene(text: str, entities: list[Entity], notes: dict[str, Entity]) -> list[dict]:
    """Run Jev pre-screen, then strong model checking. Returns contradictions."""
    
def accumulate_notes(scene: Path, entities: list[Entity], updates: dict) -> None:
    """AI-suggested updates to entity notes; author review."""
    
def load_waivers(project_root: Path) -> dict[str, set]:
    """Load waived contradiction IDs per entity/project."""
    
def save_waiver(project_root: Path, contradiction_id: str) -> None:
    """Persist a waived flag so it's not reported again."""
```

**New file: `src/lorewrite/core/jev_interface.py`**

```python
"""Jev integration: cheap pre-screening for contradictions.

Uses ~/.config/jev/jev.py to classify potential contradictions before
spending tokens on the strong model.
"""

def pre_screen_contradictions(text: str, entities: list[Entity]) -> list[tuple]:
    """Returns: [(type, severity, evidence_snippet)] for Jev validation."""
```

### 2.2 AI Integration (M3-AI)

**New file: `src/lorewrite/ai/continuity.py`**

```python
"""AI-powered continuity checking: prompts and structured output.

Uses strong models (Claude-3.5-Sonnet, GPT-4) with structured JSON output
validated app-side before UI rendering.
"""

CONTRADICTION_SCHEMA = {
    "type": "object",
    "properties": {
        "contradictions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string", "enum": [
                        "physical_attribute", "timeline", "character_knowledge",
                        "object_custody", "present_absent", "spelling_drift"
                    ]},
                    "severity": {"type": "string", "enum": ["error", "warning", "note"]},
                    "entity": {"type": "string"},
                    "evidence": {"type": "string"},
                    "suggested_fix": {"type": "string"}
                },
                "required": ["id", "type", "severity", "entity", "evidence", "suggested_fix"]
            }
        }
    }
}

SYSTEM_PROMPT = """\
You identify continuity contradictions in fiction manuscripts. Given:
1. All entity notes (character/place attributes established in prior scenes)
2. The current scene text

Find contradictions where the current scene violates established canon:
- Physical attributes that changed (eye color, height, injuries)
- Timeline impossibilities (travel time, event order)
- Character knowing things they shouldn't yet
- Objects being in the wrong place or custody
- Characters acting as present/absent inconsistently
- Name spelling drift across scenes

Be precise with line references. Don't flag intentional ambiguity.
"""

ACCUMULATION_SCHEMA = {
    "type": "object",
    "properties": {
        "updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "existing_canon": {"type": "string"},
                    "new_canon": {"type": "string"},
                    "justification": {"type": "string"}
                },
                "required": ["entity", "existing_canon", "new_canon", "justification"]
            }
        }
    }
}
```

### 2.3 TUI Integration (M3-TUI)

**New file: `src/lorewrite/tui/continuityscreen.py`**

```python
"""Continuity review modal: list contradictions, waive, jump to evidence."""

class ContinuityScreen(ModalScreen[dict[str, bool]]):
    """Review contradictions. Returns dict of waived IDs."""
    BINDINGS = [
        Binding("space", "toggle_waive", "Waive"),
        Binding("enter", "jump_to_evidence", "Jump to line"),
        Binding("escape", "done", "Done")
    ]
    
    def __init__(self, contradictions: list[dict]):
        self._contradictions = contradictions
        self._waived: set[str] = set()
```

**New file: `src/lorewrite/tui/notes accumulator.py`**

```python
"""Entity note accumulation: apply AI-suggested updates with author review."""

class NoteAccumulatorScreen(ModalScreen[list[dict] | None]):
    """Review proposed canon updates to entity notes."""
```

**Changes to `src/lorewrite/tui/app.py`**:

```python
# In LorewriteApp class:
def action_check_continuity(self) -> None:
    """Check current scene for contradictions."""
    
def action_check_manuscript(self) -> None:
    """Check entire manuscript for contradictions (slow operation)."""
    
def accumulate_entity_notes(self) -> None:
    """After scene review, offer AI-suggested note updates."""
```

### 2.4 Testing Strategy (M3-Tests)

**New file: `tests/test_continuity.py`**

```python
"""Core continuity logic tests, Jev integration mocked."""

def test_contradiction_detection():
    """Physical attribute change, timeline error, etc."""
    
def test_waiver_persistence():
    """Waived IDs remembered across sessions."""

def test_entity_accumulation():
    """Note updates applied correctly."""
```

**New file: `tests/test_ai_continuity.py`**

```python
"""AI continuity checking: mock model responses."""

def test_structured_output_parsing():
    """Valid schema adherence."""

def test_jev_pre_screen():
    """Jev filtering before expensive calls."""

async def test_continuity_flow_ui():
    """Full flow: check → review → waive → jump."""
```

---

## 3. M4: Style Tracker + Expansion

### 3.1 Core Logic (M4-Core)

**New file: `src/lorewrite/core/style.py`**

```python
"""Style guide learning and placeholder expansion.

Style guide stored in .lorewrite/style.md with structured sections:
- prose patterns
- dialogue conventions
- vocabulary preferences
- sentence structure
"""

def extract_style_guide(project: Project, limit_scenes: int = 10) -> str:
    """Sample recent scenes to build style guide template."""
    
def update_style_guide(project: Project, additions: str) -> None:
    """Incorporate author-approved style additions."""
    
def parse_expansion_placeholders(text: str) -> list[tuple[int, int, str]]:
    """Find {{expand: instruction}} markers in text."""
    
def apply_expansion(text: str, expansions: list[tuple[int, int, str]], replacements: list[str]) -> str:
    """Replace placeholder ranges with AI-generated text."""
```

### 3.2 AI Integration (M4-AI)

**New file: `src/lorewrite/ai/style.py`**

```python
"""Style-aware generation: learn author's voice, generate in style."""

STYLE_LEARNING_SCHEMA = {
    "type": "object",
    "properties": {
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": [
                        "prose", "dialogue", "vocabulary", "sentence_structure",
                        "pacing", "description_depth"
                    ]},
                    "pattern": {"type": "string"},
                    "examples": {"type": "array", "items": {"type": "string"}}
                }
            }
        }
    }
}

GENERATION_SCHEMA = {
    "type": "object",
    "properties": {
        "generated_text": {"type": "string"},
        "style_notes": {"type": "string"}
    }
}
```

### 3.3 TUI Integration (M4-TUI)

**New file: `src/lorewrite/tui/expansionprompt.py`**

```python
"""Modal for AI expansion: instruction input + generation."""

class ExpansionPromptScreen(ModalScreen[str | None]):
    """Collect instruction from user; returns instruction or None."""
```

**New file: `src/lorewrite/tui/aitextreview.py`**

```python
"""Review AI-generated text: colored, diff view, accept/reject."""

class AITextReviewScreen(ModalScreen[bool]):
    """Show AI text in distinct color; allow accept/reject."""
```

**Changes to `src/lorewrite/tui/editor.py`**:

```python
class LinkedTextArea(TextArea):
    # Add AI text marking support:
    def mark_ai_text(self, start: int, end: int, ai_generated: bool = True) -> None:
        """Mark a range as AI-generated for visual distinction."""
```

### 3.4 Testing Strategy (M4-Tests)

**New file: `tests/test_style.py`** - Style guide extraction and updates

**New file: `tests/test_ai_style.py`** - Style learning and generation mocks

**New file: `tests/test_expansion_ui.py`** - Full expansion flow UI tests

---

## 4. M6: Writing Aids

### 4.1 Core Logic (M6-Core)

**New file: `src/lorewrite/core/session.py`**

```python
"""Session tracking for writing metrics."""

@dataclass
class SessionStats:
    words_today: int
    session_time: timedelta
    average_words_per_hour: float
    current_streak: int
    
def track_session(session_dir: Path, words: int) -> SessionStats:
    """Update session metrics and return stats."""
```

**New file: `src/lorewrite/core/spellcheck.py`**

```python
"""Spell/grammar checking integration."""

def check_spelling(text: str, lang: str = "en_US") -> list[tuple[int, int, str]]:
    """Return misspellings with suggested corrections."""
    
def check_grammar(text: str) -> list[tuple[int, int, str]]:
    """Optional LLM grammar check (on-demand, not live)."""
```

### 4.2 TUI Integration (M6-TUI)

**New file: `src/lorewrite/tui/focustimer.py`**

```python
"""Focus timer for writing sprints."""

class FocusTimer(Widget):
    """Countdown timer in status bar during writing sprints."""
```

**New file: `src/lorewrite/tui/sessionstats.py`**

```python
"""Session statistics read-only screen."""

class SessionStatsScreen(ModalScreen[None]):
    """Show today's writing metrics and streaks."""
```

**Changes to `src/lorewrite/tui/app.py`**:

```python
# Add timer widget refs to status bar
def action_start_sprint(self) -> None:
    """Start a timed writing sprint."""
    
def action_session_stats(self) -> None:
    """Show session statistics screen."""
```

### 4.3 Testing Strategy (M6-Tests)

**New file: `tests/test_session.py`** - Session tracking and streaks

**New file: `tests/test_spellcheck.py`** - Spell/grammar integration

**New file: `tests/test_focus_timer.py`** - Timer UI tests

---

## 5. M7: Organization + Export

### 5.1 Core Logic (M7-Core)

**New file: `src/lorewrite/core/export.py`**

```python
"""LaTeX export pipeline with template system."""

@dataclass
class ExportConfig:
    template: str  # "book" or "manuscript"
    include_frontmatter: bool = True
    font_size: str = "12pt"
    line_spacing: str = "single"

def compile_manuscript(project: Project, config: ExportConfig) -> str:
    """Return the full manuscript as LaTeX string."""
    
def render_latex(source: str) -> bytes:
    """Compile LaTeX to PDF; returns PDF bytes."""
```

**Template files in `src/lorewrite/templates/`**:
- `book.tex.jinja2` - Book layout template
- `manuscript.tex.jinja2` - Review layout template

### 5.2 TUI Integration (M7-TUI)

**New file: `src/lorewrite/tui/exportmodal.py`**

```python
"""Export configuration and progress modal."""

class ExportScreen(ModalScreen[Path | None]):
    """Configure and run export; returns PDF path or None."""
```

**Changes to `src/lorewrite/tui/sidebar.py`**:

```python
# Add drag-reorder support for scenes
def on_mouse_drag(self, event: MouseDrag) -> None:
    """Handle scene drag-reordering with visual feedback."""
```

### 5.3 Testing Strategy (M7-Tests)

**New file: `tests/test_export.py`** - LaTeX compilation and templates

**New file: `tests/test_drag_reorder.py`** - Scene reordering UI tests

---

## 6. M8: Beyond Novels (Exploratory)

### 6.1 Core Logic (M8-Core)

**Extensions to `src/lorewrite/core/entities.py`**:

```python
# Add new entity types:
VALID_TYPES = ("character", "place", "object", "faction", "figure", "table", "equation")

# Add structured data fields for new types:
@dataclass
class StructuredEntity(Entity):
    caption: str = ""
    alt_text: str = ""  # for figures
    data: dict = field(default_factory=dict)  # table/equation data
```

### 6.2 TUI Integration (M8-TUI)

**New file: `src/lorewrite/tui/screenpacemode.py`**

```python
"""Screenplay formatting mode and export."""

class ScreenplayMode:
    """Configurable screenplay formatting rules."""
```

### 6.3 Testing Strategy (M8-Tests)

**New file: `tests/test_structured_entities.py`** - Figure/table/equation entities

---

## 7. Cross-Cutting Integration Details

### 7.1 Project Settings Extensions

**Extend `project.toml` schema**:

```toml
[ai]
fast_model = "google/gemini-2.5-flash"
strong_model = "anthropic/claude-sonnet-4.5"

[continuity]
auto_check_scene = false
auto_check_manuscript = false
waiver_expiration_days = 30

[style]
auto_update = true

[export]
default_template = "book"
default_font_size = "12pt"
default_line_spacing = "single"

[writing]
focus_timer_minutes = 25
show_live_spellcheck = false
track_sessions = true
```

### 7.2 New Commands Palette Entries

**Actions to add to `src/lorewrite/tui/commands.py`**:

```python
# M3 actions:
("Check scene continuity", "check_continuity", "AI: find contradictions in current scene"),
("Check manuscript continuity", "check_manuscript", "AI: check entire story for contradictions"),
("Accumulate entity notes", "accumulate_entity_notes", "AI: update entity notes from scene review"),

# M4 actions:
("Learn author style", "learn_style", "AI: analyze your writing style"),
("Insert AI expansion", prompt_expansion", "AI: generate text at cursor"),
("Review AI text", "review_ai_text", "Review and accept/reject AI-generated text"),

# M6 actions:
("Start focus sprint", "start_sprint", "Begin timed writing sprint"),
("Session statistics", "session_stats", "Show writing metrics and streaks"),
("Toggle spellcheck", "toggle_spellcheck", "Enable/disable live spell checking"),

# M7 actions:
("Export manuscript", "export_manuscript", "Export to PDF via LaTeX"),
("Scene drag reorder", "enable_drag_reorder", "Allow drag-and-drop scene reordering"),
```

### 7.3 Status Bar Extensions

**Add to status bar info**:
- Current AI model in use
- Continuity check status for current scene (✓/⚠️/—)
- Active focus timer (if running)
- Session words today

---

## 8. Integration Dependencies

### 8.1 Critical Path Dependencies

```
M3 success depends on:
✓ Jev integration (external dependency)
✓ Strong model access (OpenRouter)
✓ Entity note accumulation workflow

M4 success depends on:
✓ M3: Entity notes structure established
✓ Text marking system in editor
✓ Style guide persistence

M6 success depends on:
✓ Session tracking in core
✓ Timer widget system

M7 success depends on:
✓ LaTeX toolchain (external)
✓ Template Jinja2 system

M8 success depends on:
✓ M3+M4: Core AI interaction patterns
✓ Entity system extensions
```

### 8.2 Parallel Safe vs Serial Requirements

**Safe to parallelize**:
- Core logic modules (continuity, style, session, export)
- TUI modal screens (each independent)
- Test suites for each module

**Must be serial**:
- Final `app.py` integration points (one at a time)
- Project setting schema changes (coordinate)
- Database schema migrations (Index class)

---

## 9. Risk Mitigation & Open Questions

### 9.1 Known Technical Risks

1. **Private TextArea API drift** (from AGENTS.md): The link-highlighting uses Textual internals
   - Mitigation: Tests lock current behavior; graceful fallback
   
2. **AI costs**: Strong model usage for continuity checking can be expensive
   - Mitigation: Jev pre-screening; explicit warnings in UI
   
3. **LaTeX compilation**: External toolchain dependency
   - Mitigation: Graceful fallback to Markdown if unavailable
   
4. **Large manuscript performance**: AI context limits
   - Mitigation: Retrieval layer (deferred to post-M4)

### 9.2 Open Questions for Team

1. **Jev threshold tuning**: What contradiction confidence scores should trigger strong model checks?
2. **Style guide granularity**: How detailed should the learned style guide be?
3. **Session privacy**: Should session stats be per-project or global?
4. **Export customization**: How configurable should LaTeX templates be?

---

## 10. Review Gates Before Reporting Done

For each milestone, before reporting complete:

1. **Unit tests pass**: `pytest tests/test_milestone.py`
2. **Integration tests pass**: Full UI flow tests using Pilot
3. **Jev review**: `git diff --changed-files | ~/.config/jev/jev.py review --task "Milestone X" --files ...`
4. **Performance check**: No regressions in file load/save times
5. **API compatibility**: Existing core APIs unchanged
6. **Error handling**: Network failures, missing files handled gracefully
7. **Documentation**: SPEC.md updated for any design changes

---

## 11. File Ownership Summary

```
M3 (Lore):
- Core: continuity.py, jev_interface.py
- AI: continuity.py (ai/)
- TUI: continuityscreen.py, notesaccumulator.py
- Tests: test_continuity.py, test_ai_continuity.py

M4 (Style):
- Core: style.py
- AI: style.py (ai/)
- TUI: expansionprompt.py, aitextreview.py, editor.py changes
- Tests: test_style.py, test_ai_style.py, test_expansion_ui.py

M6 (Aids):
- Core: session.py, spellcheck.py
- TUI: focustimer.py, sessionstats.py, app.py changes
- Tests: test_session.py, test_spellcheck.py, test_focus_timer.py

M7 (Export):
- Core: export.py, templates/
- TUI: exportmodal.py, sidebar.py drag support
- Tests: test_export.py, test_drag_reorder.py

M8 (Beyond):
- Core: entities.py extensions
- TUI: screenplay.py
- Tests: test_structured_entities.py

Integration:
- TUI: app.py (milestone-specific sections only)
- Core: project.py (settings extensions)
- Tests: conftest.py (new fixtures only)
```