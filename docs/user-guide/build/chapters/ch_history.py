"""Chapter 8: History and Versions."""


def build(s, R):
    s.chapter("8", "History and Versions",
              "Snapshots of your scenes, the number of the draft you are "
              "on, and optional git for people who want to keep the "
              "manuscript somewhere else too.")

    s.p("Writing is mostly changing your mind. Lorewrite keeps a quiet "
        "history of each scene so that changing your mind is never a "
        "risk: you can look at an earlier version, see exactly what is "
        "different from now, and put it back. This chapter covers three "
        "separate things that are easy to mix up:", idx=["history", "versions"])
    s.bullets([
        "**Snapshots**: saved copies of a single scene at a moment in "
        "time, taken by you or by Lorewrite.",
        "**The draft number** (//Draft 2//): a counter for the whole "
        "book, which you advance when you finish a pass and begin the "
        "next.",
        "**Git sync**: an optional way to record the whole project in a "
        "git repository and send it to another computer. It is off "
        "unless you use it.",
    ])
    s.attention("The word //draft// has two meanings in Lorewrite. In "
                "this chapter a **draft** is a pass over the whole book "
                "(//Draft 2//). In Chapters 10 and 11 an **AI draft** is a "
                "piece of text the assistant wrote that you have not yet "
                "accepted or rejected. The two are unrelated. Starting a "
                "new draft does not touch AI drafts, and accepting an AI "
                "draft does not change the draft number.")

    # ------------------------------------------------------------------
    s.h2("The Safety-Net Idea", idx=["snapshot|why", "backup|not a backup"])
    s.p("A snapshot is a complete copy of one scene, kept in a folder "
        "beside your manuscript. It is a safety net for //your own "
        "changes//: the rewrite you regret, the paragraph you cut and "
        "want back, the scene you restored by accident. It is not a "
        "backup. Snapshots live inside the project folder, so if the "
        "disk fails or the folder is deleted, they go with everything "
        "else. For protection against that, copy the project folder "
        "somewhere safe or use git sync (below) with a remote that "
        "lives on another machine.")
    s.p("Snapshots are only ever of //scenes// (the files of your "
        "manuscript, including scenes in Unplaced). Notes, research "
        "notes, the style guide and the dictionary files have no "
        "history. If your project counts chapters instead of scenes "
        "(Chapter 13), the desktop application and the palette say "
        "//chapter// where this chapter says //scene//.")

    # ------------------------------------------------------------------
    s.h2("When Snapshots Are Taken", idx=["snapshot|automatic", "snapshot|manual"])
    s.p(f"Some snapshots you ask for; others Lorewrite takes by itself "
        f"at moments when you might want to go back. {R('t_snapwhen')} "
        "lists all of them with the name each is given in the history "
        "list.")
    s.table("t_snapwhen", "Every kind of snapshot",
            ["Name shown", "When it is taken", "Can you switch it off?"], [
        ["Snapshot (or the label you typed)", "You take it: //Snapshot "
         "scene// or //Snapshot all scenes//, with an optional label.",
         "It only happens when you ask."],
        ["Automatic (first edit of the day)", "Just before the first "
         "save that changes a scene on a given day. The copy holds the "
         "scene as it was //before// that day's edits.",
         "Yes: the History setting (below)."],
        ["Before a restore", "Just before a snapshot replaces the scene, "
         "so the restore itself can be undone.", "No."],
        ["Before accepting all AI drafts", "Before //Accept all AI "
         "drafts in this scene// (Chapter 11), if the scene has at "
         "least one pending draft.", "No."],
        ["Before rejecting all AI drafts", "Likewise before //Reject "
         "all AI drafts in this scene//.", "No."],
        ["End of draft //N//", "When you start a new draft: one for "
         "every scene.", "No."],
    ], [0.30, 0.46, 0.24])
    s.p("Accepting or rejecting a //single// AI draft takes no "
        "snapshot. Lorewrite does not announce automatic snapshots; you "
        "see them only when you open the history of a scene.")
    s.p("The daily snapshot is a gentle default. It skips a scene whose "
        "text did not actually change, a scene that already has a "
        "snapshot from today, a scene whose newest snapshot is already "
        "identical to the file, and a scene that has just been created "
        "(there is no earlier state to keep). If taking it fails for "
        "any reason, your save still goes through.")
    s.h3("Turning the Daily Snapshot Off", idx=["snapshot|setting"])
    s.p(f"In Settings, in the section **History**, the checkbox "
        "**Snapshot a scene the first time it is edited each day** is "
        f"on by default ({R('fig_gsetting')}). It is a setting of the "
        "person, not of the project: it applies to every project you "
        "open. In the terminal application, change it and choose "
        "**Save**. The other automatic snapshots (before a restore, "
        "before accept all or reject all, end of draft) always happen.")
    s.gfigure("fig_gsetting", "g_settings_history", "The History section of "
              "the desktop Settings dialog", width=300)

    # ------------------------------------------------------------------
    s.h2("Taking and Using Snapshots", idx=["snapshot|take", "History dialog",
                                           "Snapshots screen"])
    s.table("t_snaptasks", "Snapshot tasks in the two applications",
            ["Task", "Terminal application", "Desktop application"], [
        ["Open the history of the open scene",
         "Palette: //Scene · Snapshots//",
         "The clock button (**History**) in the left rail, the "
         "**Snapshot** item at the left of the status bar, or "
         "**History (snapshots)…** in the binder's options menu"],
        ["Snapshot this scene", "Palette: //Scene · Snapshot scene//, or "
         "`n` in the snapshots list",
         "Type an optional label, then **Snapshot this scene**"],
        ["Snapshot every scene", "Palette: //Action · Snapshot all "
         "scenes//, or `a` in the snapshots list",
         "Type an optional label, then **Snapshot all**"],
        ["Compare with the scene as it is now", "`enter` or `c` on a "
         "row", "**Compare** on the row"],
        ["Put a snapshot back", "`r` on a row (or in the Compare "
         "screen)", "**Restore** on the row (or in the Compare dialog)"],
        ["Delete a snapshot", "`d` on a row", "**Delete** on the row"],
    ], [0.24, 0.34, 0.42])
    s.p("There are no keyboard shortcuts for these, in either "
        "application. In the terminal, the palette is `ctrl+p`.")

    s.h3("In the Terminal Application", idx=["snapshot|terminal"])
    s.p(f"Choose //Scene · Snapshots//. The screen {R('fig_snaps')} "
        "lists the snapshots of the open scene, newest first. Each row "
        "gives the label, the date and time with how long ago it was, "
        "and the number of words in the snapshot, followed by how many "
        "words more or fewer the scene has now (for example //1,240 "
        "words (+85 now)//). The word counts leave out any AI text you "
        "have not accepted. The hint line along the bottom of the "
        "screen lists the keys.")
    s.figure("fig_snaps", "tui_snapshots", "The Snapshots screen of the "
             "terminal application, with one snapshot taken by hand and "
             "two taken automatically")
    s.table("t_snapkeys", "Keys on the Snapshots screen",
            ["Key", "Action"], [
        ["enter, c", "Compare the highlighted snapshot with the scene."],
        ["r", "Restore the highlighted snapshot (after a confirmation)."],
        ["d", "Delete the highlighted snapshot (after a confirmation)."],
        ["n", "Take a new snapshot of this scene. A prompt asks for an "
         "optional label; `enter` takes the snapshot, `esc` cancels."],
        ["a", "Snapshot all scenes, with one label."],
        ["esc", "Close the screen."],
    ], [0.22, 0.78], mono_cols=(0,))
    s.p(f"Compare ({R('fig_compare')}) shows one stream of text from "
        "the snapshot to now. Words that were in the snapshot but are "
        "gone are red and struck through; words you have added since "
        "are green and underlined. Nothing is written into the text "
        "with brackets or markers. A line at the bottom counts them "
        "(//12 words added (green, underlined), 40 removed (red, struck "
        "through) since the snapshot.//). Press `r` to restore this "
        "snapshot, or `esc` to go back to the list.")
    s.figure("fig_compare", "tui_compare", "The Compare screen: removed "
             "words in red and struck through, added words in green and "
             "underlined")
    s.note("The title of the Compare screen shows the snapshot's file "
           "name, such as //20261001-101500--auto//, not its friendly "
           "label. The two are the same snapshot (see “On Disk” below).")
    s.p("When any snapshot exists for the open scene, the status bar "
        "ends with an item such as //Snapshot 12 min ago//. It is "
        "absent if the scene has none.")

    s.h3("In the Desktop Application", idx=["snapshot|desktop"])
    s.p(f"Any of the three entry points opens the History dialog "
        f"({R('fig_ghist')}), headed //History:// and the scene's "
        "title. At the top is a field for an optional label (for "
        "example, //before the rewrite//); press `enter` there or "
        "click **Snapshot this scene** to take one. **Snapshot all** "
        "takes one of every scene, all with that label. Below is the "
        "list of snapshots, newest first. Each row shows the label in "
        "bold, then the date, how long ago, and the word count with "
        "the change since (//1,240 words (+85 now)//), and has the "
        "buttons **Compare**, **Restore** and **Delete**.")
    s.gfigure("fig_ghist", "g_history", "The History dialog: a label field, "
              "the two snapshot buttons, and a row per snapshot with "
              "Compare, Restore and Delete", width=330)
    s.p(f"**Compare** ({R('fig_gcompare')}) opens a dialog with two "
        "columns that scroll together: the snapshot on the left, headed "
        "//Snapshot// and how long ago, and the scene as it is now on "
        "the right, headed //Now//. Removed words are marked in the "
        "left column and added words in the right, and the dialog opens "
        "scrolled to the first change. A line at the top says //12 "
        "words added, 40 removed since// the date, or //The text is "
        "the same as this snapshot.// Its buttons are **Back to the "
        "list**, **Restore this snapshot** and **Close**.")
    s.gfigure("fig_gcompare", "g_compare", "The Compare dialog, snapshot "
              "on the left, the scene now on the right", width=380)
    s.p("Compare always sets one snapshot against the //current// text "
        "(including words you have not yet saved). It does not compare "
        "two snapshots with each other.")

    s.h3("Restoring a Snapshot", idx=["snapshot|restore", "restore"])
    s.p(f"Restoring replaces the whole scene with the text of the "
        f"snapshot. Lorewrite first takes a snapshot of the scene as "
        f"it is, named //Before a restore//, so a restore is never a "
        f"one-way trip: if you change your mind, restore that one. "
        f"The terminal application asks //Replace this scene with the "
        f"snapshot?// with **Restore** and **Cancel**. The desktop "
        f"application shows a dialog ({R('fig_grestore')}) with "
        f"**Cancel** (already selected) and **Restore**.")
    s.gfigure("fig_grestore", "g_restore_confirm", "The confirmation before "
              "a restore", width=300)
    s.p("If the snapshot was taken while the scene held pending AI "
        "drafts, restoring it puts the text those drafts replaced "
        "back too, so the drafts can still be accepted or rejected.")
    s.attention("Restoring changes the scene on disk at once. The "
                "desktop application saves your open text first; if it "
                "cannot, it says //Could not save the current text "
                "first; nothing was restored.// and leaves everything "
                "as it was. Restoring is not counted as writing in the "
                "session statistics (Chapter 12).")

    s.h3("Deleting a Snapshot", idx=["snapshot|delete"])
    s.p("Deleting asks for a confirmation (//Delete the snapshot? This "
        "cannot be undone.//) and then removes the file. Lorewrite "
        "never deletes snapshots by itself: there is no limit to how "
        "many a scene can have, and none are pruned. A scene edited "
        "every day for a year has about three hundred and sixty-five "
        "automatic snapshots. They are small text files, but if you "
        "want to tidy them, delete them here, or remove the files by "
        "hand (below). When you take **Snapshot all scenes**, you "
        "make one file per scene; a hundred scenes means a hundred "
        "files.")

    s.h3("Snapshots Follow the Scene", idx=["snapshot|rename and move"])
    s.p("A scene keeps its history when you rename it, move it to "
        "another part, send it to Unplaced or reorder the manuscript "
        "(Chapter 5). If you delete a scene, its snapshots go to the "
        "Trash with it, and come back when you restore the scene from "
        "the Trash. Emptying the Trash removes them for good.")

    # ------------------------------------------------------------------
    s.h2("Snapshot Status in the Status Bar", idx=["status bar|snapshot"])
    s.p("At the left end of the desktop status bar "
        f"({R('fig_gstatusleft')}) are three small items. The first is "
        "the draft badge (below). Next is the snapshot item, which "
        "reads //Snapshot 3 h ago// or //No snapshot// for the open "
        "scene; click it to open History. With no scene open it reads "
        "//Snapshots// and is dimmed. The third is the sync item, "
        "described under “Git Sync” below; it is absent if git is "
        "not installed.")
    s.gfigure("fig_gstatusleft", "g_status_left", "The left end of the "
              "desktop status bar: the draft badge, the snapshot item "
              "and the sync item", width=330)

    # ------------------------------------------------------------------
    s.h2("Drafts of the Book: Draft N", idx=["draft|book-level", "Draft N",
                                            "start new draft"])
    s.p("A novel goes through drafts: the first rough pass, the "
        "second, the one you send to a reader. Lorewrite lets you "
        "mark the turning point. The project has a **draft number** "
        "that starts at 1 and appears in the status bar of the "
        "terminal application as //Draft 1//, and in the desktop "
        "application both as a tag in the title bar and as the first "
        "item at the left of the status bar.")
    s.p("**Starting a new draft** does exactly two things. It "
        "snapshots every scene in the project (the book and Unplaced), "
        "labeled //End of draft N//, and then it raises the number to "
        "N+1. It does not change a word of your text. The old draft "
        "is therefore not a separate copy you open; it lives in each "
        "scene's history, where you can find //End of draft 1// among "
        "the other snapshots, compare it with the scene as it has "
        "become, and restore it. If any scene cannot be snapshotted, "
        "the counter is not raised.")
    s.table("t_draftstart", "Starting a new draft",
            ["", "Terminal application", "Desktop application"], [
        ["Where", "Palette: //Action · Start new draft//",
         "Click the **Draft N** badge (title bar or status bar), then "
         "**Start draft N+1…**"],
        ["Confirmation", "//Start draft N+1?// Every scene is "
         "snapshotted now as ‘end of draft N’; your text is not "
         "changed. **Start new draft** or **Cancel**.",
         "Dialog titled //Start draft N+1//. **Cancel** or **Start new "
         "draft**."],
        ["Afterward", "//Draft N is saved as snapshots (‘end of draft "
         "N’). You are now on draft N+1.//",
         "//Draft N is saved as snapshots (“End of draft N”). You are "
         "now on draft N+1.//"],
    ], [0.17, 0.43, 0.40])
    s.p(f"In the desktop application, clicking the badge opens a small "
        f"menu ({R('fig_gdraftmenu')}) with the current draft as a "
        f"heading and the single command to start the next one. The "
        f"confirmation ({R('fig_gdraftconfirm')}) repeats what will "
        f"happen. In the terminal application the badge in the status "
        f"bar is only a display and cannot be clicked.")
    s.gfigure("fig_gdraftmenu", "g_draft_menu", "The menu of the Draft "
              "badge", width=200)
    s.gfigure("fig_gdraftconfirm", "g_draft_confirm", "Confirming the start "
              "of a new draft", width=300)
    s.note("There is no command to go back a draft. The number is the "
           "`draft` value in `project.toml` (below); it never affects "
           "your text, so it is harmless to leave it.")

    # ------------------------------------------------------------------
    s.h2("Git Sync (Optional)", idx=["git", "sync", "git|Synced status"])
    s.p("Snapshots protect you from your own edits. **Git** is a "
        "separate program that writers do not need but programmers "
        "love: it records the whole project folder as a series of "
        "commits, and can send them to a copy on another computer or "
        "a hosting service. If you already use git, Lorewrite can "
        "show whether your project has unrecorded changes and can "
        "commit and push for you. If you do not, you can ignore this "
        "section completely; nothing in Lorewrite depends on it.")
    s.p("The rules are deliberately cautious.")
    s.bullets([
        "Lorewrite only //looks// at git by itself, to show the "
        "status. It commits, pushes or initializes only when you "
        "choose to.",
        "A push always asks first, and is //never forced//. It cannot "
        "overwrite what is already on the remote.",
        "It never pulls, fetches, merges or switches branches. If "
        "another computer has newer work, bring it in with git "
        "yourself.",
        "It runs git in the project folder only, and only commits "
        "that folder. A project that sits inside a larger repository "
        "commits only its own files.",
        "Git needs to be installed. Without it, the status and "
        "the three commands below do not appear at all.",
    ])

    s.h3("The Status", idx=["git|status"])
    s.p(f"For a project under git, the sync item shows one of three "
        f"states ({R('t_syncstatus')}). The terminal application "
        f"shows it as the third part of the status bar, after the "
        f"scene and //Draft N//. Lorewrite checks it when the project "
        f"opens, a couple of seconds after each save, and after each "
        f"sync action.")
    s.table("t_syncstatus", "The sync status",
            ["Shows", "Means"], [
        ["Synced", "Nothing uncommitted and nothing waiting to be "
         "pushed."],
        ["//N// changes (or 1 change)", "There are //N// changed, "
         "added or removed files in the project folder not yet "
         "committed. Each new file counts."],
        ["Ahead //N//", "Everything is committed, but //N// commits "
         "have not been pushed to the remote."],
    ], [0.34, 0.66])
    s.attention("**Synced is not a backup.** If the repository has no "
                "remote, Synced only means that the changes are "
                "recorded in git //on this computer//, in a hidden "
                "folder inside the project. The desktop tooltip says so "
                "(//Committed (no remote is configured, so nothing is "
                "pushed).//). Also, Synced does not mean you are up to "
                "date: Lorewrite never shows whether the remote has "
                "commits you lack.")
    s.p("In the desktop application the item has a cloud icon: crossed "
        "out for a project not under git (it reads //Sync//), with a "
        "check when synced, and with an arrow and an accent color "
        "when there is something to commit or push. Hover for a "
        "sentence explaining it.")

    s.h3("Committing", idx=["git|commit"])
    s.p("A **commit** records the current state of the project folder "
        "with a message. Everything in the folder is included: "
        "scenes, notes, research, `project.toml`, the `.snapshots/` "
        "and `.drafts/` folders, and your settings files. Only the "
        "index cache, `.lorewrite/`, is left out, because Lorewrite "
        "puts a line for it in the project's `.gitignore`. Your name "
        "and e-mail address must already be set in git; if not, git's "
        "own complaint appears.")
    s.p(f"Choose //Action · Commit changes// in the terminal "
        f"application, or click the sync item and choose **Commit "
        f"//N// changes…** in the desktop application. Lorewrite saves "
        f"the open scene first and offers a message such as "
        f"//lorewrite: 2026-10-01 — 3 scenes changed// (when no scene "
        f"changed it counts //files//), which you can edit "
        f"({R('fig_tuicommit')}, {R('fig_gcommit')}). The terminal "
        f"prompt says //Commit// //N// //change(s) in this project "
        f"folder (enter commits, esc cancels)//; the desktop dialog, "
        f"**Commit changes**, names the repository and says //Nothing "
        f"is pushed.// An empty message is not accepted. When it is "
        f"done, a message shows //Committed:// followed by git's "
        f"summary line. If there is nothing to commit, you are told so.")
    s.figure("fig_tuicommit", "tui_commit", "The commit-message prompt of "
             "the terminal application, with the suggested message")
    s.gfigure("fig_gcommit", "g_commit", "The desktop Commit changes "
              "dialog", width=300)

    s.h3("Pushing", idx=["git|push"])
    s.p("A **push** sends your commits to a remote copy. For it to be "
        "offered, three things must already be true, and Lorewrite "
        "cannot set up any of them for you:")
    s.bullets([
        "The repository has a **remote** (such as `origin`), added "
        "with git outside Lorewrite.",
        "You are on a **branch** (not in the detached state that git "
        "uses when looking at an old commit).",
        "Your **credentials work without being asked**. Lorewrite "
        "runs git with prompts turned off, so it cannot ask you for "
        "a password or a key's passphrase. Use a credential helper, "
        "an SSH agent, or a key that needs no passphrase. If a push "
        "needs to ask, it simply fails and shows git's own error.",
    ])
    s.p(f"Choose //Action · Push// in the terminal application, or "
        f"**Push //N// commits to //remote//…** in the sync menu of "
        f"the desktop application ({R('fig_gsyncmenu')}). Both ask "
        f"for confirmation ({R('fig_gpush')}), naming the branch, the "
        f"remote and its address, and saying //It is never forced.// "
        f"The first push of a branch also sets it to follow the "
        f"remote. Afterward you see //Pushed// //branch// //to// "
        f"//remote//. In the desktop menu, Push is dimmed with "
        f"//(nothing to push)// when you are not ahead, and absent "
        f"when there is no remote.")
    s.gfigure("fig_gsyncmenu", "g_sync_menu", "The desktop sync menu: "
              "commit, push and refresh", width=230)
    s.gfigure("fig_gpush", "g_push", "The Push confirmation", width=300)

    s.h3("Initialize Git", idx=["git|initialize"])
    s.p("If the project folder is not under git, the terminal palette "
        "offers //Action · Initialize git for this project//, and the "
        "desktop sync menu offers **Initialize git for this "
        "project…**. After a confirmation Lorewrite turns the folder "
        "into a repository and makes sure `.gitignore` hides "
        "`.lorewrite/`. It does not commit anything, add a remote or "
        "name a branch. The offer is not made for a project that is "
        "inside another repository.")
    s.p(f"The palette entries are listed in {R('t_histpalette')} "
        "(Chapter 14 lists every command).")
    s.table("t_histpalette", "Palette actions for history and sync",
            ["Entry", "What it does"], [
        ["Scene · Snapshots", "Open the Snapshots screen."],
        ["Scene · Snapshot scene", "Snapshot the open scene with an "
         "optional label."],
        ["Action · Snapshot all scenes", "Snapshot every scene with "
         "one label."],
        ["Action · Start new draft", "Snapshot every scene as the end "
         "of the draft, then count up."],
        ["Action · Commit changes", "Commit the project folder."],
        ["Action · Push", "Push the branch to its remote, after a "
         "confirmation."],
        ["Action · Initialize git for this project", "Make the folder "
         "a git repository."],
    ], [0.42, 0.58])
    s.note("The three git entries appear only when they apply: "
           "Commit when the project is under git, Push when it also "
           "has a remote and a branch, Initialize when it is not under "
           "git. None appear without git installed.")

    # ------------------------------------------------------------------
    s.h2("On Disk", idx=[".snapshots", "project.toml|draft"])
    s.p("Snapshots are plain Markdown files in a folder called "
        "`.snapshots/` at the top of the project, with one subfolder "
        "per scene. The folder is named after the scene's path with "
        "each `/` written as `__`. Appendix A describes every file; "
        "here is the shape.")
    s.code("""\
my-novel/
  project.toml
  manuscript/01-the-recall/02-capsule.md
  .snapshots/
    manuscript__01-the-recall__02-capsule.md/
      20261001-101500.md
      20261001-101500--auto.md
      20261001-143200--before-the-rewrite.md
      20261002-090011--before-restore.md
      20261002-090011--before-restore.json
""")
    s.p("A file name is the date and time, then two hyphens and a "
        "label if there is one. Two snapshots in the same second get "
        "a number (`20261001-101500-2--auto.md`) rather than "
        "overwriting each other. A label you type is tidied for the "
        "file name: spaces are collapsed, and characters that file "
        "systems dislike are changed to hyphens. The `.md` file is "
        "the scene, word for word, front matter included. The "
        "optional `.json` beside it holds the originals of any "
        "pending AI drafts at that moment. You may open snapshots in "
        "any editor, copy text out of them, or delete them by hand. "
        "Snapshots are ordinary project files: they are not hidden "
        "from git and are committed with everything else.")
    s.p("The draft number is one line of `project.toml`, next to the "
        "unit:")
    s.code("""\
[manuscript]
unit = "scene"
draft = 2
""")
    s.p("A missing or invalid value counts as 1.")

    # ------------------------------------------------------------------
    s.h2("Things to Know", idx=["snapshot|limits"])
    s.bullets([
        "**Snapshots are not a backup.** They live in the project "
        "folder. Back up the folder too.",
        "**The daily snapshot is the //start// of the day**, not the "
        "end: it holds the scene as it was before that day's first "
        "change. To keep an end-of-day state, take a snapshot of your "
        "own.",
        "**Nothing is ever pruned.** Delete snapshots yourself if "
        "the folder grows larger than you like.",
        "**Spaces and old text.** Compare can be slow on a huge "
        "scene that has been almost completely rewritten; Lorewrite "
        "then shows the whole changed stretch as one replacement "
        "instead of word by word.",
        "**Git commits everything**, including research notes, "
        "`.snapshots/` and `.drafts/`, not just scenes. The count in "
        "the suggested message counts scenes only.",
        "**The terminal and desktop wording differ slightly** (for "
        "example, //+-0// versus //±0// for no change in the word "
        "count); the meaning is the same.",
    ])


GLOSSARY = [
    ("snapshot", "A saved copy of one scene at a moment in time, kept in "
     "the `.snapshots/` folder. Taken by you, or automatically."),
    ("History", "The desktop dialog (and, in the terminal, the Snapshots "
     "screen) that lists a scene's snapshots."),
    ("compare", "Showing a snapshot against the scene as it is now, with "
     "removed words marked and added words marked."),
    ("restore", "Replace a scene with a snapshot. The scene as it was is "
     "snapshotted first as //Before a restore//."),
    ("automatic snapshot", "A snapshot Lorewrite takes by itself: the "
     "first edit of a day, before a restore, before accept all or reject "
     "all, and at the end of a draft."),
    ("draft number", "A counter for the whole book (//Draft 2//), kept "
     "in `project.toml`. Not the same as an AI draft."),
    ("start new draft", "Snapshot every scene as //End of draft N// and "
     "count up to draft N+1. Text is unchanged."),
    ("git", "An outside program that records a folder's history; "
     "optional with Lorewrite."),
    ("commit", "In git, a recorded state of the project folder with a "
     "message."),
    ("push", "Send commits to a remote copy. Asks first; never forced."),
    ("remote", "The other copy of a git repository, on another computer "
     "or a hosting service."),
    ("Synced", "The sync status meaning nothing uncommitted and nothing "
     "unpushed. Not a backup if there is no remote."),
]

MSG_TUI = {
    "info": [
        ["Snapshot taken", "A snapshot of the scene was saved."],
        ["Snapshot taken: //label//", "Likewise, with your label."],
        ["Snapshot taken of //N// scene(s)", "Snapshot all scenes "
         "finished."],
        ["Snapshot restored; the text from before is kept as ‘before a "
         "restore’", "The restore worked and can itself be undone."],
        ["Draft //N// is saved as snapshots (‘end of draft //N//’). "
         "You are now on draft //N+1//.", "A new draft was started."],
        ["Committed: //git line//", "The commit worked."],
        ["Pushed //branch// to //remote//", "The push worked."],
        ["This folder is now a git repository. Nothing is committed "
         "yet.", "Initialize git finished."],
        ["Nothing to commit: everything is already committed",
         "Commit changes was chosen with no changes."],
    ],
    "warn": [
        ["Open a scene first", "A snapshot command needs an open scene."],
        ["No remote is configured for this project", "Push needs a "
         "remote."],
        ["This project is not in a git repository", "Commit needs git."],
    ],
    "err": [
        ["Could not start a new draft: //reason//", "A scene could not "
         "be snapshotted; the draft number is unchanged."],
    ],
}

MSG_GUI = [
    ["Open a scene to see its history.", "History needs an open scene."],
    ["Snapshot taken.", "A snapshot was saved (with a label, the label "
     "is shown)."],
    ["Snapshot taken of //N// scenes.", "Snapshot all finished."],
    ["Snapshot restored. The text from before is kept as “Before a "
     "restore”.", "The restore worked."],
    ["Could not save the current text first; nothing was restored.",
     "Restore stopped; nothing changed."],
    ["Draft //N// is saved as snapshots (“End of draft //N//”). You "
     "are now on draft //N+1//.", "A new draft was started."],
    ["Could not save the current document first.", "Starting a draft "
     "stopped."],
    ["Committed: //git line//", "The commit worked."],
    ["Could not save the current document first; nothing was "
     "committed.", "Commit stopped; nothing changed."],
    ["Pushing…  /  Pushed //branch// to //remote//", "A push is "
     "running / done."],
    ["This folder is now a git repository. Nothing is committed yet.",
     "Initialize git finished."],
]

PALETTE = [
    ["Scene · Snapshots", "Open the Snapshots screen for the open scene.",
     ""],
    ["Scene · Snapshot scene", "Snapshot the open scene, with an "
     "optional label.", ""],
    ["Action · Snapshot all scenes", "One snapshot of every scene, with "
     "one label.", ""],
    ["Action · Start new draft", "Snapshot every scene as the end of "
     "this draft, then count up.", ""],
    ["Action · Commit changes", "Git: commit the project folder.", ""],
    ["Action · Push", "Git: push the branch, after confirming.", ""],
    ["Action · Initialize git for this project", "Make the folder a git "
     "repository.", ""],
]

PROBLEMS = [
    ["I changed my mind about a restore.", "Open History and restore "
     "the snapshot named //Before a restore//."],
    ["History says //Open a scene to see its history.//", "Snapshots "
     "exist only for scenes. Open a scene, not a note."],
    ["Push is missing or fails.", "The project needs a remote and a "
     "branch, and credentials that work without a prompt. Add the "
     "remote with git, and set up a credential helper or SSH agent."],
    ["Commit fails with a message about a name or e-mail address.",
     "Tell git who you are (`user.name` and `user.email`), then try "
     "again."],
    ["The status says Synced but I have no other copy.", "Synced with "
     "no remote only means committed on this computer. Copy the "
     "folder elsewhere or add a remote and push."],
    ["There is no sync item.", "Git is not installed, or git could "
     "not be run. Install git."],
]
