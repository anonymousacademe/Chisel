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
        for path in app.project.list_scenes():
            title = app.project.scene_title(path)
            yield (
                f"Scene · {title}",
                title,
                partial(app.open_file, path),
                f"Open scene {path.name}",
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
         "Swap with the scene above (renumbers files)"),
        ("Move current scene down", "move_scene_down",
         "Swap with the scene below (renumbers files)"),
        ("Delete current scene", "delete_scene_confirm",
         "Delete the scene open in the editor"),
        ("Writer mode", "writer_mode", "Hide everything but the editor (f11)"),
        ("New character", "create_entity_prompt_character", "Create a character note"),
        ("New place", "create_entity_prompt_place", "Create a place note"),
        ("Find aliases in this scene", "find_aliases",
         "AI: find other ways the prose refers to your entities (ctrl+l)"),
        ("Check scene for continuity issues", "check_continuity",
         "AI: flag contradictions with the story bible"),
        ("Update story bible from scene", "update_bible",
         "AI: propose canon updates to entity notes from this scene"),
        ("Set OpenRouter API key", "set_api_key",
         "Store the key for AI features in the system keyring"),
        ("Settings", "open_settings",
         "API key, models, and editor preferences"),
        ("Return to main menu", "main_menu",
         "Save and go back to the launch screen (switch projects)"),
        ("Rebuild index", "rebuild_index", "Rebuild the link/entity index from disk"),
    ]

    def _entries(self):
        app = self.app
        for title, method, help_text in self.ACTIONS:
            yield f"Action · {title}", title, getattr(app, method), help_text
