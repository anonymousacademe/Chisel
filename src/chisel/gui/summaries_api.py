"""Summaries (core/summaries.py, ai/summaries.py, core/scale.py): status, propose / save / lock / delete, the cost
estimate and the "long project" hint. Nothing here saves a generated summary: ``summarize_propose`` and
``part_summarize_propose`` return a PROPOSAL, and only ``summary_save`` / ``part_summary_save`` (the author accepting,
possibly after editing) write a file."""

from __future__ import annotations

from dataclasses import replace

from ..ai import client as ai_client
from ..ai.budget import Budget, estimate_tokens
from ..ai.summaries import SYSTEM_PROMPT, plan_summarize, plan_summarize_part
from ..core import drafts, scale
from ..core import summaries as store
from . import workspace as ws
from ._bridge import bridge

# What one scene summary writes, in output tokens: a plain model needs about 300 to 1000; a model that thinks
# first wrote 3,000 to 20,000 in the measurements (docs: DIAGNOSIS section 5). Estimates, never promises.
OUTPUT_TOKENS = (300, 1000)
OUTPUT_TOKENS_THINKING = (3000, 20000)
PART_ID_PREFIX = "part:"
SHOWN_REFUSALS = 3          # facts named in a refusal message; the rest are counted


def _summary_payload(s: store.Summary) -> dict:
    return {"summary": s.summary, "characters": [{"name": c.name, "state": c.state} for c in s.characters],
            "facts": [{"text": f.text, "quote": f.quote} for f in s.facts], "threads": list(s.threads)}


def _part_payload(p: store.PartSummary) -> dict:
    return {"summary": p.summary, "characters": [{"name": c.name, "state": c.state} for c in p.characters],
            "threads": list(p.threads)}


def _words(text: str) -> int:
    return len(text.split())


def _check_words(text: str, cap: int, what: str) -> None:
    if not text.strip():
        raise ValueError(f"A {what} needs some text.")
    if _words(text) > cap:
        raise ValueError(f"A {what} is at most {cap} words; this one has {_words(text)}.")


def _sentence_list(items: list[str]) -> str:
    shown = ", ".join(f"“{i}”" for i in items[:SHOWN_REFUSALS])
    return shown + (f" and {len(items) - SHOWN_REFUSALS} more" if len(items) > SHOWN_REFUSALS else "")


def _added_by_author(candidate: dict, proposed: dict | None) -> bool:
    """The author's words are in *candidate* that the proposal did not have: a changed summary text, or a character
    state, fact or thread that is new or reworded (pure removals are not editing)."""
    if proposed is None:
        return True
    if " ".join(str(candidate.get("summary", "")).split()) != " ".join(str(proposed.get("summary", "")).split()):
        return True

    def rows(d: dict) -> set:
        return ({("c", str(c.get("name")), str(c.get("state"))) for c in d.get("characters") or [] if isinstance(c, dict)}
                | {("f", str(f.get("text")), str(f.get("quote"))) for f in d.get("facts") or [] if isinstance(f, dict)}
                | {("t", str(t)) for t in d.get("threads") or []})
    return bool(rows(candidate) - rows(proposed))


class SummariesMixin:
    # Mixin of Api (api.py): every public method is a bridge method; shared state is on Api. The AI functions
    # (summarize_scene, summarize_part) are looked up on the api module at call time so tests and gui/mockai can
    # replace them like every other AI call.

    def _summary_target(self, ident: str):
        """(project, path, is_part) for a scene id or a "part:..." id (call with the lock held)."""
        project = self._require()
        if str(ident).startswith(PART_ID_PREFIX):
            part = ws.part_for_id(project, ident)
            if part is None:
                raise ValueError("no such part")
            return project, part, True
        path, kind = self.resolve_document(ident)
        if kind != "scene":
            raise ValueError("a summary belongs to a scene")
        return project, path, False

    # -- status -----------------------------------------------------------------------------

    @bridge
    def summaries_status(self) -> dict:
        """Every counted scene in reading order with its summary status (missing | fresh | stale | locked) and the
        words of its summary, every part with the status of its part summary, and the totals. No AI and no
        network; it reads each scene once to compare it with the summary it was made from, so it is not part of
        ``get_workspace`` and the project lock is not held while it reads."""
        with self._lock:
            project = self._require()
            scenes = project.counted_scenes()
            parts = [p for p in project.list_parts() if not project.part_is_front_matter(p)]
        rows, counts = [], {s: 0 for s in store.STATUSES}
        for path in scenes:
            status = store.status(project, path)
            stored = store.load(project.root, path)
            counts[status] += 1
            part = project.part_of(path)
            rows.append({"id": ws.rel_id(project, path), "title": project.scene_title(path), "status": status,
                         "words": _words(stored.summary) if stored else 0,
                         "part": ws.part_id(project, part) if part else None,
                         "changedSince": bool(stored and stored.protected and store.changed_since(project, path)),
                         "facts": len(stored.facts) if stored else 0})
        part_rows = []
        for part in parts:
            stored = store.load_part(project.root, part)
            members = [r for r in rows if r["part"] == ws.part_id(project, part)]
            part_rows.append({"id": ws.part_id(project, part), "title": project.part_title(part),
                              "status": store.part_status(project, part), "scenes": len(members),
                              "summarised": sum(r["status"] != store.MISSING for r in members),
                              "words": _words(stored.summary) if stored else 0})
        total = len(rows)
        percent = round(100 * (total - counts[store.MISSING]) / total) if total else 100
        return {"scenes": rows, "parts": part_rows,
                "totals": {"scenes": total, "counts": counts, "percent": percent}}

    @bridge
    def summary_get(self, scene_id: str) -> dict:
        """The stored summary of a scene or a "part:..." id, for its card: `status` (missing | fresh | stale | locked),
        `summary` (summary, characters, facts, threads; None when there is none), `locked`, `authorEdited`, `model`,
        `created`, `cost` and `changedSince` (a locked or edited summary whose scene changed afterwards). Reads one
        scene, no AI."""
        with self._lock:
            project, path, is_part = self._summary_target(scene_id)
            stored = store.load_part(project.root, path) if is_part else store.load(project.root, path)
            if stored is None:
                return {"id": scene_id, "status": store.MISSING, "summary": None, "locked": False,
                        "authorEdited": False, "changedSince": False}
            return {"id": scene_id, "summary": (_part_payload if is_part else _summary_payload)(stored),
                    "status": store.part_status(project, path) if is_part else store.status(project, path),
                    "locked": stored.locked, "authorEdited": stored.author_edited, "model": stored.model,
                    "created": stored.created, "cost": stored.cost,
                    "changedSince": bool(not is_part and stored.protected and store.changed_since(project, path))}

    # -- propose (AI jobs: ai_start kinds "summarize" and "part_summarize") -------------------

    @bridge
    def summarize_propose(self, scene_id: str) -> dict:
        """An AI job (kind ``summarize``): propose a summary of one scene. Returns the PROPOSAL (summary, characters,
        facts, threads), what verification dropped (`dropped`: kind, text, reason), how many facts needed the looser
        quote rule (`tolerant`), whether the text had to be cut at the word cap (`trimmed`), the cost, the model and the `sent` report. NOTHING is saved. A locked or
        author-edited summary is never regenerated (an error says so). The project lock is released before the
        network call."""
        from . import api as api_module

        with self._lock:
            project, path, is_part = self._summary_target(scene_id)
            if is_part:
                raise ValueError("a scene summary belongs to a scene (use part_summarize_propose for a part)")
            existing = store.load(project.root, path)
            if existing is not None and existing.protected:
                raise ValueError("This summary is locked or edited by you, so it is never replaced. "
                                 "Unlock it or delete it first.")
            text, originals = ws.read_text(project, path)
            if not ws.split_title(store.prose_of(text, originals))[1].strip():
                raise ValueError("This scene has no text to summarise yet.")
            scene_text = drafts.strip_pending(text, originals)
            model = ai_client.resolve_model("summary", project.meta)
            entities = list(self.entities)
        kept, sent = plan_summarize(scene_text, entities, Budget.for_model(model))   # before any network call
        calls = api_module.LEDGER.count()
        proposal = self._stream(api_module.summarize_scene, text, kept, model, originals=originals)
        s = proposal.summary
        return {"id": scene_id, "model": model, "replacing": existing is not None,
                "proposal": _summary_payload(s),
                "dropped": [{"kind": d.kind, "text": d.text, "reason": d.reason} for d in proposal.dropped],
                "tolerant": proposal.tolerant, "trimmed": proposal.trimmed, "sourceHash": s.source_hash,
                "cost": s.cost or self._spent(calls), "sent": sent.to_dict()}

    @bridge
    def part_summarize_propose(self, part_id: str) -> dict:
        """An AI job (kind ``part_summarize``): propose a summary of a part from its scenes' stored summaries
        (the scenes without one are named in `missing`). Nothing is saved."""
        from . import api as api_module

        with self._lock:
            project, part, is_part = self._summary_target(part_id)
            if not is_part:
                raise ValueError("pick a part")
            existing = store.load_part(project.root, part)
            if existing is not None and existing.protected:
                raise ValueError("This part summary is locked or edited by you, so it is never replaced. "
                                 "Unlock it or delete it first.")
            scenes, missing = [], []
            for path in project.part_scenes(part):
                stored = store.load(project.root, path)
                if stored is None:
                    missing.append(project.scene_title(path))
                else:
                    scenes.append((project.scene_title(path), stored))
            if not scenes:
                raise ValueError("Summarise the scenes of this part first: a part summary is made from them.")
            inputs = store.part_inputs(project, part)
            title = project.part_title(part)
            model = ai_client.resolve_model("summary", project.meta)
        names, sent = plan_summarize_part(title, scenes, Budget.for_model(model))
        use = [(n, s) for n, s in scenes if n in names]
        calls = api_module.LEDGER.count()
        result = self._stream(api_module.summarize_part, title, use, model, inputs=inputs)
        return {"id": part_id, "model": model, "replacing": existing is not None,
                "proposal": _part_payload(result), "missing": missing, "trimmed": result.trimmed,
                "cost": result.cost or self._spent(calls), "sent": sent.to_dict()}

    # -- save / lock / delete ---------------------------------------------------------------

    @bridge
    def summary_save(self, scene_id: str, summary_payload: dict) -> dict:
        """The author accepted a summary, possibly after editing it. *summary_payload* is `summary`, `characters`,
        `facts`, `threads`, plus what the proposal returned: `proposed` (the proposal's own summary / characters /
        facts / threads, so an edit can be told from an acceptance), `sourceHash`, `model`, `cost`. Refused with a
        message when: the text is empty or over 90 words; any fact's quote no longer matches the scene, or a
        character's name is not in it (the facts are named); the summary is locked; the scene changed since the
        proposal. `author_edited` is set when the author's own words are in it (a changed summary text, or a new or
        reworded fact / character / thread; with no `proposed` the whole text is the author's). Atomic write.
        Returns the new status."""
        if not isinstance(summary_payload, dict):
            raise ValueError("nothing to save")
        with self._lock:
            project, path, is_part = self._summary_target(scene_id)
            if is_part:
                raise ValueError("use part_summary_save for a part")
            candidate = store.summary_from_dict(summary_payload)
            if candidate is None:
                raise ValueError("A summary needs some text.")
            _check_words(candidate.summary, store.SUMMARY_WORDS, "summary")
            existing = store.load(project.root, path)
            if existing is not None and existing.locked:
                raise ValueError("This summary is locked. Unlock it to change it.")
            text, originals = ws.read_text(project, path)
            now_hash = store.hash_of(text, originals)
            proposed = summary_payload.get("proposed")
            proposed = proposed if isinstance(proposed, dict) else None
            sent_hash = str(summary_payload.get("sourceHash") or "")
            if proposed is not None and sent_hash and sent_hash != now_hash:
                raise ValueError("The scene changed since this summary was written. Propose it again.")
            clean, dropped, _ = store.verify_counted(candidate, text, originals)
            bad_facts = [d.text for d in dropped if d.kind == "fact"]
            bad_names = [d.text for d in dropped if d.kind == "character"]
            if bad_facts:
                reasons = sorted({d.reason for d in dropped if d.kind == "fact"})
                raise ValueError(f"These facts cannot be kept: {_sentence_list(bad_facts)} ({'; '.join(reasons)}). "
                                 "Fix the quote or remove the fact.")
            if bad_names:
                raise ValueError(f"These characters are not named in the scene: {_sentence_list(bad_names)}.")
            edited = _added_by_author(summary_payload, proposed)
            model = str(summary_payload.get("model") or (existing.model if existing else "") or "")
            cost = summary_payload.get("cost")
            saved = replace(clean, source_hash=now_hash, model=model if proposed is not None else "author",
                            created=store.now(), author_edited=edited, locked=False,
                            cost=float(cost) if isinstance(cost, (int, float)) and proposed is not None else 0.0)
            store.save(project.root, path, saved)
            return {"id": scene_id, "status": store.status(project, path), "authorEdited": edited,
                    "summary": _summary_payload(saved)}

    @bridge
    def part_summary_save(self, part_id: str, summary_payload: dict) -> dict:
        """Accept a part summary (same payload as ``summary_save`` without facts; at most 150 words; `proposed` tells
        an edit from an acceptance). It records the scene summaries it now stands on, so it goes stale when one
        changes. Refused when it is locked."""
        if not isinstance(summary_payload, dict):
            raise ValueError("nothing to save")
        with self._lock:
            project, part, is_part = self._summary_target(part_id)
            if not is_part:
                raise ValueError("use summary_save for a scene")
            candidate = store.part_from_dict(summary_payload)
            if candidate is None:
                raise ValueError("A part summary needs some text.")
            _check_words(candidate.summary, store.PART_SUMMARY_WORDS, "part summary")
            existing = store.load_part(project.root, part)
            if existing is not None and existing.locked:
                raise ValueError("This part summary is locked. Unlock it to change it.")
            proposed = summary_payload.get("proposed")
            proposed = proposed if isinstance(proposed, dict) else None
            edited = _added_by_author(summary_payload, proposed)
            cost = summary_payload.get("cost")
            saved = replace(candidate, inputs=store.part_inputs(project, part), created=store.now(),
                            model=str(summary_payload.get("model") or "") if proposed is not None else "author",
                            cost=float(cost) if isinstance(cost, (int, float)) and proposed is not None else 0.0,
                            author_edited=edited, locked=False)
            store.save_part(project.root, part, saved)
            return {"id": part_id, "status": store.part_status(project, part), "authorEdited": edited,
                    "summary": _part_payload(saved)}

    @bridge
    def summary_lock(self, scene_id: str, locked: bool) -> dict:
        """Lock (or unlock) the stored summary of a scene or a "part:..." id: a locked summary is never offered for
        regeneration and never overwritten. An error when there is no summary."""
        with self._lock:
            project, path, is_part = self._summary_target(scene_id)
            stored = store.load_part(project.root, path) if is_part else store.load(project.root, path)
            if stored is None:
                raise ValueError("There is no summary to lock.")
            changed = replace(stored, locked=bool(locked))
            (store.save_part if is_part else store.save)(project.root, path, changed)
            return {"id": scene_id, "locked": bool(locked),
                    "status": store.part_status(project, path) if is_part else store.status(project, path)}

    @bridge
    def summary_delete(self, scene_id: str) -> dict:
        """Delete the stored summary of a scene or a "part:..." id. Plain deletion, not the Trash: a summary can be
        written again (it costs a call), so there is nothing to restore; the UI confirms first, and says so when the
        summary was locked or edited by the author."""
        with self._lock:
            project, path, is_part = self._summary_target(scene_id)
            stored = store.load_part(project.root, path) if is_part else store.load(project.root, path)
            if stored is not None:
                (store.delete_part if is_part else store.delete)(project.root, path)
            return {"id": scene_id, "deleted": stored is not None, "wasProtected": bool(stored and stored.protected)}

    # -- estimate and hint (no AI) -----------------------------------------------------------

    @bridge
    def summaries_estimate(self, scene_ids: list | None = None) -> dict:
        """What summarising would cost, BEFORE anything is sent and with no network: the number of calls, the input
        tokens (characters / 4: the scene and the instructions), and a cost range from the model's price in the
        catalogue Chisel already fetched. The price is `None` and the cost "unknown" when the catalogue has none (never
        a made-up number); a local model costs nothing. `scene_ids` None = every scene that has no summary or a stale
        one; a locked or edited summary is never counted (`skipped`). `reasoningModel` says whether the catalogue lists
        the model as one that thinks first (None = unknown) and `reasoning` is the current setting; thinking multiplies
        the output tokens by about ten, which the range shows."""
        with self._lock:
            project = self._require()
            model = ai_client.resolve_model("summary", project.meta)
            setting = ai_client.resolve_reasoning(project.meta)
            if scene_ids is None:
                candidates = project.counted_scenes()
                wanted = None
            else:
                candidates = [self.resolve_document(str(i))[0] for i in scene_ids]
                wanted = True
        paths, skipped, tokens = [], [], 0
        for path in candidates:
            stored = store.load(project.root, path)
            if stored is not None and stored.protected:
                skipped.append(ws.rel_id(project, path))
                continue
            if wanted is None and store.status(project, path) not in (store.MISSING, store.STALE):
                continue
            text, originals = ws.read_text(project, path)
            tokens += estimate_tokens(store.prose_of(text, originals)) + estimate_tokens(SYSTEM_PROMPT)
            paths.append(path)
        calls = len(paths)
        thinking = ai_client.cached_is_reasoning(model)
        out_low, out_high = OUTPUT_TOKENS_THINKING if thinking and setting != "off" else OUTPUT_TOKENS
        price = ai_client.cached_pricing(model)
        cost = None
        if price is not None:
            prompt_per_m, completion_per_m = price
            cost = {"low": round((tokens * prompt_per_m + calls * out_low * completion_per_m) / 1e6, 4),
                    "high": round((tokens * prompt_per_m + calls * out_high * completion_per_m) / 1e6, 4)}
        notes = []
        if price is None:
            notes.append("The price of this model is unknown: open the model picker once so Chisel can read it.")
        if thinking is None and not ai_client.is_local(model):
            notes.append("Chisel does not know whether this model thinks before it answers.")
        if thinking and setting != "off":
            notes.append("This model thinks before it answers, which makes each call slower and several times "
                         "dearer than the summary itself. The setting 'reasoning: off' avoids that, with thinner "
                         "answers.")
        return {"calls": calls, "inputTokens": tokens, "outputTokens": {"low": out_low * calls, "high": out_high * calls},
                "model": model, "local": ai_client.is_local(model), "reasoningModel": thinking, "reasoning": setting,
                "price": ({"promptPerM": price[0], "completionPerM": price[1]} if price else None),
                "cost": cost, "costText": "unknown" if cost is None else
                (f"${cost['low']:.4f} to ${cost['high']:.4f}" if cost["high"] else "free"),
                "skipped": skipped, "notes": notes}

    @bridge
    def scale_hint(self) -> dict:
        """The "this project is getting long" hint (core.scale.scale_hint): `level` none | notice | strong, a
        plain-language `message`, the `numbers` behind it and the level the author last closed (`dismissedLevel`).
        Uses the real window of the summary model. It reads every scene, so it is its own call (never part of
        ``get_workspace``) and the lock is not held while it reads."""
        with self._lock:
            project = self._require()
            model = ai_client.resolve_model("summary", project.meta)
            dismissed = project.scale_hint_dismissed()
        window = Budget.for_model(model).window_tokens
        out = scale.scale_hint(project, window, words=scale.count_words(project),
                               coverage=store.coverage(project), dismissed=dismissed)
        return {**out, "dismissedLevel": dismissed, "model": model}

    @bridge
    def scale_hint_dismiss(self, level: str) -> dict:
        """The author closed the hint of *level* ("notice" or "strong"; "" forgets it): kept in project.toml
        `[ui] scale_hint_dismissed`, written atomically. A hint of that level or a milder one stays hidden; a
        stronger one can still appear."""
        with self._lock:
            self._require().set_scale_hint_dismissed(level)
            return {"dismissedLevel": level}
