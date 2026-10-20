"""Chapter 20: Writing a Research Paper."""


def build(s, R):
    s.chapter("20", "Writing a Research Paper",
              "Creating a research project, bringing your sources in from "
              "Zotero, citing them, and checking the paper against the "
              "journal's rules.")
    s.p("Chisel is also used for research papers and proposals. A "
        "research project is still a folder of plain Markdown files "
        "(Chapter 1), but the binder speaks the language of a paper: what "
        "other chapters call a scene is a //section// here, the notes "
        "under **Sources** are the papers you cite, and the notes under "
        "**Concepts and methods** hold the ideas and methods you want to "
        "keep straight. Scene details for point of view, place and story "
        "time are not shown in a research project.",
        idx=["research project", "research mode"])
    s.p("The research features described in this chapter are in the "
        "desktop application: creating "
        "the project with its product type, the Zotero connection, the "
        "source notes, citations, the journal requirements and the "
        "guidelines. The terminal application can create a Research "
        "project and edit the same files, but the menus and dialogs this "
        "chapter describes belong to the desktop window.")
    s.h2("Creating a Research Project", idx=["research project|creating",
                                             "More menu"])
    s.proc("To start a paper in the desktop application:", [
        "On the launch screen, type the **Title** of the paper and press "
        "**Research** under the project type.",
        "Under **What are you writing?**, choose **Manuscript** or "
        "**Proposal**.",
        "Choose the **Target journal** for a manuscript, or the "
        "**Proposal guide** for a proposal. **No target journal "
        "(standard structure)** starts from the standard layout for the "
        "type. The list holds the journals Chisel has a profile for; the "
        "first one is selected for a manuscript.",
        "Press **Create**.",
    ])
    s.p("The product type and the journal can be changed later: open "
        "**More › Project settings…**. The project's menu is the "
        "**More** button (the three dots) in the title bar at the top of "
        "the desktop window. Changing the product type or the journal "
        "never moves or deletes your sections. In the terminal "
        "application, the new-project prompt offers **Research** but not "
        "the product type or a journal; choose those in **Project "
        "settings** in the desktop application afterwards.",
        idx=["Project settings"])

    s.h2("The Starter Outline", idx=["starter outline", "outline|starter"])
    s.p("Starting from a journal profile creates that profile's outline "
        "as ordinary, editable sections in parts. A manuscript starts "
        "with the front matter the profile asks for (for example a Title "
        "page, Highlights, an Abstract and Keywords), the article "
        "sections (Introduction, Methods, Results, Discussion, "
        "Conclusions), and the declarations and availability statements "
        "the profile asks for (for example Funding, a data availability "
        "statement and an acknowledgement). A proposal starts with a "
        "Project summary, Background and significance, Objectives, "
        "Approach and methods, Timeline and deliverables, Team and "
        "resources, Broader impacts and Budget justification. Each "
        "section's details carry a one-line reminder of what belongs in "
        "it (Chapter 5).")
    s.p("The sections are empty: the outline is a place to start, not a "
        "template you must keep. Rename, reorder, add and delete them as "
        "you would any section (Chapters 4 and 5). With **No target "
        "journal**, Chisel uses the standard layout for the product type.")
    s.p("The short note that a new project normally opens with is parked "
        "for a research project: it sits in **Parked sections**, so it "
        "neither counts towards your words nor goes into an export.")

    s.h2("Connecting Zotero", idx=["Zotero|connecting", "Zotero",
                                   "Zotero settings"])
    s.p("Chisel reads your Zotero library; it never changes anything in "
        "Zotero. There are two ways to connect it, and a third for "
        "working offline.")
    s.proc("To connect Zotero:", [
        "Choose **More › Zotero settings…**.",
        "For **Zotero on this computer**, leave **Read my library from "
        "Zotero on this computer** ticked and keep Zotero open. In "
        "Zotero 10, open **Settings**, then **Advanced**, and turn on "
        "“Allow other applications on this computer to communicate with "
        "Zotero”.",
        "Or use **Zotero on the web**: paste a Zotero web API key and "
        "press **Save key**. A read-only key is enough. The key is kept "
        "in your system keyring, not in the project and not in a Chisel "
        "settings file; it is never shown again, and the dialog says only "
        "that a key is saved. The key identifies your account, so the Web "
        "user id can stay blank.",
        "Optionally, give a Better BibTeX export file (a `.bib` or "
        "`.json` file) for when Zotero is not running.",
        "Press **Check connection** to see each connection it tried, "
        "with //working// or //not working// and the reason. It saves the "
        "form first.",
    ])
    s.note("The local connection needs Zotero open. If a connection cannot "
           "answer, Chisel tries the others; **Check connection** and the "
           "preview's report say which one was used.")
    s.p("Press **Save** to keep the settings. It is safe to leave the "
        "address boxes empty unless your Zotero uses another address.")

    s.h2("Syncing Sources", idx=["sources|syncing", "sync",
                                 "Zotero|sync"])
    s.p("A sync copies the Zotero items you choose into source notes in "
        "your project. It only reads from Zotero and never writes to it. "
        "You always see the changes first, and only the rows you tick are "
        "written.")
    s.proc("To bring sources in:", [
        "Choose **More › Sync sources from Zotero…**.",
        "Tick the collections to read: their names are shown, nested "
        "collections indented, with a filter box, **Select all shown** "
        "and **Clear**. With no collection ticked, Chisel reads the whole "
        "library. **Include subcollections** is ticked by default.",
        "Press **Preview changes**. After a successful sync from the same "
        "collections the button reads **Sync again**. The first read can "
        "take a minute; a spinner and a sentence say what is happening, "
        "and an elapsed count appears after five seconds. **Cancel "
        "preview** abandons the request, and nothing has been written.",
        "Read the preview. Each paper is a row marked **New**, "
        "**Changed**, **Missing in Zotero** or **Key mismatch**, with a "
        "sentence saying what changed. A row that cannot be applied says "
        "why after **Not applied:**. Search the papers, and use **Select "
        "all** and **Select none**; the count reads, for example, //7 of "
        "12 selected//. Nothing is written yet.",
        "Press **Apply** (it names the number of changes). Only the "
        "ticked rows are applied. The last line reports how many changed "
        "and how many were skipped, with a reason for each skip.",
    ])
    s.p("The collections you ticked are remembered for this project, so "
        "the next time the dialog opens they are already selected. Papers "
        "added to them later arrive as **New** rows the next time you "
        "sync. A paper that leaves a collection is not removed or marked "
        "missing. A paper that is no longer in Zotero at all keeps its "
        "note, which is marked missing; if it comes back, the next sync "
        "says so.")
    s.p("A **Key mismatch** means the citation key in Zotero differs from "
        "the one stored in your note. Chisel reports it and changes "
        "nothing: give the item in Zotero the key the note uses, then "
        "sync again. If a note or a file changed after the preview, Apply "
        "stops before writing anything and asks you to preview again.")
    s.note("Only the rows you tick are ever written: a paper you untick is "
           "left as it is. A preview that is out of date cannot be applied "
           "at all; make it again.")

    s.h2("The Sources Group and Source Notes",
         idx=["Sources group", "source note", "source"]
         )
    s.p("Each synced paper becomes one //source note//, a note of type "
        "source kept in `entities/sources/` and listed under **Sources** "
        "in the binder. Open one and you find a readable block made by "
        "the sync:")
    s.bullets([
        "**The title and authors**, then the journal or publisher, the "
        "year, and the DOI and URL as links.",
        "**Abstract**, when Zotero has one.",
        "**Notes**, the notes you wrote on the item in Zotero.",
        "**Highlights**, your annotations, with their page numbers.",
    ])
    s.p("Below that block is **My notes**, which is yours. A sync "
        "regenerates only the block above it: everything you write under "
        "**My notes** is never overwritten. The editor hides the note's "
        "frontmatter and the opening sync marker, and shows the other "
        "markers dimmed; a banner over the block says that the part above "
        "is replaced by a sync and that your own notes go under **My "
        "notes**. The hidden frontmatter and opening marker cannot be "
        "edited; the dimmed markers can. A source note synced before this "
        "readable layout was introduced is reformatted on its next sync, "
        "and the preview marks that row //reformatted//.")
    s.p("At the top of the **Notes** panel for an open source note, the "
        "**Source** card shows the citation text to copy "
        "(`[[@key]]`) with a **Copy** button, the DOI and a link, **Open "
        "in Zotero**, the Zotero collections it is in, and how many notes "
        "and highlights it has. If the collections cannot be "
        "read, the card asks whether Zotero is running.")

    s.h2("Citing a Paper", idx=["citation", "citing a source",
                                "Cite a source"])
    s.h3("While you type")
    s.p("In a section, type two opening square brackets, an at sign and "
        "the start of an author, year, title or key: `[[@`. A list of "
        "your synced sources appears. Keep typing to narrow it, choose "
        "with the arrow keys and press `enter`; Chisel inserts the key "
        "and the closing brackets. Typing `[[+@` offers the same list "
        "for a narrative citation (see below).",
        idx=["citation|inserting", "[[@", "citation|completion"])
    s.h3("With the Cite command")
    s.p("**More › Cite a source…**, or `ctrl+shift+l` in the "
        "editor, opens a small window. Search by author, year, title or "
        "key, type an optional **Page**, choose with the arrow keys and "
        "press `enter` or **Insert**. The citation goes at the cursor, "
        "replacing a selection. The line under the list shows exactly "
        "what will be inserted. If the project has no sources yet, the "
        "window offers **Sync sources from Zotero…** instead.",
        idx=["Cite a source"])
    s.h3("The forms a citation can take")
    s.table(None, None, ["What you type", "What it means"], [
        ["`[[@wang2026]]`", "A parenthetical citation."],
        ["`[[+@wang2026]]`", "A narrative citation: the author is part of "
         "the sentence and the year is in parentheses."],
        ["`[[@wang2026, p. 12]]`", "A citation with a page or other "
         "locator. The Cite window writes `p.` before a bare number; "
         "`ch. 3` and `pp. 4-5` are kept as written."],
        ["`[[@wang2026; @zhang2026]]`", "Several sources in one "
         "parenthetical citation, separated by semicolons. Each may have "
         "its own page."],
    ], [0.38, 0.62], mono_cols=(0,))
    s.p("You can also put words before a key, as in `[[see @wang2026]]`, "
        "and hide the author with a minus, as in `[[-@wang2026]]` (the "
        "year alone is shown). A citation in the plain pandoc form, "
        "`[@wang2026]`, is recognized as well. Keys are case-sensitive.")
    s.h3("How it looks in the text")
    s.p("The editor shows the formatted citation in place of the raw "
        "text, in an approximation of APA: one author as //(Wang, 2026)//, "
        "two as //(Wang & Valeo, 2026)//, three or more as //(Wang et "
        "al., 2026)//, no year as //(Wang, n.d.)//, and the letters //a// "
        "and //b// when two sources share the author and year. The "
        "Environmental Modelling & Software profile writes a plain "
        "**and** instead of **&**. Put the cursor in a citation, or click "
        "it, to see and edit the raw `[[@key]]` again; the hover card "
        "shows the paper's title and says that the form is approximate.")
    s.p("If no source note has the key, the citation is //unresolved//: "
        "the key itself is shown in the missing style, and the hover card "
        "says there is no source with that key. Sync from Zotero or check "
        "the spelling of the key. When a journal is selected, the journal "
        "requirements (below) also "
        "report every citation that does not match a source.",
        idx=["citation|unresolved"])

    s.h2("Journal Requirements", idx=["journal requirements",
                                      "requirements"])
    s.p("**More › Journal requirements…** checks your paper "
        "against the target journal's rules. The rules are Chisel's own "
        "short restatement of the journal's Guide for Authors; the dialog "
        "names the journal and the date the guide was read, and says to "
        "check the live guide before you submit. Press "
        "**Check again** after making changes.")
    s.table(None, None, ["Status", "What it means"], [
        ["**Ok**", "The check found what the rule asks for. A section "
         "that exists but is empty never counts as ok."],
        ["**Needs attention**", "The check did not find what the rule "
         "asks for: too many words, a missing section, a citation that "
         "does not resolve, a figure or table without a caption."],
        ["**Note**", "A check of low importance did not pass. It is "
         "reported, but it is not counted as needing attention."],
        ["**Not applicable**", "There is nothing to check yet for this "
         "item."],
        ["**Reminder**", "Advice Chisel cannot check for you, such as a "
         "file format, the numbering scheme or a graphical abstract."],
    ], [0.24, 0.76])
    s.p("The summary line reads, for example, //12 ok, 3 need attention, "
        "14 reminders//; notes and items that do not apply are not counted "
        "there. Items are grouped by topic (front matter, structure, "
        "figures and tables, references, and what the "
        "journal looks for). The checks cover things such as the abstract "
        "length, the number and length of keywords and highlights, "
        "required sections, captions and in-text citations for figures "
        "and tables, citations that resolve, DOIs, and the declaration of "
        "AI use when you have accepted AI-written words. Nothing in the "
        "list blocks export.")
    s.p("A project with **No target journal** has no requirements to "
        "check; the window says to choose a journal in **Project "
        "settings** first. Changing the journal changes the list and "
        "never moves or deletes a section.")

    s.h2("Guidelines", idx=["guidelines", "journal guidelines",
                            "call for proposals"])
    s.p("**More › Guidelines…** keeps the documents you write "
        "against: the journal's Guide for Authors, a funder's call for "
        "proposals, or your own notes on them. Press **Add files** to "
        "choose `.pdf`, `.docx`, `.md` or `.txt` files, or **Paste "
        "text** and give the text a title. The files are copied into the "
        "project's `guidelines/` folder, so they travel with the paper.")
    s.p("The list shows each file's type and size and says whether its "
        "text was read. **View text** shows the extracted text (the first "
        "part only, when the document is long). Reading the text of a "
        "PDF needs the optional `pypdf` package; without it, or for a "
        "password-protected or scanned PDF, Chisel says no text was read "
        "and asks you to paste the text instead. **Remove** asks first "
        "and states that your paper is not changed.")
    s.p("Guidelines stay on your computer, in the project. No feature of "
        "this version sends them to an AI.")

    s.p("More is planned for research projects: an assistant that "
        "proposes an outline, screens for placing and editing figures, "
        "tables and equations, and export screens that prepare the paper "
        "for submission. They are not in this version.")


GLOSSARY = [
    ("citation", "A reference to a source, written as `[[@key]]` (or one "
     "of its other forms) and shown as a formatted author-year citation "
     "in the editor. A citation whose key has no source note is "
     "unresolved."),
    ("journal requirements", "The target journal's rules, restated by "
     "Chisel and checked against the paper, with the statuses ok, needs "
     "attention, note, not applicable and reminder."),
    ("source note", "The note for one Zotero item, listed under Sources. "
     "A sync rewrites its From Zotero block and never touches My notes."),
    ("guidelines", "A journal's guide or a funder's call, kept in the "
     "project's `guidelines/` folder for you to read; no current feature "
     "sends it to an AI."),
    ("Zotero", "The reference manager Chisel reads sources from. Chisel "
     "reads the library and never changes it."),
]

MSG_TUI = {"info": [], "warn": [], "err": []}

MSG_GUI = [
    ["Zotero key stored in the system keyring.",
     "The web key is saved and will not be shown again."],
    ["There are no sources in this project yet. Sync from Zotero first: "
     "it brings your library in as sources you can cite.",
     "The Cite window has nothing to search. Choose **Sync sources from "
     "Zotero…**, then cite again."],
    ["This project has no journal selected. Choose one in Project "
     "settings.",
     "Journal requirements need a target journal. Set one in "
     "**More › Project settings…**."],
]

PROBLEMS = [
    ["A citation shows its key instead of an author and year.",
     "No source note has that key. Sync from Zotero, or correct the key "
     "(they are case-sensitive), then reopen the section."],
    ["Zotero settings says a connection is not working.",
     "Keep Zotero open and allow other applications to communicate with "
     "it (Settings, then Advanced), or save a web API key (Chapter 20)."],
    ["A guideline PDF says no text was read.",
     "Reading PDFs needs the optional `pypdf` package, and a scanned or "
     "protected PDF has no text to read. Paste the text instead "
     "(Chapter 20)."],
    ["A sync row says key mismatch.",
     "The citation key in Zotero differs from the one in the note. "
     "Chisel does not change either; make them agree in Zotero, then "
     "sync again."],
]

PALETTE = []
