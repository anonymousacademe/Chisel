"""Command palette providers (ctrl+p): scenes, entities, links, actions.

Every provider implements discover() so the palette opens as a menu, not a
blank search bar, and search() treats an empty query as match-all (Textual's
fuzzy Matcher raises/scores 0 on empty queries).
"""

from __future__ import annotations

from functools import partial

from textual.command import DiscoveryHit, Hit, Provider


class _Provider(Provider):
    """Base: shared machinery for entry-list providers.

    Errors are isolated per provider: one failing provider must never blank
    the whole command palette.
    """

    def _entries(self):
        """Yield (display, match_text, callback, help). Override."""
        raise NotImplementedError
        yield

    def _safe_entries(self):
        try:
            yield from self._entries()
        except Exception as exc:  # noqa: BLE001 - isolation, not silence
            self.app.log.warning(f"command provider {type(self).__name__}: {exc}")

    async def search(self, query: str):
        matcher = self.matcher(query)
        query = query.strip()
        for display, match_text, callback, help_text in self._safe_entries():
            score = matcher.match(match_text) if query else 1.0
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(display) if query else display,
                    callback,
                    help=help_text,
                )

    async def discover(self):
        for display, _, callback, help_text in self._safe_entries():
            yield DiscoveryHit(display, callback, help=help_text)


class SceneProvider(_Provider):
    """Open a scene by title."""

    def _entries(self):
        app = self.app
        unit = app.project.unit
        for path in app.project.all_scene_files():
            title = app.project.scene_title(path)
            yield (
                f"{unit.capitalize()} · {title}",
                title,
                partial(app.open_file, path),
                f"Open {unit} {path.name}",
            )


class EntityProvider(_Provider):
    """Open an entity note by name or alias."""

    def _entries(self):
        app = self.app
        for entity in app.entities:
            display = f"Entity · {entity.name} ({entity.type})"
            match_text = " ".join(entity.names)
            aliases = ", ".join(entity.aliases)
            help_text = f"Open {entity.type} note" + (
                f" — aliases: {aliases}" if aliases else ""
            )
            yield display, match_text, partial(app.open_file, entity.path), help_text


class InsertLinkProvider(_Provider):
    """Insert an entity's name at the cursor (recognized as a mention)."""

    def _entries(self):
        app = self.app
        for entity in app.entities:
            display = f"Link · {entity.name}"
            yield (
                display,
                display,
                partial(app.insert_link, entity.name),
                f"Insert {entity.name} at cursor",
            )


class ActionProvider(_Provider):
    """App actions: scene organization, new entities, index rebuild."""

    ACTIONS = [
        ("New scene", "create_scene_prompt", "Create a new manuscript scene"),
        ("Next scene", "next_scene", "Open the next scene (alt+right)"),
        ("Previous scene", "previous_scene", "Open the previous scene (alt+left)"),
        ("Rename current scene", "rename_scene_prompt",
         "Rename the scene open in the editor"),
        ("Move current scene up", "move_scene_up",
         "Swap with the scene above in its part (renumbers files)"),
        ("Move current scene down", "move_scene_down",
         "Swap with the scene below in its part (renumbers files)"),
        ("Edit details", "edit_details",
         "POV, place, purpose, status and word target (stored in the scene's frontmatter)"),
        ("Collections", "open_collections",
         "Tick the open scene's collections; add, rename, recolour or delete them (sidebar filter: #name)"),
        ("Snapshots", "open_snapshots",
         "List, compare, restore or delete snapshots of the open scene"),
        ("Snapshot scene", "snapshot_scene_prompt",
         "Keep a verbatim copy of the open scene you can compare and restore"),
        ("Snapshot all scenes", "snapshot_all_prompt",
         "One snapshot of every scene in the project, with one label"),
        ("Commit changes", "sync_commit_prompt",
         "git: commit this project folder (message pre-filled; nothing is pushed)"),
        ("Push", "sync_push_confirm",
         "git: push the current branch to its remote, after a confirmation (never forced)"),
        ("Initialize git for this project", "sync_init_confirm",
         "Make the project folder a git repository (.gitignore hides .lorewrite/)"),
        ("Start new draft", "start_new_draft",
         "Snapshot every scene as the end of this draft, then count up to the next draft"),
        ("New part", "new_part_prompt", "Add a part (a folder under manuscript/)"),
        ("Rename part", "rename_part_prompt", "Retitle the open scene's part"),
        ("Move part up", "move_part_up", "Swap the part with the one before it"),
        ("Move part down", "move_part_down", "Swap the part with the one after it"),
        ("Delete empty part", "delete_part_confirm",
         "Remove a part that has no scenes"),
        ("Move scene to part", "move_scene_to_part_prompt",
         "Send the open scene to the end of another part"),
        ("Move scene to Unplaced", "unplace_scene_action",
         "Take the open scene out of the book (kept, not counted)"),
        ("Place scene in the book", "place_scene_action",
         "Bring an unplaced scene back into a part"),
        ("Delete current scene", "delete_scene_confirm",
         "Move the scene open in the editor to the Trash"),
        ("Open Trash", "open_trash",
         "Restore deleted scenes, delete them forever, or empty the Trash"),
        ("Toggle scene/chapter labels", "toggle_unit",
         "Call the manuscript's units scenes or chapters (labels only)"),
        ("Writer mode", "writer_mode", "Hide everything but the editor (f11)"),
        ("New character", "create_entity_prompt_character", "Create a character note"),
        ("New place", "create_entity_prompt_place", "Create a place note"),
        ("Find aliases in this scene", "find_aliases",
         "AI: find other ways the prose refers to your entities (ctrl+l)"),
        ("Check scene for continuity issues", "check_continuity",
         "AI: flag contradictions with the story bible"),
        ("Restore waived continuity issues (this scene)", "restore_waived",
         "Un-waive this scene's continuity flags so the next check reports them"),
        ("Update story bible from scene", "update_bible",
         "AI: propose canon updates to entity notes from this scene"),
        ("AI: learn style guide from manuscript", "learn_style_guide",
         "Describe your voice from your own prose; review before saving style.md"),
        ("Open style guide", "open_style_guide",
         "Edit style.md, the style guide the AI writing features follow"),
        ("AI write at cursor / expand / rewrite selection", "generate_text",
         "Draft prose (prompt window), expand a {{expand: …}} marker, or rewrite the selection (ctrl+g)"),
        ("Accept all AI drafts in this scene", "accept_all_drafts",
         "Keep every pending AI draft as normal text (f7 does one)"),
        ("Reject all AI drafts in this scene", "reject_all_drafts",
         "Restore the original text for every pending AI draft (f8 does one)"),
        ("Toggle spell check", "toggle_spellcheck",
         "Underline misspelled words in scenes (f6 fixes the next one)"),
        ("Add selection to dictionary", "add_selection_to_dictionary",
         "Never flag the selected word or phrase in this project"),
        ("Open project dictionary", "open_project_dictionary",
         "Edit dictionary.txt, the words this project never flags"),
        ("Set OpenRouter API key", "set_api_key",
         "Store the key for AI features in the system keyring"),
        ("Settings", "open_settings",
         "API key, models, and editor preferences"),
        ("Return to main menu", "main_menu",
         "Save and go back to the launch screen (switch projects)"),
        ("Rebuild index", "rebuild_index", "Rebuild the link/entity index from disk"),
    ]

    #: actions listed under another category than "Action"
    CATEGORY = {"edit_details": "Scene", "open_snapshots": "Scene", "open_collections": "Scene",
                "snapshot_scene_prompt": "Scene"}

    def _entries(self):
        app = self.app
        chapters = app.project is not None and app.project.unit == "chapter"
        for title, method, help_text in self.ACTIONS:
            visible = getattr(app, "sync_visible", None)
            if visible is not None and method.startswith("sync_") and not visible(method):
                continue
            if chapters:  # the manuscript's unit is a label only
                title = title.replace("scene", "chapter").replace("Scene", "Chapter")
                help_text = help_text.replace("scene", "chapter")
            category = self.CATEGORY.get(method, "Action")
            if chapters and category == "Scene":
                category = "Chapter"
            yield f"{category} · {title}", title, getattr(app, method), help_text
