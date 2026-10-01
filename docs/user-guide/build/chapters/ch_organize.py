"""Chapter 5: Organizing the Manuscript."""


def build(s, R):
    s.chapter("5", "Organizing the Manuscript",
              "Parts, front matter, the order of the book, scenes kept out "
              "of it, the Trash, scene details and collections.")

    s.p("A manuscript is more than a pile of scenes. This chapter is about "
        "the shape of the book: how scenes are grouped into //parts//, "
        "what order they read in, where a scene goes when you want to keep "
        "it but not count it, what happens to a scene you delete, and how "
        "to attach a few facts (status, point of view, a word target) and "
        "your own labels to a scene. Everything here is done with ordinary "
        "folders and files, so you can always see and repair the result "
        "with a file manager. Writing the scenes themselves is Chapter 4.",
        idx=["manuscript", "structure"])

    # ------------------------------------------------------------------
    s.h2("How the Book Is Laid Out", idx=["part", "manuscript folder",
                                          "reading order"])
    s.p("Every scene is a Markdown file in the `manuscript` folder of the "
        "project. A scene can sit in one of three places:")
    s.bullets([
        "**Directly in `manuscript`.** Such a scene is //loose//. This is "
        "how a new project starts: a flat list of scenes.",
        "**In a part.** A part is a folder inside `manuscript` with a "
        "numeric prefix, such as `01-the-recall`. Only one level of "
        "folders is recognized; a folder inside a part is ignored.",
        "**In `_unplaced`.** This special folder holds scenes you have "
        "written but taken out of the book (see “Unplaced Scenes” below). "
        "Because its name begins with an underscore it is not a part.",
    ])
    s.p("Files and folders whose names begin with `_` or `.` are never "
        "scenes or parts. Inside a part, an optional file `_part.md` holds "
        "the part's title as its first heading (`# The Recall`). Lorewrite "
        "creates it when you make a part. If the file is missing, the "
        "title is made from the folder name: `02-ghost-frequency` becomes "
        "//Ghost Frequency//.")
    s.code("""\
my-novel/
  manuscript/
    05-loose-scene.md           a loose scene
    00-front-matter/            a part: front matter (see below)
      _part.md                  # Front Matter
      01-title.md
    01-the-recall/              a part
      _part.md                  # The Recall
      01-rain-on-the-spur.md
      02-capsule-7-19.md
    02-ghost-frequency/
      01-signal.md
    _unplaced/                  written, but not in the book
      01-draft.md
  .trash/                       deleted scenes and research notes""")

    s.h3("Reading order and numbering", idx=["numbering", "scene numbers"])
    s.p("Files are put in order by their numeric prefix, read as a number "
        "(`2-` comes before `10-`), and then by name; a name with no prefix "
        "comes last. The //book// reads in this order:")
    s.bullets([
        "loose scenes first, whatever their numbers,",
        "then each part in the order of its folder prefix, and the scenes "
        "of each part in the order of theirs.",
    ])
    s.p("Unplaced scenes are not in the book at all. The next scene and "
        "previous scene keys (`alt+right` and `alt+left` in the terminal "
        "application) follow this order and skip the unplaced scenes.")
    s.p("The number shown to the writer depends on whether the project "
        "has any parts. Without parts, a scene's number is simply its "
        "file prefix (`01`, `04`), so a gap in the files shows as a gap. "
        "Once any part exists, the number is the scene's //position in the "
        "book//, counting loose scenes and then the parts, two digits "
        "(`03`). Front matter and unplaced scenes have no number. The "
        "desktop application shows the number on corkboard cards "
        "(//SCENE 03//) and in the binder and outline; the terminal "
        "application shows only titles, and the status bar shows the file's "
        "path.")
    s.note("Creating the first part does not move the scenes you already "
           "have. They stay loose, and still read first. Move them into "
           "the part with **Move scene to part** (below).")

    # ------------------------------------------------------------------
    s.h2("Parts", idx=["part|create", "part|rename", "part|move", "part|delete"])
    s.p("Make a part when the book has sections you want to see as "
        "sections: Part I and Part II, the days of a week, a prologue. "
        "A new part is a folder numbered after the highest part you "
        "already have, so it goes last. Its name comes from its title: "
        "//The Long Dark// becomes `03-the-long-dark` when parts 00, 01 "
        "and 02 exist.")
    s.p(f"In the terminal application the sidebar shows each part as a "
        f"header in capital letters above its scenes ({R('fig_tuiparts')}). "
        "A project without parts looks like a flat list. The header is not "
        "a row you can open.")
    s.figure("fig_tuiparts", "tui_parts", "The terminal sidebar grouping "
             "scenes under part headers")
    s.p("In the desktop application the binder is a tree "
        f"({R('fig_obinder')}). From the top it shows the front matter "
        "(muted), a **Manuscript** folder for loose scenes (only when "
        "there are some, or when there are no other parts), each part, "
        "then **Characters**, **World Bible**, **Style Guide**, "
        "**Dictionary**, **Research**, **Unplaced Scenes** and **Trash**, "
        "with the **Collections** list underneath. The number beside the "
        "project's name is the word count of the book (see “Word "
        "Counts”). Clicking a part selects it and opens or closes it.")
    s.gfigure("fig_obinder", "g_binder", "The desktop binder: front "
              "matter, two parts, the notes groups, Unplaced Scenes, the "
              "Trash and the Collections list", width=150,
              crop=(0, 1, 0, 0.8))

    s.h3("Working with parts", idx=["new part", "move part", "rename part",
                                    "delete empty part"])
    s.table("t_parttasks", "Part tasks in the two applications",
            ["Task", "Terminal application", "Desktop application"], [
        ["Make a part", "**Action · New part**. Asks //New part title://.",
         "Binder **…** menu (//Scene and part options//) > **New part…**. "
         "Dialog //New part//, field //Title//, button **Create**."],
        ["Rename a part", "**Action · Rename part**. Asks //Rename part "
         "'//title//' to://.", "**…** menu > **Rename part “//title//”…**."
         " Dialog //Rename part//."],
        ["Move a part earlier or later", "**Action · Move part up** and "
         "**Action · Move part down**.", "**…** menu > **Move part up** "
         "and **Move part down**."],
        ["Delete an empty part", "**Action · Delete empty part**, then "
         "confirm.", "**…** menu > **Delete empty part…**, then **Delete "
         "part**."],
        ["Move a scene to a part", "**Action · Move scene to part**.",
         "**…** menu > **Move scene to part…**, or drag in the "
         "corkboard (below)."],
        ["Move a scene up or down inside its part", "**Action · Move "
         "current scene up** and **down**.", "**…** menu > **Move up** and "
         "**Move down**."],
    ], [0.22, 0.38, 0.40])
    s.p("Some details are worth knowing.")
    s.bullets([
        "The part actions of the terminal application always ask which "
        "part: a picker titled //Rename which part?//, //Move which "
        "part?// or //Delete which (empty) part?// lists the parts, with "
        "the part of the open scene already chosen. It works with no "
        "scene open, and with a note or an unplaced scene open. In the "
        "desktop application the part actions work on the "
        "part you last clicked in the binder, or else the part of the "
        "open scene.",
        "Renaming a part changes only its title (the heading in "
        "`_part.md`). The folder keeps its old name for good, which is "
        "harmless.",
        "Moving a part swaps its folder prefix with its neighbor's. Both "
        "must have numeric prefixes (`01-`, `02-`); otherwise Lorewrite "
        "says the part is at the edge. Scenes follow their folder, and so "
        "do their snapshots, comments and pending drafts.",
        "Only an //empty// part can be deleted. Move its scenes out "
        "first. A stray non-scene file inside the folder also stops the "
        "deletion; `_part.md` itself is removed for you.",
        "Notes written below the heading of `_part.md` are kept, but no "
        "screen shows or edits them. Edit the file by hand if you want "
        "them.",
    ])

    s.h3("Moving a scene to a part", idx=["move scene to part"])
    s.p("In the terminal application, open the scene and use **Action · "
        "Move scene to part**. A list //Move '//scene//' to which "
        "part?// shows every part, front matter included, and "
        "//(no part - top level)//. In the desktop application the dialog "
        f"({R('fig_gmovepart')}) is titled //Move scene to a part//, says "
        "//It goes to the end of the part you pick.//, and lists each part "
        "with its scene count and, last, //No part (top level)//. The "
        "scene is added at the end of the part you pick. The scenes of "
        "the destination are renumbered in order, and the folder the "
        "scene left is not (see “Quirks and Limits”).")
    s.gfigure("fig_gmovepart", "g_move_to_part", "The Move scene to a part "
              "dialog in the desktop application", width=300)
    s.gfigure("fig_omenu", "g_binder_menu", "The Scene and part options "
              "menu in the binder, with the scene, part, research and "
              "Trash commands", width=200)
    s.p(f"The menu of {R('fig_omenu')} is the home of nearly every "
        "structure command in the desktop application. The scene items "
        "are disabled until a scene is open, and the part items until a "
        "part is in focus.")

    # ------------------------------------------------------------------
    s.h2("Front Matter", idx=["front matter"])
    s.p("Front matter is the title page, dedication, epigraph and similar "
        "pages that come before the story. It is kept out of the numbers "
        "and the word count of the book but still read, checked for "
        "spelling and indexed for links. It is a part whose folder name, "
        "after the numeric prefix, is exactly `front-matter`: "
        "`00-front-matter`. Its title can be anything.")
    s.p("**There is no front matter button or menu entry.** You make it "
        "like this.")
    s.proc("To make front matter:", [
        "Make a part titled //Front matter// (see above). It is created "
        "last, perhaps as `03-front-matter`; Lorewrite recognizes it by "
        "that name at once.",
        "Move it first with **Move part up**, once for every part in "
        "front of it. Or, with the project closed, rename the folder to "
        "`00-front-matter` in your file manager.",
        "Put the pages in it with **Move scene to part**, or make new "
        "scenes while a front-matter page is open (a new scene goes into "
        "the part of the scene you have open).",
    ])
    s.p("Front matter is shown muted in the desktop binder and as the "
        "kicker //FRONT MATTER// on a corkboard card. In the terminal "
        "application it looks like any other part. Where it sits in the "
        "reading order depends on its folder prefix: a `00-` prefix puts "
        "it first, but loose scenes still read before every part.")

    # ------------------------------------------------------------------
    s.h2("Unplaced Scenes", idx=["unplaced scenes", "_unplaced"])
    s.p("Sometimes you write a scene you are not ready to cut but do not "
        "want in the book: an alternate opening, a scene that may belong "
        "to the sequel. **Unplaced** scenes are kept in `_unplaced`. "
        "They are not in the reading order, have no scene number, and are "
        "not counted in the book. They are still real scenes: you can "
        "open and edit them, they are spell-checked, linked and indexed "
        "(so their characters have backlinks), they take part in "
        "snapshots, collections and search, and they appear in the "
        "palette and quick switcher.")
    s.table("t_unplaced", "Taking scenes out of the book and putting "
            "them back",
            ["Task", "Terminal application", "Desktop application"], [
        ["Unplace the open scene", "**Action · Move scene to Unplaced**. "
         "Message //Moved to Unplaced scenes (not counted in the book)//.",
         "**…** menu > **Move to Unplaced Scenes**. Toast //Moved to "
         "Unplaced Scenes. It no longer counts in the book.// No "
         "confirmation, and no Undo."],
        ["Put it back", "Open the unplaced scene, then **Action · Place "
         "scene in the book**; pick a part from //Place in which part?//.",
         "Open it; the **…** menu shows **Place in the book…** instead. "
         "Or drag its card into a part in the corkboard."],
        ["Find them", "Sidebar header //UNPLACED SCENES//, after the "
         "last part.", "Binder group **Unplaced Scenes** (with a count); "
         "the last group of the Corkboard and Outline."],
    ], [0.20, 0.38, 0.42])
    s.p("A placed scene goes to the end of the part you choose. The "
        "binder's breadcrumb for an unplaced scene reads //Unplaced "
        "Scenes > Scene//.")

    # ------------------------------------------------------------------
    s.h2("The Trash", idx=["trash", ".trash", "delete scene", "restore"])
    s.p("Lorewrite never deletes a scene outright. **Delete** moves it to "
        "the Trash, a hidden `.trash` folder in the project, from which "
        "it can be restored or, deliberately, deleted forever. Deleted "
        "research notes (Chapter 9) go to the same place. The Trash lists "
        "the newest first, with the date and where each item came from.")
    s.table("t_trashdo", "Deleting and the Trash",
            ["Task", "Terminal application", "Desktop application"], [
        ["Delete the open scene", "**Action · Delete current scene**, "
         "then **Move to Trash** at //Move scene '//title//' to the "
         "Trash? You can restore it from Action · Open Trash.//",
         "**…** menu > **Delete scene…**; dialog //Move scene to the "
         "Trash//; button **Move to Trash**."],
        ["Open the Trash", "**Action · Open Trash**.", "Binder **Trash** "
         "row, or **…** menu > **Open Trash…**."],
        ["Restore", "`enter` or `r` on the row.", "**Restore** on the "
         "row."],
        ["Delete one item forever", "`d`, then **Delete forever**.",
         "**Delete forever** on the row, then confirm."],
        ["Empty the Trash", "`e`, then **Empty Trash**.", "**Empty "
         "Trash** (disabled when empty), then confirm."],
    ], [0.22, 0.38, 0.40])
    s.figure("fig_tuitrash", "tui_trash", "The Trash in the terminal "
             "application. Each row shows the title, the date and the "
             "place it came from")
    s.p(f"The terminal Trash ({R('fig_tuitrash')}) is a window with "
        "`enter` or `r` to restore, `d` to delete forever, `e` to empty "
        "the Trash and `esc` to close. Restoring asks nothing and shows "
        "where the scene went, for example //Restored to "
        "01-the-recall/03-a.md//; the window stays open so you can "
        "restore several. In the desktop application "
        f"({R('fig_gtrash')}) restoring closes the dialog and opens the "
        "restored scene.")
    s.gfigure("fig_gtrash", "g_trash", "The Trash dialog in the desktop "
              "application, with Restore and Delete forever on each row",
              width=330)

    s.h3("Where a restored scene goes", idx=["restore|scene"])
    s.p("A scene returns to the end of the folder it was deleted from. If "
        "that part has since been deleted or renumbered away, the scene "
        "goes to Unplaced Scenes instead, and the desktop application "
        "says so: //Restored “Rain”: its part is gone, so it went to Unplaced "
        "Scenes.// When the part still exists the toast names it (//Restored "
        "“Rain” to The Recall.//), and a scene that was unplaced to begin "
        "with is reported as //Restored “Rain” to Unplaced Scenes.// It is given the next free number in that folder; its "
        "neighbors are not renumbered, so it may differ from its old "
        "number. Its snapshots, comments and pending AI drafts come back "
        "with it. A research note returns to `research/` under its "
        "old name, or with `-2` added if the name is taken.")
    s.h3("What is in the Trash folder")
    s.p("A trashed file is named with its date and old location, with "
        "folder separators written as double underscores:")
    s.code("""\
.trash/20261001-101500-manuscript__01-the-recall__01-a.md
.trash/20261001-102200-research__tides__almanac.md""")
    s.p("Beside a scene may be small companion files for its snapshots, "
        "comments and pending drafts. Appendix A describes them. The "
        "folder is created at the first deletion and removed when it is "
        "empty again.")
    s.attention("**Empty Trash removes the whole `.trash` folder**, "
                "including any file of your own that you put there. The "
                "count it reports covers only items Lorewrite recognizes. "
                "Deleting forever cannot be undone.")

    # ------------------------------------------------------------------
    s.h2("Scenes or Chapters", idx=["scene label", "chapter label",
                                    "unit|scene or chapter"])
    s.p("Some writers think in scenes, others in chapters. A single "
        "setting decides which word Lorewrite uses for the units of the "
        "book. It changes //labels only//: no file or folder is renamed, "
        "and nothing on disk changes except one line of `project.toml`:")
    s.code("""\
[manuscript]
unit = "chapter"        # "scene" (the default) or "chapter\"""")
    s.p("In the terminal application run **Action · Call them chapters** "
        "(when the wording is scenes) or **Action · Call them scenes** "
        "(when it is chapters); each time it flips, and says //Labels now "
        "say 'chapter'// (or //'scene'//). The palette then reads "
        "**Chapter · Edit details**, **Action · New chapter**, **Action · "
        "Move current chapter up**, and so on, and the sidebar heading "
        "becomes //Chapters//. In the desktop application open the "
        "title bar's **More** (…) menu and choose **Call scenes "
        "“chapters”** (or **Call chapters “scenes”**). The toast says "
        "//Labels now say “chapter”. Only the wording changes.// The "
        "kicker on a card reads //CHAPTER 03//, and the menus, dialogs "
        "and corkboard wording follow. There is no entry in Settings "
        "for it.")
    s.p("Some texts do not change: the //Unplaced Scenes// group names, a "
        "few messages such as //Open a scene first//, and the Trash's "
        "wording. The palette entry that switches the setting keeps a "
        "clear name of its own in both states.")

    # ------------------------------------------------------------------
    s.h2("Scene Details", idx=["scene details", "status", "point of view",
                               "word target", "frontmatter|scene details"])
    s.p("Each scene can carry a few facts that are about the scene, not in "
        "it. They help you plan and see the state of the book at a "
        "glance.")
    s.table("t_details", "The scene details",
            ["Field", "Meaning"], [
        ["Status", "Free text. Suggested values are //idea//, //draft//, "
         "//revising// and //done//; use your own."],
        ["POV", "The point-of-view character. Any name; character names "
         "are offered."],
        ["Place", "Where the scene happens. Any name; place names are "
         "offered."],
        ["Scene purpose", "What the scene is for in the story, in a "
         "sentence or two (//Chapter purpose// when the label is "
         "chapter)."],
        ["Target words", "A number of words you aim for. Blank means no "
         "target. Commas are accepted (//2,400//)."],
    ], [0.24, 0.76])

    s.h3("What is stored", idx=["frontmatter"])
    s.p("Details are written as a small block at the very top of the "
        "scene file, between two lines of three dashes (the "
        "//frontmatter//). A field you leave empty is not written, and a "
        "scene with no details has no block at all. The title heading "
        "follows the block.")
    s.code("""\
---
pov: Mara Vale
place: Lower Meridian
purpose: First contact with Elias's signal
status: revising
target: 2400
collections: [Needs continuity pass]
---
# A City That Remembers""")
    s.p("The block holds the details and the scene's collections (see "
        "below). Any other keys you add by hand are kept. Whitespace in "
        "a value is collapsed to one line, and a list is written on one "
        "line in square brackets. Snapshots keep the whole file, block "
        "included.")
    s.p("The block is //not prose//. It is left out of every word count "
        "(the status bars, the project total, session statistics, "
        "snapshots' word counts), of spell check, of the search for "
        "mentions, of continuity checks and of style sampling. One "
        "exception: a POV or place that is the name of a note counts as "
        "a mention, so the scene shows up in that character's or place's "
        "backlinks. The AI receives the details as a short header "
        "(status, POV, place, purpose), not as raw text; the target and "
        "the collections are not sent.")

    s.h3("In the terminal application")
    s.p("Run **Scene · Edit details** (**Chapter · Edit details** when "
        "the label is chapter). The window "
        f"({R('fig_tuidetails')}) has five fields: //POV character//, "
        "//Place//, //Scene purpose//, //Status (idea / draft / revising "
        "/ done, or your own)// and //Target words (a number, blank for "
        "none)//. `tab` moves between them, the right arrow accepts a "
        "suggested name, `enter` or `ctrl+s` saves and `esc` cancels. "
        "A target that is not a number stops with //Target must be a "
        "number of words//. Saving says //Details saved//.")
    s.figure("fig_tuidetails", "tui_details", "The Scene details window "
             "in the terminal application")
    s.p("In the terminal editor the block is shown faded and is ordinary "
        "text, so you can also edit it directly.")

    s.h3("In the desktop application", idx=["inspector"])
    s.p("The block is hidden in the editor; the facts are shown above and "
        f"below the page. Above it is the context row ({R('fig_gcontext')}): "
        "the breadcrumb, a status tag (//Revising//, or //No status//) and "
        "the word target chip (//1,942 / 2,400 words//, or just //1,942 "
        "words// without a target). Below the page is the details strip "
        f"({R('fig_gstrip')}) with the cells //Status//, //POV / Place//, "
        "//Scene purpose//, //Collections// and //Session//.")
    s.gfigure("fig_gcontext", "g_context", "The context row above the "
              "page: breadcrumb, status tag and word target", width=418)
    s.gfigure("fig_gstrip", "g_strip", "The details strip below the "
              "page", width=418)
    s.p(f"Click the status tag, the word target chip, or the Status, POV / "
        f"Place or Scene purpose cell to open the //Scene details// "
        f"dialog ({R('fig_gdetails')}). Its fields are //Status//, //POV//, "
        "//Place//, //Scene purpose// and //Target words//. A target that "
        "is not a number shows //A number of words, like 2400.// and "
        "disables **Save**. The **Collections** cell opens the "
        "collections dialog instead (below).")
    s.gfigure("fig_gdetails", "g_details_dialog", "The Scene details "
              "dialog", width=300)
    s.p("Saving the dialog is an ordinary edit of the page, so `ctrl+z` "
        "undoes it, and autosave writes it. The corkboard cards and "
        "outline rows show the same facts: status, POV and words, or "
        "words against the target.")

    # ------------------------------------------------------------------
    s.h2("Reordering in the Corkboard and Outline",
         idx=["corkboard", "outline", "drag and drop", "reorder"])
    s.p("The terminal application has no mouse reordering; use **Move "
        "current scene up**, **Move current scene down** and **Move scene "
        "to part**. The desktop application adds two views of the whole "
        "book next to the page, chosen in the editor's toolbar: "
        "**Manuscript**, **Corkboard** and **Outline**. Both can reorder "
        "scenes by dragging.")
    s.p("The Corkboard "
        f"({R('fig_ocork')}) shows a card for each scene, with its "
        "kicker (//SCENE 07//, //FRONT MATTER//, //UNPLACED//), title, "
        "an excerpt and its status, POV and words. The cards are in "
        "groups: loose scenes (titled only when parts exist), each part, "
        "and last //Unplaced scenes//. A header gives each group's title "
        "and scene count.")
    s.gfigure("fig_ocork", "g_corkboard", "The Corkboard, with the cards "
              "in parts", width=380)
    s.p("The Outline "
        f"({R('fig_goutline')}) lists the same scenes as rows "
        "(//03  Title//) with the headings of each scene beneath. Drag "
        "a row by the grip handle at its left.")
    s.gfigure("fig_goutline", "g_outline", "The Outline, with parts",
              width=380)
    s.proc("To move a scene by dragging:", [
        "Drag a card (or an outline row by its handle) onto another "
        "card to put the scene //before// that card, in that card's "
        "part; or onto the strip at the end of a group, "
        "//Drop here to put it at the end of// the part.",
        f"Lorewrite always asks you to confirm ({R('fig_gdrag')}): "
        "//Move “//title//” to position //n// in //part//?// or, to "
        "another group, //Move “//title//” to //part//, position //n//?//. "
        "Press **Move**; **Cancel** is the default.",
        "A toast says //Moved “//title//”.// with an **Undo** button.",
    ])
    s.gfigure("fig_gdrag", "g_drag_confirm", "The confirmation before a "
              "scene is moved by dragging", width=300)
    s.p("Dropping a scene where it already is does nothing and asks "
        "nothing. Dropping a card on the //Unplaced scenes// group takes "
        "it out of the book; dragging a card out of that group places it. "
        "The scene is saved before it moves and stays open. The binder "
        "itself does not accept drags of scenes.")
    s.attention("The **Undo** button exists only in that toast, which "
                "stays for about nine seconds. It is not `ctrl+z`. "
                "Undo moves the scene back to its old part and place, but "
                "the file numbers may not return to exactly what they "
                "were if the folder had gaps.")

    # ------------------------------------------------------------------
    s.h2("Collections", idx=["collections", "collection|filter",
                             "tag"])
    s.p("A **collection** is a label you invent and put on scenes, as many "
        "as you like on a scene and as many scenes as you like in a "
        "collection: //Needs continuity pass//, //Mara's arc//, "
        "//Ask Elena//. Collections cut across parts. A scene can be in "
        "any number of them, and putting it in one never moves it. "
        "Unplaced scenes can be in collections; trashed scenes cannot.")
    s.p("A collection has a name (up to 60 characters; names that differ "
        "only in capitals are the same name) and one of five colors: "
        "violet (the default for a new one), amber, green, red and "
        "gray. The definitions are in `project.toml`; the members are "
        "recorded in each scene's own frontmatter, so a collection "
        "travels with its scenes:")
    s.code("""\
[collections]
"Needs continuity pass" = "amber"
"Mara's arc" = "violet\"""")
    s.p("and, in a scene file, `collections: [Needs continuity pass, "
        "Mara's arc]` inside the block shown earlier. A name used by a "
        "scene but not defined in `project.toml` is still listed, in "
        "gray, until you choose a color for it.")

    s.h3("Collections in the terminal application")
    s.p("Run **Scene · Collections**. The window "
        f"({R('fig_tuicoll')}) is titled //Collections - //scene "
        "title// and lists the collections with a tick box for the open "
        "scene, a colored dot, the name and how many scenes it holds.")
    s.figure("fig_tuicoll", "tui_collections", "The Collections window in "
             "the terminal application")
    s.table("t_collkeys", "Keys in the Collections window",
            ["Key", "Action"], [
        ["space, enter", "Tick or untick the collection for the open "
         "scene."],
        ["n", "New collection. Asks //New collection name://. It starts "
         "violet."],
        ["r", "Rename it."],
        ["c", "Change the color. It cycles through violet, amber, "
         "green, red and gray; there is no picker."],
        ["d", "Delete the collection, after a confirmation. It is taken "
         "off its scenes; no scene is deleted."],
        ["esc", "Close."],
    ], [0.22, 0.78], mono_cols=(0,))
    s.p("To see only the members of a collection, type `#` and part of "
        "its name in the sidebar filter: `#arc` lists the scenes of every "
        "collection whose name contains //arc//. The sidebar shows no "
        "colors, and there is no corkboard in the terminal application.")

    s.h3("Collections in the desktop application")
    s.p("The bottom of the binder lists the collections, each with a "
        "color swatch, its name and its count. Click one to filter: the "
        "binder, the Corkboard and the Outline then show only its scenes, "
        f"under a banner //Only “//name//” · //n// with **Show all** "
        f"({R('fig_gfilter')}). Click it again to clear the filter. The "
        "filter is not saved with the project.")
    s.gfigure("fig_gfilter", "g_collection_filter", "The corkboard "
              "filtered by a collection, with its banner", width=330)
    s.p("**Edit**, beside the **Collections** label, opens the manager "
        f"({R('fig_gcoll')}). Click a name to rename it (`enter` saves, "
        "`esc` cancels); click a swatch to recolor it at once; use the "
        "trash button to delete it; or type a name in the last row, pick "
        "a swatch and press **Add**.")
    s.gfigure("fig_gcoll", "g_collections_manager", "The Collections "
              "manager", width=300)
    s.p("To put the open scene in collections, click the **Collections** "
        "cell of the details strip, or choose **Collections…** from the "
        f"**…** menu. A list of check boxes ({R('fig_gscene')}) appears; "
        "tick the ones you want and press **Save**. **Edit "
        "collections…** in the same dialog opens the manager.")
    s.gfigure("fig_gscene", "g_scene_collections", "The Collections "
              "dialog for one scene", width=260)
    s.attention("Renaming or deleting a collection rewrites every scene "
                "file that belongs to it. Lorewrite saves the open scene "
                "first. Deleting a collection removes the label from its "
                "scenes; it never deletes a scene.")

    # ------------------------------------------------------------------
    s.h2("Word Counts: What Counts as the Book", idx=["word count",
                                                      "book words"])
    s.p("Lorewrite is careful about what it calls your words. The "
        "//book// is every scene that is neither front matter nor "
        "unplaced. The totals follow that rule, and the single-scene "
        "counts follow the second column.")
    s.table("t_counts", "What each count includes",
            ["Count", "Includes", "Leaves out"], [
        ["Terminal status bar, //N words (M project)//",
         "N is the open file; M is the book.",
         "Front matter and Unplaced Scenes from M; pending AI drafts and "
         "the details block from both."],
        ["Desktop status bar //N project words// and binder total",
         "The book.", "Front matter, Unplaced Scenes, pending AI "
         "drafts, details."],
        ["Part rows in the binder", "The words in each part. The front "
         "matter part shows its own muted count.", "The front matter "
         "count is not added to the total."],
        ["A scene's chip, card or outline row", "The scene's own words, "
         "even for front matter and unplaced scenes.",
         "Pending AI drafts and the details block."],
        ["Style learning, voice samples, statistics", "The book.",
         "Front matter and Unplaced Scenes."],
    ], [0.30, 0.34, 0.36])
    s.p("Text that an AI proposed and you have not yet accepted "
        "(Chapter 11) is never counted, because it is not yet part of "
        "your book. Comments (Chapter 9) are not counted either; they are "
        "not in the text.")

    # ------------------------------------------------------------------
    s.h2("Quirks and Limits", idx=["quirks", "numbering|gaps"])
    s.bullets([
        "**Folders keep their names.** Renaming a part changes only its "
        "title, and renaming a scene changes only its heading. File and "
        "folder names, and so the reading order, change only through "
        "moves.",
        "**Gaps in the numbers.** Moving a scene into a part renumbers "
        "the part it enters, in order. The part it left keeps its "
        "numbers, leaving a gap (`02-b.md` alone). This does no harm: "
        "once there are parts, the numbers you see are positions, not "
        "file prefixes. **Move up** and **Move down** need a numeric "
        "prefix on both files and report the edge for a file without "
        "one.",
        "**Where a new scene goes.** A new scene goes into the part of "
        "the scene you have open (or loose, if that one is loose). If "
        "a note or an unplaced scene is open, it goes to the last part "
        "that is not front matter, or to the top level if there is none.",
        "**Loose scenes always read first,** before every part, "
        "regardless of their numbers.",
        "**One level of folders.** A folder inside a part is ignored.",
        "**The terminal part commands ask which part,** with the open "
        "scene's part preselected, so you can rename, move or delete any "
        "part whatever is open.",
        "**The Trash and `_unplaced` are not hidden from version "
        "control.** Only `.lorewrite/` (the index cache) is ignored by the "
        "project's own ignore list, so a version-control sync includes "
        "the Trash, the unplaced scenes and the draft sidecars.",
        "**Shared editing.** If the terminal and desktop applications "
        "are open on the same project and a file changes under the "
        "desktop editor, a banner offers **Reload from disk** or **Keep "
        "my version**. Edits you make in a file manager are picked up "
        "the next time you open the project; **Rebuild the link index** "
        "(`f9` in the terminal) refreshes the cache.",
        "**Unplaced scenes and the AI.** The continuity check, like "
        "every AI feature, looks only at the scene you have open, so it "
        "runs on an unplaced scene if you open one. Unplaced scenes are "
        "simply not part of the book's order or word totals.",
    ])

    # ------------------------------------------------------------------


GLOSSARY = [
    ("part", "A folder inside manuscript that groups scenes, with its "
     "title kept in _part.md. Parts read in the order of their folder "
     "prefixes."),
    ("front matter", "The part whose folder name is front-matter: title "
     "page, dedication and the like. Not numbered and not counted in the "
     "book."),
    ("loose scene", "A scene directly in the manuscript folder, outside "
     "any part. Loose scenes read before all parts."),
    ("book", "The scenes that count: every scene that is not front "
     "matter and not unplaced."),
    ("Unplaced Scenes", "Scenes kept in the _unplaced folder: still "
     "editable and indexed, but not in the book's order or counts."),
    ("Trash", "The .trash folder, where deleted scenes and research "
     "notes wait to be restored or deleted forever."),
    ("scene details", "Status, POV, place, purpose and word target of a "
     "scene, stored as frontmatter and not counted as prose."),
    ("frontmatter", "A short block of keys between two --- lines at the "
     "top of a file. Lorewrite uses it for scene details and "
     "collections."),
    ("collection", "A colored label you create and put on any number of "
     "scenes. Members are recorded in each scene's frontmatter."),
    ("corkboard", "A desktop view of the whole book as cards, which can "
     "be dragged to reorder scenes."),
    ("outline", "A desktop view of the whole book as rows with the "
     "headings of each scene, which can be dragged to reorder."),
    ("unit", "The word, scene or chapter, that Lorewrite uses for the "
     "book's units. A label only."),
]

MSG_TUI = {
    "info": [
        ["Created part '//title//'", "A new part was made."],
        ["Moved part '//title//'", "Move part up or down worked."],
        ["Moved (at the end of the part)", "Move scene to part worked."],
        ["Moved to //file name//", "Move current scene up or down worked."],
        ["Moved to Unplaced scenes (not counted in the book)",
         "The scene was taken out of the book."],
        ["Placed in the book", "An unplaced scene went into a part."],
        ["Moved '//title//' to the Trash", "A scene was deleted to the "
         "Trash."],
        ["Restored to //path//", "A scene was restored from the Trash."],
        ["Restored the research note to research/ //file//",
         "A research note was restored."],
        ["Emptied the Trash (//n//)", "The Trash was emptied."],
        ["Deleted part '//title//'", "An empty part was removed."],
        ["Labels now say 'chapter'", "The unit label was toggled (or "
         "'scene')."],
        ["Details saved", "The Scene details window was saved."],
    ],
    "warn": [
        ["Already at the edge", "The part cannot move further, or has "
         "no numeric prefix."],
        ["Already at the edge of its part", "The scene is first or last "
         "in its folder, or its file has no number."],
        ["'//title//' still has scenes - move them out first",
         "Delete empty part refused."],
        ["Already unplaced - use Action · Place scene in the book",
         "The open scene is already in Unplaced."],
        ["Open an unplaced scene first", "Place scene in the book needs "
         "an unplaced scene open."],
        ["Open a scene first", "A scene command was used with no scene "
         "open."],
        ["No more scenes this way", "The first or last scene of the "
         "book was reached."],
        ["Target must be a number of words", "The target field of the "
         "details window was not a number."],
        ["Open a scene to tick its collections", "The Collections "
         "window was used with no scene open."],
    ],
    "err": [
        ["a part needs a title", "New part or Rename part got an empty "
         "title."],
        ["the part folder still holds other files", "A part has a "
         "stray file besides its scenes."],
        ["not in the trash: //name//", "The item is no longer in the "
         "Trash."],
        ["a collection needs a name", "An empty collection name."],
        ["a collection name is at most 60 characters", "The name is "
         "too long."],
        ["a collection named “//name//” already exists", "The name is "
         "taken (case is ignored)."],
        ["colour must be one of: violet, amber, green, red, gray",
         "Only these five colors exist."],
    ],
}

MSG_GUI = [
    ["Moved.", "A scene went to another part."],
    ["Moved “//title//”.  [Undo]", "A drag was confirmed; Undo is "
     "available for about nine seconds."],
    ["Moved back.", "Undo moved the scene back."],
    ["Moved to Unplaced Scenes. It no longer counts in the book.",
     "The scene was unplaced."],
    ["Placed in the book.", "An unplaced scene went into a part."],
    ["Moved “//title//” to the Trash.", "A scene was deleted to the "
     "Trash."],
    ["Restored “//title//”.", "A scene was restored."],
    ["Restored “//title//” to //part//.", "A scene returned to its part."],
    ["Restored “//title//” to Unplaced Scenes.", "A scene that was "
     "unplaced went back to Unplaced Scenes."],
    ["Restored “//title//”: its part is gone, so it went to Unplaced "
     "Scenes.", "The scene's part no longer exists."],
    ["Emptied the Trash (//n//).", "Everything in the Trash is gone."],
    ["Labels now say “chapter”. Only the wording changes.",
     "The unit label was toggled."],
    ["the part is already at the edge", "Move part up or down at the "
     "first or last part."],
    ["the scene is already at the edge of its part", "Move up or down "
     "at the end of a part."],
    ["the part still has scenes - move them out first", "Delete empty "
     "part refused."],
    ["a scene needs a title", "An empty title for a new scene."],
    ["Could not save the current document first.", "A move or "
     "collection change was cancelled because the open scene could not "
     "be saved."],
    ["A number of words, like 2400.", "The target in Scene details is "
     "not a number."],
    ["The text changed while saving the details; try again.",
     "You typed while the details were being saved."],
    ["Only “//name//” · //n//", "The banner while a collection filter "
     "is on (**Show all** clears it)."],
]

PALETTE = [
    ["New part", "Add a part (a folder under manuscript/).", ""],
    ["Rename part", "Retitle a part (asks which, the open scene's part "
     "first).", ""],
    ["Move part up", "Swap the part with the one before it.", ""],
    ["Move part down", "Swap the part with the one after it.", ""],
    ["Delete empty part", "Remove a part that has no scenes.", ""],
    ["Move scene to part", "Send the open scene to the end of another "
     "part.", ""],
    ["Move current scene up", "Swap with the scene above, in its part.",
     ""],
    ["Move current scene down", "Swap with the scene below, in its part.",
     ""],
    ["Move scene to Unplaced", "Take the open scene out of the book "
     "(kept, not counted).", ""],
    ["Place scene in the book", "Bring an unplaced scene back into a "
     "part.", ""],
    ["Delete current scene", "Move the open scene to the Trash.", ""],
    ["Open Trash", "Restore deleted scenes and research notes, delete "
     "them forever, or empty the Trash.", ""],
    ["Call them chapters (or Call them scenes)", "Switch the "
     "manuscript's wording between scenes and chapters (labels only).",
     ""],
    ["Edit details", "POV, place, purpose, status and word target "
     "(category Scene).", ""],
    ["Collections", "Tick the open scene's collections; add, rename, "
     "recolor or delete them (category Scene).", ""],
    ["Next / previous scene", "Walk the book in order, skipping "
     "Unplaced scenes.", "alt+right / alt+left"],
]

PROBLEMS = [
    ["I cannot find a way to make front matter.",
     "There is no button. Make a part titled Front matter and move it "
     "first, or name its folder 00-front-matter."],
    ["Delete empty part says the part still has scenes, or targets the "
     "wrong part (terminal).",
     "Choose the right part in the picker (the open scene's part is "
     "preselected). A part with scenes cannot be deleted: move them out "
     "first."],
    ["The scene numbers have gaps, or restored scenes have new numbers.",
     "Harmless. Only the destination of a move is renumbered, and a "
     "restored scene takes the next free number in its folder."],
    ["A deleted scene is gone from the book and I want it back.",
     "Open the Trash (Action · Open Trash, or the binder's Trash row) and "
     "restore it."],
    ["Words I wrote are not in the book total.",
     "Front matter and Unplaced Scenes are not counted, nor are details "
     "or AI text you have not accepted."],
    ["I moved a scene by dragging and want it back.",
     "Press Undo in the toast within nine seconds, or move it again."],
]
