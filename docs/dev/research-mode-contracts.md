# Research mode: interface contracts (P0)

The shared types and function signatures that let the work packages in
[plan-research-mode-work-packages.md](plan-research-mode-work-packages.md) proceed in parallel. They are the
output of package P0 and are **frozen once Wave 1 starts**: a package that needs a change stops and reports
(see its stop conditions) instead of editing a contract. Design reasoning is in
[plan-research-mode.md](plan-research-mode.md); section numbers below refer to it.

All dataclasses are frozen unless noted. Offsets are code points; UTF-16 conversion happens only at the GUI
bridge (`core/spans.py`). Module paths are the intended homes. Research code lives in `core/paper/` (not `core/research/`: that name
collides with the existing `core/research.py`, the Notebook notes). The project mode is `story` or `research`
(`core/project.py` `MODES`); the plan's older word "fiction" means story.

## Types (`core/paper/types.py`)

```python
@dataclass(frozen=True)
class CiteRef:
    key: str                  # case-sensitive, exactly as written after @
    prefix: str = ""          # text before the key inside the citation ("see")
    locator: str = ""         # "p. 12"
    suffix: str = ""
    suppress_author: bool = False   # -@key

@dataclass(frozen=True)
class Citation:
    refs: list[CiteRef]
    start: int                # code point offsets of the whole [[...]] or [@...]
    end: int
    raw: str
    kind: Literal["bracketed", "narrative", "pandoc"]   # [[@k]] / [[+@k]] / [@k]

@dataclass(frozen=True)
class Placement:              # ![[fig:x]] alone on a line
    kind: Literal["fig", "tbl", "eq"]
    label: str                # the file-name stem without the kind prefix ("flow-model")
    start: int
    end: int

@dataclass(frozen=True)
class ObjectRef:              # [[fig:x]] in prose
    kind: Literal["fig", "tbl", "eq"]
    label: str
    start: int
    end: int

@dataclass(frozen=True)
class Num:
    seq: int                  # order of appearance within its kind, 1-based
    display: str              # "2", "2.1", "S1"

Numbering = dict[str, Num]    # key "fig:flow-model" -> Num

@dataclass(frozen=True)
class RefObject:
    kind: Literal["fig", "tbl", "eq"]
    label: str
    path: str                 # project-relative path of the .md
    caption: str
    source: Literal["static", "script", "data"]
    file: str | None          # figure image path, table csv path, None for equations
    width: float | None       # inches
    alt: str
    status: Literal["current", "stale", "failed", "missing"]

@dataclass(frozen=True)
class Annotation:
    id: str                   # Zotero annotation key, stable across syncs
    text: str
    comment: str
    page: str

@dataclass(frozen=True)
class ZItem:
    key: str                  # Zotero item key (not the citation key)
    version: int | None       # meaningful only for the backend that produced it
    csl: dict                 # the item's full CSL JSON, verbatim
    citation_key: str | None  # data.citationKey, or from Extra on older libraries
    notes: list[str]          # note HTML, unsanitised (the sanitiser is P2)
    annotations: list[Annotation]
    deleted: bool = False

@dataclass(frozen=True)
class Flag:                   # a research-check finding
    kind: str                 # "citation-unresolved", "source-uncited", "ref-missing", ...
    path: str
    row: int | None
    message: str
    blocking: bool
```

## Parsing (`core/links.py`, owner P1)

```python
def find_citations(text: str) -> list[Citation]: ...
def find_placements(text: str) -> list[Placement]: ...      # owner P4 (core/objects.py)
def find_refs(text: str) -> list[ObjectRef]: ...            # owner P4
def strip_math(text: str, *, keep_length: bool = True) -> str: ...   # owner P4; research mode only
```

Rules (6.1): `find_links` and `find_all_links` ignore any target that starts with `@`, `-@` or `+@`, contains
` @`, or starts with `fig:`, `tbl:`, `eq:`. `find_citations` is the only citation parser. `strip_math` uses
pandoc's `tex_math_dollars` rule and is a no-op outside research mode.

## Entities and sources (`core/entities.py`, `core/project.py`; owner P1)

```python
VALID_TYPES = ("character", "place", "object", "faction",
               "source", "concept", "method", "dataset")
TYPE_SUBDIRS["source"] = "sources"      # entities/sources/ (also entities/concepts/, methods/, datasets/)

Entity.is_source: bool                  # type == "source"
def resolve_key(key: str, entities: Iterable[Entity]) -> Entity | None: ...   # case-sensitive, source keys only
Index.citers(key: str) -> list[Backlink]          # from the case-sensitive citations(source, key) table
```

`Project.entity_path` and `create_entity` use `slugify(key)` plus a collision suffix for sources. "Rename
everywhere" is disabled for sources. **AI exclusion:** `continuity.canon_map`, `ai/relevance.rank` and the
alias finder skip source-kind entities unless attached or the open "About:" subject. A test asserts no
source text appears in any `build_context_sections` output.

## Zotero client (`core/zotero/`, owner P2)

```python
class ZoteroSource(Protocol):
    name: Literal["web", "local", "file", "cache"]
    def probe(self) -> Status: ...                       # reachable? version? server id?
    def fetch(self, scope: Scope, since: int | None) -> FetchResult: ...

@dataclass(frozen=True)
class FetchResult:
    backend: str
    items: list[ZItem]
    deleted_keys: list[str]
    library_version: int | None
    server_id: str | None            # local API Zotero-Server-ID

def open_sources(settings) -> list[ZoteroSource]: ...
def chain_fetch(sources, scope, state) -> tuple[FetchResult, list[str]]: ...   # report in plain words
```

Order is web, local, file, cache. Fall-through never mixes version state across backends (4.1, 4.3).

## Source notes and sync (`core/sources.py`, owner P3)

```python
def item_to_note(item: ZItem, existing: Entity | None) -> Entity: ...
def replace_block(body: str, md: str) -> str: ...        # only between the zotero markers
def plan_sync(project, result: FetchResult) -> SyncPlan: ...   # rows: id, key, action (new|changed|missing|key-mismatch), summary
def apply_sync(project, plan: SyncPlan, ticked_ids: list[str]) -> dict: ...    # {"changed": [ids]}; refuses files changed since the plan
```

## Objects (`core/objects.py`, `core/tables.py`, `core/figscripts.py`, `core/tablefmt.py`; owners P4, P4b)

```python
def list_objects(project) -> list[RefObject]: ...
def create_figure(project, src_bytes: bytes, label: str, caption: str) -> RefObject: ...   # PNG/JPG by bytes, 10 MB cap
def numbering(project) -> Numbering: ...                 # reading order via list_scenes; schemes: plain|per-section|supplementary

def parse_pipe(text: str) -> Table: ...                  # Table(cells: list[list[str]], align: list[str])
def to_pipe(table: Table) -> str: ...                    # canonical form, deterministic dash counts

# P4b
def trust_state(project, id: str) -> Literal["trusted", "untrusted", "changed"]: ...   # reads the per-user state folder only
def trust_figure(project, id: str, sha: str) -> None: ...      # the only writer of the trust record
def run_figure(project, id: str) -> RunResult: ...             # refuses unless trust_state == "trusted"; status, error text
def figure_status(project, id: str) -> Literal["current", "stale", "failed", "missing"]: ...
def build_table(project, id: str) -> BuiltTable: ...           # markdown + export form + warnings
```

Trust is stored in the per-user state folder keyed by project id, figure path and SHA-256. Nothing in the
project can mark a script trusted.

## Export (`core/export/research.py`, `csljson.py`, `pandoc.py`, `manuscript.py`; owner P5)

```python
def assemble_research(project, opts) -> Book: ...        # Book gains Heading, Math, Citation, Figure, Table, Equation, Footnote
def convert_research(book, fmt: Literal["docx", "tex", "pdf"], out: Path, *,
                     csl: Path, reference_doc: Path | None, resource_path: Path) -> ExportResult: ...
```

Generated constructs bypass escaping; author text keeps strict escaping. Fiction exports must stay
byte-identical (a test).

## Checks (`core/researchchecks.py`, owner P6)

```python
def run_checks(project) -> list[Flag]: ...
def blocking(flags: list[Flag]) -> bool: ...             # export gate; called by P7's export_research_start
```

## AI functions (`ai/`, owner P4c)

```python
def suggest_latex(description: str, *, model, cancel) -> str: ...          # pending proposal only
def suggest_plot_code(description: str, columns: list[str] | None, *, model, cancel) -> str: ...
```

Both follow the existing AI-call pattern (`call_ai` filters, `mockai.py` mock, entries in the mocked-name
tuples and the signature test, a budget `Section` and a `SentReport`). `columns` is sent only if the author
ticked it. Neither runs anything.

## GUI bridge (`gui/research_api.py`, owner P7; every method `@bridge`, returns `{ok, ...}`, network outside `self._lock`)

| Method | Purpose |
|---|---|
| `zotero_status()` | which backends answer |
| `zotero_sync_plan(scope)` / `zotero_sync_apply(ticked)` | review-then-apply sync |
| `list_sources()` | binder rows |
| `list_objects()` | binder rows for figures, tables, equations |
| `object_numbers()` | the `Numbering` |
| `object_render(ids)` | batch for the editor widgets: kind, number, caption, image data, table cells, LaTeX, status |
| `object_image(label)` | figure bytes via one `_figure_file` door, cached by mtime |
| `read_table(id)` / `save_table(id, cells, align, base_mtime)` | table panel (Python parses and serialises) |
| `insert_figure(data_url, label, caption)` | add a figure |
| `trust_figure(id, sha)` / `figure_run_start(id)` / `figure_run_status(job)` / `figure_run_cancel(job)` | script flow, as a job |
| `build_table(id)` | generated tables |
| `suggest_latex(...)` / `suggest_plot_code(...)` | AI proposals (mock names listed in the signature test) |
| `research_checks()` | flags |
| `export_research_start(opts)` | refuses while `blocking(run_checks(...))` unless overridden |

## Spans (`core/spans.py`, `gui/api.py`, owner P1 for the parsers, P7 for the bridge)

`compute_spans` / `link_spans` additionally emit citation, object-reference, placement and inline-math spans
(research mode only). Fiction span output must be byte-identical (a test).

## Registrations done in P0 (so later packages touch only their own modules)

As built: `core/paper/types.py`, the empty `ResearchMixin` (`gui/research_api.py`, in the `Api` bases),
`gui/src/data/research.ts`, and the project `mode` (`core/project.py` `MODES`, `Project.mode`, workspace
`project.mode` and `labels`, `set_mode`). **Deliberately left to their owners** because a registration without
its behaviour would change fiction projects or break tests: `TYPE_SUBDIRS` / `VALID_TYPES` (P1, gated by mode so
a story project gains no folders), the Trash kind `object` and the `code` document kind (P4, with their
branches and tests), and the mocked-name tuple entries (P4c, when the functions exist).

Original list:

`ResearchMixin` stub in the `Api` mixin list and facade; `TYPE_SUBDIRS` and `VALID_TYPES` entries; the Trash
kind `object` constant and its branches; `_doc_kind` branches including the new `code` kind; `gui/src/data/types.ts`
placeholders; `project.toml` `mode` accessor; mocked-name tuple placeholders.
