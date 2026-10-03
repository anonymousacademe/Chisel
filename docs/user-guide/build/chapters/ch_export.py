"""Chapter 14: Exporting Your Book (PDF, DOCX, EPUB, Markdown, LaTeX source)."""


def build(s, R):
    s.chapter("14", "Exporting Your Book",
              "Turn the manuscript into a file you can print, send to a "
              "reader, or hand to an editor, without changing a word of it.")
    s.p("Your scenes are plain Markdown files, which is ideal for writing "
        "and poor for handing to anyone else. //Export// gathers the scenes "
        "in book order and writes them as one file: a typeset PDF, a Word "
        "document, an EPUB for e-readers, a single Markdown file, or LaTeX "
        "source. Both applications can do it. Export is //read-only//: it "
        "never edits a scene, never touches the index, and uses no AI. If "
        "an export looks wrong, nothing in your project is wrong. Change "
        "an option and export again.",
        idx=["export", "exporting the book", "manuscript|exporting"])
    s.p("Every export is saved in the `exports` folder of the project and "
        "is never written over an earlier one. Nothing is opened, "
        "uploaded or sent anywhere unless you click a button that says "
        "so.")

    # ------------------------------------------------------------------
    s.h2("Formats", idx=["export|formats", "formats, export"])
    s.p(f"There are five formats ({R('x_formats')}). The three PDF "
        "//layouts// are three looks for the same book; they are listed "
        "as one format, //PDF//, with a choice of layout.")
    s.table("x_formats", "Export formats",
            ["Format", "File", "What it is for", "Needs"], [
        ["PDF, layout //Book//", "`.pdf`", "A typeset trade paperback: "
         "title page, contents, chapters on new pages, running heads, "
         "page numbers. For reading, printing or proofing as a book.",
         "ReportLab"],
        ["PDF, layout //Manuscript review//", "`.pdf`", "Double-spaced, "
         "US Letter, with line numbers on every page. For printing and "
         "marking with a red pen, or for sending to a reader.",
         "ReportLab"],
        ["PDF, layout //Plain proof//", "`.pdf`", "Sans serif, 1.5 "
         "spacing, simple. A plain copy for proofreading on screen or "
         "paper.", "ReportLab"],
        ["Word (DOCX)", "`.docx`", "A Word document, for editors and "
         "agents who want one.", "pandoc"],
        ["EPUB", "`.epub`", "An e-book for e-readers and reading apps.",
         "pandoc"],
        ["Markdown", "`.md`", "The whole book as one Markdown file, "
         "cleaned up as described below.", "nothing extra"],
        ["LaTeX source", "`.tex`", "A standalone LaTeX file, for authors "
         "who typeset with TeX elsewhere. Chisel does not run LaTeX "
         "itself.", "pandoc"],
    ], [0.22, 0.09, 0.51, 0.18])
    s.h3("What the Program Needs", idx=["pandoc", "ReportLab", "export|requirements"])
    s.p("Markdown needs nothing. The PDF layouts are drawn by a Python "
        "library called ReportLab, which is an optional part of the "
        "install: `pip install 'lorewrite[export]'` (it also brings the "
        "hyphenation helper that lets the Book layout break long words "
        "at line ends). DOCX, EPUB and LaTeX are written by a separate "
        "program, **pandoc**, which must be installed on your computer "
        "and findable on its path. Chisel never downloads either.")
    s.p("When a tool is missing the format is still listed, but marked. "
        "In the terminal form the entry reads //PDF (install ReportLab: "
        "pip install 'lorewrite[export]')// or //Word (DOCX) (install "
        "pandoc)//. In the desktop dialog the format button is dimmed, "
        "and a line below the buttons gives the same reason. A missing "
        "format cannot be exported; choosing it in the terminal and "
        "pressing `ctrl+s` shows the reason as a warning instead. If "
        "the form opens with a remembered format that is no longer "
        "possible, it starts on the first one that is.")
    s.note("The PDF fonts are **Noto Serif**, **Liberation Serif**, "
           "**Liberation Sans** and **Liberation Mono**. They are looked "
           "for in the system font folders (`/usr/share/fonts`, "
           "`/usr/local/share/fonts`) and in `~/.local/share/fonts` and "
           "`~/.fonts`, and are embedded in the PDF so it looks the same "
           "on any computer. If a font you chose is missing, Chisel "
           "falls back to the layout's next font and tells you (see "
           "Messages below); if none of them is installed the export "
           "stops.")

    # ------------------------------------------------------------------
    s.h2("What Is in the Book", idx=["export|what is included", "included in export"])
    s.p("Export builds the book from the same place as the word count in "
        "the manuscript: the scenes you have //placed//, in the order "
        "the binder shows them (Chapter 5). Scenes directly in the "
        "manuscript come first, then each part in order, with its scenes. "
        "Chapters are numbered straight through the book; numbering does "
        "not restart in a new part.")
    s.table("x_included", "What export includes and leaves out",
            ["Item", "In the export?"], [
        ["Placed scenes (the text of each, in order)", "Yes."],
        ["Part names", "Yes: a part title page in the PDFs and a "
         "top-level heading elsewhere, with a label such as //Part I// "
         "unless the headings are //Titles only//."],
        ["The `front-matter` part", "Yes, first, if //Include front "
         "matter// is on. It has no numbers, no part page, and is not "
         "listed in the contents (Chapter 5)."],
        ["Parked scenes", "No."],
        ["The Trash", "No."],
        ["Research notes", "No."],
        ["Character and place notes", "No."],
        ["Comments, in any form", "No. Comment markers and any other "
         "`<!-- ... -->` comments in a scene are dropped."],
        ["Scene details (the block at the top of a scene)", "No."],
        ["The style guide and the dictionary", "No."],
        ["Pending AI drafts (Chapter 11)", "Left out by default: the "
         "text from before the draft is used. A switch includes them "
         "as written."],
        ["`{{expand: ...}}` markers", "Removed, with a warning."],
    ], [0.45, 0.55])
    s.h3("How Text Is Turned into Pages", idx=["export|text changes", "links, export"])
    s.bullets([
        "The scene's first `# heading` line becomes its title and is "
        "taken out of the text. A scene with no such line gets a title "
        "made from its file name (`ghost-frequency.md` becomes //Ghost "
        "Frequency//).",
        "`[[links]]` become their display text: `[[Mara Voss]]` prints "
        "as //Mara Voss//, and `[[Mara Voss|Mara]]` prints as //Mara//. "
        "The brackets never reach the book.",
        "//Italic//, **bold** and bold-italic text are kept. Other "
        "Markdown decoration is dropped: backticks vanish and the text "
        "stays plain, and the `>` at the start of a line is removed.",
        "A sub-heading inside a scene (a `##` line) becomes a bold "
        "paragraph.",
        "Lines you hard-wrapped are joined into one paragraph; a blank "
        "line separates paragraphs.",
        "A line of `***`, `---`, `___` or `* * *` on its own is a "
        "//scene break//. It prints as an ornament: three asterisks in "
        "the Book layout, `#` in the Manuscript review layout (the "
        "traditional manuscript mark), `* * *` in the Plain proof layout "
        "and in Markdown. Repeated breaks collapse into one, and a break "
        "at the very start or end of a scene is dropped.",
        "Only the Book layout changes straight quotes, `--` and `...` "
        "into curly quotes, dashes and ellipses. Your files are not "
        "changed.",
    ])
    s.h3("Pending AI Drafts", idx=["export|pending AI drafts", "drafts, pending|export"])
    s.p("Text an AI wrote that you have not accepted is not part of the "
        "book (Chapter 11). Export keeps to that rule. A scene with a "
        "pending draft is exported as it was //before// the draft: a "
        "draft that replaced your text puts your original text back, "
        "and a draft that only added text disappears. The switch //Include "
        "pending AI drafts// reverses this and prints the AI text as "
        "written. The file on disk is never changed either way.")
    s.attention("If the original text a draft replaced is missing "
                "(the saved copy in the project's `.drafts` folder is "
                "gone), export cannot restore it. That draft is left out "
                "and a warning names the scene. Open the scene and "
                "accept or reject the draft before you rely on the "
                "export.")

    # ------------------------------------------------------------------
    s.h2("Options", idx=["export|options", "options, export"])
    s.p(f"The options are the same in both applications ({R('x_options')}). "
        "Most apply only to some formats; a control that does not apply "
        "is dimmed or hidden. In the headings control, the word is "
        "//Scene// or //Chapter// to match the unit your project uses.")
    s.table("x_options", "Export options",
            ["Option", "Choices", "Applies to", "Notes"], [
        ["Format", "PDF, Word (DOCX), EPUB, Markdown, LaTeX source",
         "all", "Unavailable formats are marked."],
        ["Layout", "Book, Manuscript review, Plain proof", "PDF",
         "See the layouts below."],
        ["Page size", "Trade 6 x 9 in, A5, US Letter, A4", "PDF",
         "Each layout offers only some sizes."],
        ["Font", "Noto Serif, Liberation Serif, Liberation Sans, "
         "Liberation Mono", "PDF", "Each layout offers only some fonts."],
        ["Scene or Chapter headings", "“Scene 3” (or “Chapter 3”); "
         "Numbers; Titles only", "all",
         "How each heading is labeled. Titles only drops the number "
         "and the //Part I// label."],
        ["Table of contents", "on / off (on by default)",
         "Book layout, DOCX, EPUB, LaTeX", "Not offered for the "
         "Manuscript review and Plain proof layouts."],
        ["Include front matter", "on / off (on by default)", "all",
         "The `front-matter` part."],
        ["Run scenes on with a break ornament", "on / off (off by "
         "default)", "all", "See below."],
        ["Include pending AI drafts", "on / off (off by default)", "all",
         "See above."],
        ["Copyright line (PDF) / Copyright or edition line (optional)",
         "any text, such as //First edition, 2026//", "PDF", "Printed "
         "on the title page area. Left empty, nothing is printed."],
    ], [0.24, 0.30, 0.17, 0.29])
    s.h3("Page Size and Font", idx=["page size", "font, export"])
    s.p("A layout only offers what suits it, and what you pick is kept "
        "when you change layout if the new layout offers it; otherwise "
        "Chisel uses that layout's first choice. The Book layout "
        "offers Trade 6 x 9 in (the default), A5 and US Letter, in Noto "
        "Serif (the default) or Liberation Serif. Manuscript review is "
        "US Letter only, in Liberation Serif (the default) or Liberation "
        "Mono. Plain proof offers A4 (the default) and US Letter, in "
        "Liberation Sans. The desktop dialog shows the page-size and "
        "font buttons only when there is a real choice; the terminal "
        "form shows the page size but has no font control. The terminal "
        "keeps whatever font the project last remembered, and "
        "otherwise the layout's default.")
    s.h3("Headings and Numbering", idx=["numbering, chapter", "headings, export"])
    s.p("Each placed scene is a //chapter// of the book, headed by its "
        "title. //“Scene 3”// (or //“Chapter 3”//, if your project calls "
        "its scenes chapters) puts that label above the title; "
        "//Numbers// puts just //3//; //Titles only// prints only the "
        "title. Parts get //Part I//, //Part II// and so on unless you "
        "choose //Titles only//. Front matter is never numbered.")
    s.h3("Running Scenes On", idx=["continuous, export", "scene break ornament"])
    s.p("Normally each scene starts a new page with its own heading. "
        "//Run scenes on with a break ornament// instead pours all the "
        "scenes of a part into one unbroken chapter, with a scene-break "
        "ornament between them and no scene headings. Use it for a "
        "novel written in many short scenes where you do not want a "
        "heading for each. Part titles are kept; front matter is not "
        "affected.")

    # ------------------------------------------------------------------
    s.h2("The Three PDF Layouts", idx=["layouts, PDF", "PDF|layouts", "templates, layouts"])
    s.p("The layouts differ in much more than size, and each is meant "
        "for a particular reader.")
    s.table("x_layouts", "The PDF layouts",
            ["", "Book", "Manuscript review", "Plain proof"], [
        ["Description", "A typeset trade paperback", "Double-spaced "
         "with line numbers", "A simple copy for proofreading"],
        ["Page sizes", "Trade 6 x 9 in (default), A5, US Letter",
         "US Letter", "A4 (default), US Letter"],
        ["Fonts", "Noto Serif (default), Liberation Serif",
         "Liberation Serif (default), Liberation Mono",
         "Liberation Sans"],
        ["Text", "11 pt, justified, hyphenated, first line indented "
         "except after a heading or break", "12 pt, double-spaced, "
         "left-aligned, 1 inch margins", "10.5 pt, 1.5 spacing, "
         "left-aligned"],
        ["Title page", "Title and author, with the copyright line at "
         "the foot", "Author top left, title, //by// author, //about N "
         "words//, copyright line", "Title, author, //N words in N "
         "scenes//"],
        ["Contents", "Yes (option)", "No", "No"],
        ["Heads and feet", "Mirrored margins; book title on left pages, "
         "chapter title on right pages; page number in the foot",
         "Surname / TITLE / page number at top right; the line numbers "
         "restart on every page", "Book title and page number in "
         "the foot"],
        ["New chapter", "New page", "New page", "New page"],
    ], [0.15, 0.30, 0.30, 0.25])
    s.p("Each sample below is a page of a real export of the Residual "
        "example project, not a mock-up.")
    s.gfigure("pdf_book_title", "pdf_book_title",
              "The title page of the Book layout, from a real export of "
              "the Residual example (trade 6 x 9 in)", width=230)
    s.gfigure("pdf_book_toc", "pdf_book_toc",
              "The contents page of the Book layout, from a real export "
              "of the Residual example", width=230)
    s.gfigure("pdf_book_page", "pdf_book_page",
              "A chapter page of the Book layout, with the running head "
              "and the page number, from a real export of the Residual "
              "example", width=230)
    s.gfigure("pdf_ms_title", "pdf_ms_title",
              "The title page of the Manuscript review layout (US "
              "Letter), from a real export of the Residual example",
              width=300)
    s.gfigure("pdf_ms_page", "pdf_ms_page",
              "A text page of the Manuscript review layout, "
              "double-spaced, with the running head and the line "
              "numbers in the margin, from a real export of the "
              "Residual example", width=300)
    s.gfigure("pdf_plain_page", "pdf_plain_page",
              "A page of the Plain proof layout, from a real export of "
              "the Residual example", width=300)
    s.h3("Layouts Are Small Modules", idx=["layouts|adding", "templates, layouts"])
    s.p("A PDF layout is not a setting in a file; it is a short piece "
        "of Python in the program's `core/export/layouts` folder. Each "
        "one gives its name, a one-line description, the page sizes and "
        "fonts it offers, and whether it honors the table of contents, "
        "the run-on option and the numbering words; the dialog and "
        "the form are built from that description, which is why "
        "they show only what a layout can do. Adding a new look means "
        "adding one module there and listing it, with no change to the "
        "export dialog. There is no way yet to add a layout from inside "
        "a project folder.")

    # ------------------------------------------------------------------
    s.h2("Exporting from the Terminal and the Desktop",
         idx=["export|procedure", "Export manuscript", "Open exports folder"])
    s.p(f"{R('x_tasks')} lists the tasks side by side.")
    s.table("x_tasks", "Export tasks in the two applications",
            ["Task", "Terminal application", "Desktop application"], [
        ["Open the export window", "Open the palette (`ctrl+p`) and "
         "choose //Action · Export manuscript//.", "Open the project "
         "menu (the //...// in the title bar) and choose //Export...//, "
         "or open the binder //...// menu and choose //Export...// "
         "under its //export// heading."],
        ["Choose options", "Move with `tab`; the Select boxes open "
         "with `enter`.", "Click the buttons and check boxes."],
        ["See what will be in the book", "A summary line at the top.",
         "A summary line at the top, which updates as you change "
         "options."],
        ["Export", "`ctrl+s` (or `enter` in the copyright line).",
         "The **Export** button."],
        ["Cancel without exporting", "`esc`.", "The **Cancel** button."],
        ["See the result", "A notification, with warnings under it.",
         "The dialog changes to //Export finished//."],
        ["Open the exported file", "Not offered in the application; "
         "open it from your file manager.", "**Open file**."],
        ["Open the folder", "//Action · Open exports folder//.",
         "**Show folder**."],
    ], [0.17, 0.41, 0.42])
    s.p("Both applications save the open scene before they build the "
        "book, so the export has the words you typed a moment ago.")
    s.gfigure("g_export_menu", "g_export_menu",
              "The project menu in the desktop application, with the "
              "//Export...// entry that opens the dialog", width=200)
    s.h3("The Desktop Dialog", idx=["export dialog", "desktop|export"])
    s.p("The dialog is titled //Export the book//. At the top a line "
        "counts what will be exported, for example //4 scenes, 1,502 "
        "words, 2 parts//; if some scenes have pending AI drafts it adds "
        "//; 1 scene has unaccepted AI drafts//. The line is worked "
        "out again whenever you change the front matter, drafts, "
        "headings or run-on options. The rows are, in order, //Format//, "
        "//Layout// (with the layout's description under it), //Page "
        "size//, //Font//, //Scene headings// or //Chapter headings//, "
        "then the check boxes, then the copyright line for PDF. Under "
        "the options is the reminder //Files are saved in the project's "
        "exports folder; nothing is overwritten.//")
    s.gfigure("g_export_dialog", "g_export_dialog",
              "The Export the book dialog in the desktop application, "
              "with the live summary line, the format and layout "
              "buttons, and the options", width=330)
    s.p("Press **Export** and a progress bar appears, labeled with the "
        "stage: //Reading scenes//, then //Typesetting// (for a PDF) or "
        "//Writing the file//, then //Done//. The options and the "
        "Export button are locked while it runs. **Export** is also "
        "dimmed when there is nothing to export or the chosen format "
        "is not available.")
    s.p("When it finishes, the dialog becomes //Export finished//. It "
        "says //Saved to exports/...//, then the page count (PDF only) "
        "and the word count, and lists any warnings. **Back** returns "
        "to the options, **Show folder** opens the exports folder, "
        "**Open file** opens the file in whatever program your "
        "desktop uses for that kind of file, and **Close** leaves.")
    s.gfigure("g_export_done", "g_export_done",
              "The dialog after an export, with the saved file name, the "
              "page and word counts, and the Open file and Show folder "
              "buttons", width=330)
    s.attention("Open file and Show folder hand the file or folder to "
                "your desktop (through `xdg-open`) and only when you "
                "click. They work only on a file inside the project's "
                "`exports` folder. If the file has been moved or deleted "
                "since, you get //... is no longer in the exports "
                "folder//.")
    s.h3("The Terminal Form", idx=["export form", "terminal|export"])
    s.p("//Action · Export manuscript// opens a form titled //Export "
        "manuscript//. Under the title is the same summary line, then "
        "these rows: //Format//, //Layout (PDF)//, //Page size (PDF)//, "
        "//Scene headings// (or //Chapter headings//), four check boxes "
        "(//Table of contents//, //Include front matter//, //Run scenes "
        "on with a break ornament//, //Include pending AI drafts//) and "
        "//Copyright line (PDF)//. The rows marked PDF are dimmed when "
        "another format is chosen, and the table-of-contents box is "
        "dimmed for the two layouts that have no contents. Any warnings "
        "(at most four) are shown in yellow below the options. The foot "
        "of the form reads //tab next · ctrl+s export · esc cancel · "
        "saved in exports///.")
    s.figure("tui_export", "tui_export",
             "The Export manuscript form in the terminal application")
    s.p("After you press `ctrl+s` a notice //Exporting...// appears and "
        "the file is written in the background, so you can keep working. "
        "When it is done, a notification gives the file's path, the "
        "page count (PDF only) and the word count, followed by up to "
        "three warnings.")
    s.figure("tui_export_done", "tui_export_done",
             "The notice after an export in the terminal application")
    s.p("//Action · Open exports folder// opens the `exports` folder in "
        "your desktop's file manager, creating the folder if it does "
        "not exist yet. Like the desktop buttons, it does this only "
        "when you pick it.")

    # ------------------------------------------------------------------
    s.h2("Where the Files Go", idx=["exports folder", "export|file names", "file names, export"])
    s.p("Every export is a new file in the `exports` folder at the top "
        "of the project (the folder is created the first time). The "
        "name is built like this.")
    s.code("""\
exports/<project title>-<layout or format>-<YYYYMMDD-HHMM>.<ext>

exports/residual-book-20261001-1430.pdf
exports/residual-manuscript-20261001-1432.pdf
exports/residual-plain-20261001-1433.pdf
exports/residual-docx-20261001-1435.docx
exports/residual-md-20261001-1436.md
""")
    s.p("The project title is turned into a short lower-case name "
        "(`manuscript` if the title gives nothing usable). For a PDF "
        "the middle part is the layout's name: `book`, `manuscript` or "
        "`plain`. For other formats it is the format: `docx`, `epub`, "
        "`md` or `tex`. If a file with that name already exists (two "
        "exports in the same minute), Chisel adds `-2`, then `-3`, "
        "and so on. An export never replaces an earlier file.")
    s.p("The file is first written under a hidden temporary name and "
        "renamed only when complete. A failed export therefore leaves "
        "nothing behind: no half-written PDF to be confused for the "
        "real one.")
    s.note("`exports` belongs to you. Chisel never reads it back, "
           "never indexes it and never deletes from it. If you keep "
           "your project under version control and do not want PDFs "
           "in it, add `exports/` to the ignore file. Delete old "
           "exports yourself from your file manager.")

    # ------------------------------------------------------------------
    s.h2("Remembered Options", idx=["project.toml|export", "export|remembered options"])
    s.p("After a successful export, Chisel remembers the options you "
        "used, so the next export starts where this one left off. They "
        "are kept per project, in a small `[export]` section of "
        "`project.toml`:")
    s.code("""\
[export]
format = "pdf"
layout = "book"
page_size = "trade"
font = ""
numbering = "words"
toc = true
include_front_matter = true
include_drafts = false
continuous = false
copyright = "First edition, 2026"
""")
    s.p("An empty `font` means the layout's own default. You may edit "
        "the section by hand. If a stored value is not valid (a page "
        "size that does not exist, say), Chisel ignores the whole "
        "section and starts from the standard defaults, rather than "
        "failing. Options are saved only after an export that "
        "succeeds; closing the dialog, or a failed export, saves "
        "nothing. The desktop and the terminal share these settings.")

    # ------------------------------------------------------------------
    s.h2("Word and Page Counts", idx=["export|word count", "page count"])
    s.p("The summary line and the result show the number of words in "
        "the book. This counts the prose that will be printed: the "
        "scene text after links are flattened, drafts are resolved and "
        "markers removed. It includes front matter when that is "
        "included, so it can be higher than the manuscript word "
        "count in the status bar (Chapter 5), which leaves front "
        "matter out. Only PDF has a page count, since only the PDF "
        "layouts decide where pages break. The count is the number "
        "of pages in the file, including the title page and contents.")

    # ------------------------------------------------------------------
    s.h2("Messages and Warnings", idx=["export|warnings", "warnings, export"])
    s.p("Export reports problems in plain words, never by quietly "
        "dropping something. Warnings do not stop the export; they are "
        "shown in the form beforehand and listed again with the result. "
        f"{R('x_messages')} lists them.")
    s.table("x_messages", "Export messages",
            ["Message", "Meaning"], [
        ["//N// scenes have unaccepted AI drafts, left out (the "
         "original text is used).", "Pending drafts exist and the "
         "switch is off. With it on the message ends //included as "
         "written//."],
        ["//scene//: expand marker removed: //instruction//", "A "
         "`{{expand: ...}}` note you left in a scene (Chapter 11) is "
         "not printed. The warning shows the instruction so you can "
         "find the place."],
        ["//scene//: the scene has no text", "The scene is empty, "
         "so it is in the book as a heading with nothing under it."],
        ["//scene//: an AI draft replaced text whose original is "
         "missing; it is left out of the export", "See the warning "
         "under Pending AI Drafts."],
        ["//Font// is not installed; used //Other font//.", "The font "
         "you chose is missing; the layout's next font was used."],
        ["There is nothing to export yet: the book has no scenes",
         "No placed scenes. Nothing is written."],
        ["PDF export needs ReportLab: pip install "
         "'lorewrite[export]'", "The PDF library is not installed."],
        ["pandoc is not installed; install it to export DOCX, EPUB or "
         "LaTeX", "pandoc is not on the path."],
        ["pandoc failed: //detail//", "pandoc reported an error; the "
         "last line of its message is shown."],
        ["pandoc took longer than 120 seconds and was stopped",
         "A very long book, or a stuck pandoc."],
        ["An export is already running.", "Desktop only: one export at "
         "a time."],
        ["xdg-open is not available here; open the file from your file "
         "manager", "Your system has no `xdg-open`."],
    ], [0.55, 0.45])

    # ------------------------------------------------------------------
    s.h2("How an Export Runs", idx=["export|worker", "export|progress"])
    s.p("Typesetting a long book takes seconds, so the work is done "
        "in the background and the application stays usable. In the "
        "terminal a notification marks the start and the end. In the "
        "desktop the dialog asks the program for its progress about "
        "four times a second and draws the bar. The desktop "
        "allows only one export at a time. While an export runs you can keep editing, but the "
        "scenes are read in the first moment, so changes made after "
        "that are not in the file.")
    s.p("DOCX, EPUB and LaTeX are made by handing the book to pandoc. "
        "Chisel gives pandoc plain text with its special characters "
        "escaped and with raw HTML, raw TeX and file includes switched "
        "off, so nothing in a scene can make pandoc fetch a file or "
        "run anything. pandoc has two minutes to finish. In these "
        "formats the title and author are the document's title and "
        "author, the contents option becomes a pandoc table of contents, "
        "and an EPUB is split into one file per chapter (per part when "
        "the book has parts).")

    # ------------------------------------------------------------------
    s.h2("Limits and Quirks", idx=["export|limits"])
    s.bullets([
        "The **author name** on the title page comes from the `author` "
        "line of `project.toml`; with none, the title page has only "
        "the title. The **title** is the project title.",
        "The page size, font and layout options mean nothing for "
        "DOCX, EPUB, Markdown and LaTeX; those formats ignore them. "
        "The copyright line is a PDF option in both screens, but a "
        "line entered earlier is still remembered and is written near "
        "the top of the Markdown and pandoc formats too. Clear it "
        "in a PDF export if you do not want it.",
        "Export is not an editor: pictures, footnotes, tables and "
        "special formatting in a scene are not carried into the "
        "book. Only text, paragraphs, italic, bold, sub-headings and "
        "scene breaks are.",
        "A scene with a missing or malformed title line is exported "
        "under its file name.",
        "The Book layout hyphenates only when the `pyphen` helper is "
        "installed (it comes with `lorewrite[export]`).",
        "The look of the Word, EPUB and LaTeX files is pandoc's default; "
        "Chisel does not offer styles for them. Open the file in "
        "your own tool to restyle it.",
        "There is no export of a single scene or a selection, and no "
        "export of the parked scenes. To export part of the book, "
        "move the rest to Parked scenes first.",
    ])


GLOSSARY = [
    ("export", "Writing the manuscript out as a single file (PDF, DOCX, "
     "EPUB, Markdown or LaTeX source) in the project's exports folder. "
     "Read-only: no scene is changed."),
    ("exports folder", "The `exports` folder at the top of a project, "
     "where every exported file is saved. Files are never overwritten."),
    ("layout", "One of the three PDF looks: Book, Manuscript review or "
     "Plain proof. Each offers its own page sizes and fonts."),
    ("Book layout", "The PDF layout that looks like a trade paperback, "
     "with title page, contents, running heads and page numbers."),
    ("Manuscript review", "The PDF layout in standard manuscript form: "
     "double-spaced US Letter with line numbers on every page."),
    ("Plain proof", "A simple sans-serif PDF layout with 1.5 line "
     "spacing, for proofreading."),
    ("pandoc", "A separate, free program that Chisel uses to write "
     "DOCX, EPUB and LaTeX files. It must be installed to use those "
     "formats."),
    ("ReportLab", "The Python library that draws the PDF layouts. An "
     "optional install: `pip install 'lorewrite[export]'`."),
    ("scene break ornament", "The mark printed between scenes that run on "
     "within a chapter: three asterisks in the Book layout, `#` in "
     "Manuscript review."),
    ("front matter in export", "The `front-matter` part, exported first "
     "when //Include front matter// is on, without numbers or a place "
     "in the contents."),
]

MSG_TUI = {
    "info": [
        ["Exporting...", "An export has started in the background."],
        ["Exported to //exports/file// (//N// pages, //N// words)",
         "The export finished; pages are shown for PDF only."],
    ],
    "warn": [
        ["There is nothing to export yet: the book has no scenes",
         "No placed scenes, so the form does not open."],
        ["//N// scene(s) have unaccepted AI drafts; their original text "
         "is exported unless you tick the box.", "Shown in the form."],
        ["Install pandoc / Install ReportLab: pip install "
         "'lorewrite[export]'", "The chosen format cannot run yet."],
        ["//scene//: expand marker removed: //text//",
         "An `{{expand: ...}}` note was left out of the book."],
        ["//Font// is not installed; used //Other font//.",
         "A fallback font was used."],
        ["xdg-open is not available here; open the file from your file "
         "manager", "Open exports folder could not run."],
    ],
    "err": [
        ["pandoc is not installed; install it to export DOCX, EPUB or "
         "LaTeX", "pandoc is missing."],
        ["PDF export needs ReportLab: pip install 'lorewrite[export]'",
         "ReportLab is missing."],
        ["pandoc failed: //detail//", "pandoc reported an error."],
    ],
}

MSG_GUI = [
    ["//N// scenes, //N// words, //N// parts; //N// scenes have "
     "unaccepted AI drafts", "The live summary line of the Export "
     "dialog."],
    ["Saved to //exports/file//", "The export finished; pages (PDF) "
     "and words follow."],
    ["The export uses the text from before the draft. / Their text "
     "will be in the export.", "Under the summary, depending on the "
     "drafts switch."],
    ["An export is already running.", "Only one export at a time."],
    ["//file// is no longer in the exports folder", "Open file found "
     "that the file was moved or deleted."],
    ["pandoc is not installed; install it to export DOCX, EPUB or LaTeX",
     "pandoc is missing."],
    ["PDF export needs ReportLab: pip install 'lorewrite[export]'",
     "ReportLab is missing."],
    ["Could not save the current document first.", "The open scene "
     "could not be saved, so the dialog did not open."],
]

PALETTE = []

PROBLEMS = [
    ["The DOCX, EPUB or LaTeX format is dimmed, or says “install pandoc”.",
     "Install pandoc with your system's package manager, then open the "
     "export window again."],
    ["The PDF format is dimmed, or says “install ReportLab”.",
     "Install the export extras: `pip install 'lorewrite[export]'`, then "
     "restart Chisel."],
    ["The export says there is nothing to export.", "Only placed scenes "
     "are exported. Move scenes out of Parked scenes and the Trash "
     "into the manuscript (Chapter 5)."],
    ["My AI draft is missing from the PDF.", "Pending drafts are left "
     "out by default. Accept the draft in the scene, or turn on "
     "//Include pending AI drafts//."],
    ["A note I left in a scene does not appear in the book.",
     "`{{expand: ...}}` markers and comments are removed on purpose. "
     "The warning shows what was removed."],
    ["The PDF used a different font than I chose.", "The font is not "
     "installed. Install Noto Serif or Liberation fonts and export "
     "again."],
]
