"""Chapter 9: Notes, Comments and Research."""


def build(s, R):
    s.chapter("9", "Notes, Comments and Research",
              "Notes to yourself about a passage, a folder of reference "
              "material, and an assistant that remembers your conversations.")
    s.p("A manuscript is not the only thing a writer keeps. There are "
        "reminders about particular sentences (check this against Chapter "
        "2, is this too much?), there are articles and photographs and "
        "tide tables, and there are the questions you ask along the way. "
        "This chapter covers the three places Lorewrite keeps them: "
        "//comments//, which are notes pinned to a passage of a scene; "
        "//research notes//, which are plain pages of reference material "
        "kept in a folder of their own; and //saved conversations//, the "
        "chats you have with the assistant.", idx=["notes", "reference material"])
    s.p("None of these is part of your book. Comments are not in the text, "
        "research notes are not scenes, and conversations are not either. "
        "None of them is counted in your word totals, and none of them is "
        "ever sent to the AI unless this chapter says so. Each section "
        "ends with a short statement of exactly what, if anything, "
        "travels to the AI. The AI features themselves are described in "
        "Chapters 10 and 11.")

    # ------------------------------------------------------------ COMMENTS
    s.h2("Comments", idx=["comment", "comments|concept"])
    s.p("A comment is a note you attach to a passage of a scene: “Does "
        "this contradict chapter 2?”, “Ask Dana about the tram "
        "schedule”, “Too many adjectives.” You select the words the note "
        "is about, write the note, and from then on the passage is "
        "marked. The note itself is kept //beside// the scene, in a small "
        "file in the `.comments` folder of the project. It is never "
        "written into the scene's text, so you cannot export it by "
        "accident, read it aloud by accident, or lose it by deleting a "
        "line of prose.")
    s.p("Comments apply to //scenes// only (including unplaced scenes and "
        "front matter). Character and place notes, research notes, the "
        "style guide and the dictionary cannot carry comments. A comment "
        "may be //open// or //resolved//. Open ones are the ones still "
        "waiting for you; a resolved comment is kept in the list but "
        "no longer marks the page.")
    s.table("t_cmt_not", "What a comment is not",
            ["It is not...", "In practice"], [
        ["Part of the text", "It is not in the scene file, not in an "
         "export, and not in the word count."],
        ["Spell-checked", "Nothing you type in a comment is underlined."],
        ["Sent to the AI by default", "Comments are shared with the "
         "assistant only when you attach them to a chat in the desktop "
         "application (“Attaching Material” below), and then only the "
         "open ones."],
        ["Tied to a position", "A comment follows its //words//, not its "
         "line number. See “Anchoring and Detached Comments.”"],
    ], [0.3, 0.7])

    s.h3("Adding a Comment", idx=["comment|adding"])
    s.proc("To add a comment in the terminal application:", [
        "Open a scene and select the passage (hold `shift` and move the "
        "cursor, or drag with the mouse). If there is no selection, "
        "Lorewrite says //Select the passage to comment on first//; with "
        "no scene open it says //Open a scene first//.",
        "Press `ctrl+p` and choose **Scene · Add comment on selection**.",
        "Type the note at the //Comment:// prompt and press `enter`. "
        "An empty note cancels.",
        "Lorewrite answers //Comment added (it is kept beside the scene, "
        "not in the text)//.",
    ])
    s.p("If your project's unit is “chapter” (Chapter 15), the entry reads "
        "**Chapter · Add comment on selection**. The same applies to every "
        "palette entry that begins with //Scene// in this chapter.")
    s.proc("To add a comment in the desktop application:", [
        "Open a scene and select the passage.",
        "Click the comment button in the editor toolbar (the speech "
        "bubble with a plus; its tooltip is //Add a comment on the "
        "selected passage//). It is dimmed until a scene is open and text "
        "is selected.",
        f"In the **Add comment** dialog ({R('fig_g_comment_add')}), write "
        "your note under //Your note//. The dialog shows the passage you "
        "selected, so you can check you chose the right one.",
        "Click **Add comment**, or press `ctrl+enter` (`cmd+enter` on a "
        "Mac). The button stays dim while the note is empty.",
    ])
    s.gfigure("fig_g_comment_add", "g_comment_add", "The Add comment dialog: "
              "the selected passage, a box for the note, and a reminder "
              "that the note is not part of the text, is not "
              "spell-checked and is not sent to the AI", width=300)
    s.p("A toast says //Comment added. It is kept beside the scene, not in "
        "the text.// and the assistant panel opens on its **Notes** tab, "
        "where you can see the new comment in the list.")
    s.p("A comment's note may be up to 5,000 characters, and the passage "
        "you select up to 2,000. Notes shorter than a character or longer "
        "than the limit, and selections outside the prose (inside the "
        "scene's details block at the top), are refused with a short "
        "message: //a comment needs some text//, //a comment is at most "
        "5000 characters//, //select at most 2000 characters to comment "
        "on//, //comments go on the prose, not the scene details//.")

    s.h3("Seeing Your Comments on the Page", idx=["comment|marking"])
    s.p("In the terminal application an open comment makes its passage "
        "faintly underlined. Resolved and detached comments are not "
        "marked. In the desktop application an open comment gives its "
        "passage a subtle highlight and puts a small marker in the left "
        f"margin of the page, beside the passage's first line ({R('fig_g_comment_popover')}). "
        "Click the marker to read or change the note.")
    s.gfigure("fig_g_comment_popover", "g_comment_popover", "The comment "
              "popover over the page: the date, the passage, the note, and "
              "the buttons Save, Resolve and Delete", width=300)

    s.h3("Reading, Editing, Resolving and Deleting", idx=["comment|resolving",
                                                         "comment|deleting"])
    s.p("In the terminal application every comment action starts from the "
        "list. Press `ctrl+p` and choose **Scene · Comments**. The window "
        f"({R('fig_tui_comments')}) is called //Comments - <scene "
        "title>//. Each row begins with //open// or //done//, then //line "
        "N// (or //detached//), the start of the passage in quotation "
        "marks and the start of the note; a line below the list shows the "
        "full note of the highlighted comment.")
    s.figure("fig_tui_comments", "tui_comments", "The Comments list of a "
             "scene in the terminal application; here the one comment is "
             "detached, because its passage was cut")
    s.table("t_cmt_keys", "Keys in the Comments window (terminal)",
            ["Key", "Action"], [
        ["enter", "Jump to the comment: the passage is selected in the "
         "editor and the editor gets the focus. On a detached comment "
         "this says //This comment is detached: its passage is no longer "
         "in the text//."],
        ["r", "Resolve the comment, or reopen it if it is resolved."],
        ["e", "Edit the note (the //Comment:// prompt appears with the "
         "old note filled in)."],
        ["d", "Delete the comment. Lorewrite asks //Delete this "
         "comment?// and adds that the text it was about is not touched; "
         "the button is **Delete comment**."],
        ["esc", "Close the window."],
    ], [0.2, 0.8], mono_cols=(0,))
    s.p("After each action the window opens again on the same comment, so "
        "you can work down the list. If the scene has none, the window "
        "says //No comments on this scene. Select text and use 'Add "
        "comment on selection'.//")
    s.p("In the desktop application, click the marker in the margin (or "
        "the comment's row in the list below) to open the popover "
        f"({R('fig_g_comment_popover')}). It shows the date, whether the "
        "comment is resolved, the passage, and the note in a box you can "
        "edit directly.")
    s.bullets([
        "**Save** stores your change to the note. It is available only "
        "when the note has changed and is not empty. `ctrl+enter` does "
        "the same.",
        "**Resolve** marks the comment as done; on a resolved comment the "
        "button reads **Reopen**.",
        "The trash button **Delete comment** removes it, after a "
        "confirmation (//Delete this comment? The text it is about is not "
        "touched.//).",
        "Clicking outside the popover saves an edited note, or simply "
        "closes it if you changed nothing. `esc` closes it.",
    ])
    s.p("The **Notes** tab of the assistant panel "
        f"({R('fig_g_comments_tab')}) lists the comments of the open scene "
        "under //Comments · N//, where N is the number of open ones. Each "
        "row shows the passage, the start of the note, and the date and "
        "line (//Oct 1 · line 12//). Click a row to select the passage "
        "and open its popover; the button on the right resolves or "
        "reopens the comment. Resolved comments are hidden; use "
        "//Show resolved (N)// at the foot of the list to see them. "
        "Detached comments come first, then the rest from the top of the "
        "scene to the bottom.")
    s.gfigure("fig_g_comments_tab", "g_comments_tab", "The Notes tab with "
              "its Comments section; the comment shown is detached, so it is "
              "marked and listed first", width=215)

    s.h3("Anchoring and Detached Comments", idx=["comment|anchoring",
                                                  "detached comment"])
    s.p("Lorewrite does not remember //where// a comment is, only //what// "
        "it was about: the words you selected and a little of the text "
        "around them. Every time it needs the comment, it looks for those "
        "words again. That is why you can keep writing above, below and "
        "inside the passage and the comment stays with it.")
    s.bullets([
        "If the words are still there (even if a line has been re-wrapped "
        "or the spacing changed), the comment is found. If the same words "
        "occur twice, the surrounding text decides which one is meant.",
        "If you edit the middle of a long passage, Lorewrite can still "
        "find it by its beginning and its end. If you rewrite the whole "
        "passage but leave the text on both sides, the comment lands on "
        "whatever now stands between them.",
        "A comment that is found after an edit takes the new wording as "
        "its passage.",
    ])
    s.p("When the passage cannot be found at all (you deleted it, or "
        "rewrote it and the text around it), the comment becomes "
        "//detached//. A detached comment is not deleted. It stays in the "
        "list, shown first and marked //detached// (terminal) or "
        "//Detached// (desktop), so you can read what you wanted to "
        "remember. You cannot jump to it, because there is nowhere to "
        "jump. If the words come back, for example when you undo, or "
        "retype the passage, the comment attaches again by itself.")
    s.note("There is no command to move a comment to a different "
           "passage. To do that, add a new comment on the new passage and "
           "delete the old one.")
    s.p("Comments follow their scene. If you rename, move or reorder the "
        "scene, its comments go with it; if you delete the scene they go "
        "to the Trash with it and come back when you restore it "
        "(Chapter 5).")

    s.h3("What Is Sent to the AI", idx=["privacy|comments"])
    s.p("Nothing. Comments are not part of the text that the assistant, "
        "the draft prompt or the continuity check read. The only way a "
        "comment reaches the AI is that you attach it to a conversation "
        "in the desktop application; only open comments are attached, and "
        "only for the chat you attached them to.")

    # ----------------------------------------------------------- RESEARCH
    s.h2("Research Notes", idx=["research notes", "research folder",
                                "research/"])
    s.p("A research note is a page of reference material: an article you "
        "want to remember, a list of tram stops, your own summary of how "
        "tides work. Research notes live in a folder named `research` "
        "inside the project folder. Each is a plain Markdown file, and "
        "you may arrange them in subfolders as you like.")
    s.p("They differ from the other kinds of page in the project:")
    s.table("t_res_kinds", "Research notes compared with scenes and notes",
            ["", "Scene", "Character or place note", "Research note"], [
        ["Part of the book", "Yes", "No", "No"],
        ["Counted in word totals", "Yes", "No", "No"],
        ["Spell-checked", "Yes", "No", "No"],
        ["In the link index (mentions, backlinks)", "Yes", "Yes", "No"],
        ["Read by the continuity check", "Yes", "Yes (as canon)", "No"],
        ["Can be searched by Research question", "No", "No", "Yes"],
    ], [0.34, 0.14, 0.28, 0.24])
    s.p("A research note needs no particular format. Its title is its "
        "first line that starts with `#`; without one, the file name "
        "(`tide-tables.md` becomes //Tide Tables//). Files and folders "
        "whose names begin with a dot are ignored. The notes are listed "
        "in alphabetical order of their paths.")

    s.h3("Creating a Research Note", idx=["research notes|creating"])
    s.table("t_res_tasks", "Creating and opening research notes",
            ["Task", "Terminal application", "Desktop application"], [
        ["New note", "`ctrl+p`, **Action · New research note**; type the "
         "title at //New research note title://. The note is created "
         "and opened.", "Binder menu (the ellipsis beside **Scene and "
         "part options**), **New research note…**; type a //Title// and "
         "click **Create**."],
        ["Note from a link", "`ctrl+p`, **Action · New research note from "
         "a link**; paste at //Link (https://...)://.", "Binder menu, "
         "**New research note from a link…**; or paste or drop a link "
         "(below)."],
        ["Open a note", "`ctrl+p`, type the title; choose "
         "**Research · <title>**.", "Open the **Research** group in the "
         "binder and click the note."],
        ["Delete a note", "Open it, then `ctrl+p`, **Action · Delete "
         "research note**.", "Open it, then the binder menu, **Move this "
         "research note to the Trash…**."],
    ], [0.17, 0.42, 0.41])
    s.p("A new note is a file named after its title (//Tide tables// "
        "becomes `research/tide-tables.md`; a second note of that name "
        "becomes `tide-tables-2.md`) with the title as its first line. A "
        "note must have a title: //a research note needs a title//.")
    s.p("In the desktop application the notes appear in the binder under "
        f"a group called **Research** ({R('fig_g_research_binder')}). The "
        "group shows how many notes it holds; subfolders appear as "
        "folders inside it, and each note shows its word count. The "
        "group opens by itself when you create a note. The terminal "
        "application does not show research notes in its sidebar; you "
        "reach them through the palette, as above.")
    s.gfigure("fig_g_research_binder", "g_research_binder", "The Research "
              "group opened in the binder, with a subfolder and several "
              "notes", width=150)

    s.h3("A Note from a Link", idx=["research notes|from a link"])
    s.p("Lorewrite can start a note from a web address. It does not fetch "
        "the page. It only saves the link, and a title made from the "
        "address, so that you remember to read it, or so that you can "
        "paste in the passages you want to keep. A link note looks like "
        "this:")
    s.code("""\
# example.com - tide tables explained

https://www.example.com/articles/tide-tables-explained.html
""")
    s.p("The title is the name of the site (without a leading `www.`), a "
        "dash, and the last part of the address with the hyphens turned "
        "into spaces. The address must begin with `http://` or "
        "`https://` and contain no spaces; otherwise Lorewrite says "
        "//that is not a web link (it should start with http:// or "
        "https://)//.")
    s.p("In the desktop application there are two quick ways to start a "
        f"link note ({R('fig_g_research_link')}). If a single web address "
        "is on the clipboard and you press `ctrl+v` while the focus is "
        "//outside// any text box or the editor, the **New research note "
        "from a link** dialog opens with the address filled in. If you "
        "drag a link from your browser onto the binder, the binder "
        "highlights, and the same dialog opens when you let go. The "
        "dialog asks only for the //Link (https://…)//; click **Save "
        "link**. A toast says //Saved the link as a research note: "
        "<title>//.")
    s.gfigure("fig_g_research_link", "g_research_link", "The New research "
              "note from a link dialog, with a pasted address and the "
              "reminder that the page is not downloaded", width=300)
    s.p("In the terminal application there is no pasting or dropping; you "
        "use the palette entry and paste the address into its prompt. "
        "Lorewrite answers //Saved the link as a research note (the page "
        "is not downloaded)//.")

    s.h3("Moving a Research Note to the Trash", idx=["research notes|Trash",
                                                      "Trash|research notes"])
    s.p("Deleting a research note does not destroy it. Both applications "
        "ask first, then move the file to the project's Trash, where you "
        "can restore it or delete it for good. The terminal confirmation "
        "reads //Move the research note '<title>' to the Trash?// with "
        "the button **Move to Trash**, and the application then opens the "
        "first scene. The desktop dialog is titled **Move research note "
        "to the Trash**, and its toast offers an **Open Trash** button. "
        "Chapter 5 describes the Trash in full, including restoring.")

    s.h3("What Is Sent to the AI", idx=["privacy|research notes"])
    s.p("Writing, opening, renaming and deleting research notes sends "
        "nothing anywhere. Notes are read by the AI in two cases only: "
        "when you ask a //Research question// (below), and when you "
        "attach a note to a chat in the desktop application.")

    # ------------------------------------------------- RESEARCH QUESTION
    s.h2("Asking Your Notes a Question", idx=["Research question",
                                              "citations"])
    s.p("A //Research question// is a question to the assistant that is "
        "answered from your own research notes, together with your "
        "story's characters and places (its //canon//), and not from "
        "whatever the AI model happens to know. The answer cites the "
        "notes it used by number, so you can open them and check. It "
        "costs a small amount of money per question, like any AI request "
        "(Chapter 10), and needs an OpenRouter key.")
    s.table("t_rq_how", "Asking a Research question",
            ["", "Terminal application", "Desktop application"], [
        ["Start", "`ctrl+p`, **Action · Research question**. The "
         "assistant window opens in research mode. From an ordinary "
         "assistant chat, press `ctrl+r` to switch.", "In the assistant "
         "panel, click the **Research** tile (//Your notes + canon//) in "
         "the quick actions. It is highlighted while on; click again to "
         "turn it off."],
        ["Prompt", "//Ask a question your research notes can answer...//",
         "The composer shows a **Research** tag and //Ask a question your "
         "research notes can answer…//"],
        ["While working", "(working...) in the window's title.",
         "//Searching your notes…//"],
        ["Cited notes", "A line //notes: [1] Title  [2] Title// under the "
         "answer. `ctrl+o` opens one.", "A //Notes:// line of chips, "
         "//[1] Title//. Click a chip to open the note."],
    ], [0.14, 0.43, 0.43])
    s.gfigure("fig_g_research_answer", "g_research_answer", "A research "
              "answer in the assistant panel, with chips naming the notes "
              "it was drawn from", width=215)
    s.p("If you ask with no research notes at all, no AI request is made. "
        "The terminal shows //There are no research notes yet. Add some "
        "under research/ (a new note, or a pasted link) and ask "
        "again.//; in the desktop application, switching the mode on "
        "says //Research answers come from your research notes. Add some "
        "under Research in the binder first (a new note, or paste a "
        "link).//")

    s.h3("How the Search Works", idx=["Research question|how it works"])
    s.p("Lorewrite does not send your whole `research` folder to the AI. "
        "It first looks through the notes itself, on your computer, using "
        "plain keyword matching, and sends only the best few passages.")
    s.bullets([
        "The words of your question are reduced to their stems "
        "(//tides// and //tidal// are not equated, but //tides// and "
        "//tide// are) and little words are dropped. Words shorter than "
        "three letters are ignored.",
        "Each note is scored by how often those words occur in it, "
        "counting rare words more than common ones, with a bonus when a "
        "word is in the note's title.",
        "The best five notes are used. From each, Lorewrite picks the "
        "single paragraph that matches best, up to 1,500 characters, and "
        "the sum of the excerpts is held to about 9,000 characters.",
        "The excerpts are numbered in the order they are listed, "
        "[1], [2] and so on, and sent to the AI with your question and "
        "your canon. The AI is told to cite only those numbers, to invent "
        "no sources, and to say so when the notes do not cover the "
        "question. The last six turns of the conversation go along, each "
        "trimmed to 1,500 characters, so you can ask a follow-up.",
    ])
    s.attention("The search matches words, not meaning. A question about "
                "“sea levels” will not find a note that only says "
                "“the water rose,” and a note that says //boat// will not "
                "answer a question that asks about a //ship//. If an "
                "answer seems to ignore a note you know you wrote, ask "
                "again using the words the note uses. Only five notes, and "
                "only the best paragraph of each, are read, so a long note "
                "is seen in part.")
    s.p("What goes to the AI in a research question, then, is: your "
        "question, up to the five excerpts, your canon (character and "
        "place notes), and the recent turns of the conversation. Scene "
        "text is not sent, unless you attach it in the desktop "
        "application. The style guide is not used in this mode.")

    # ----------------------------------------------------------- ASSISTANT
    s.h2("Saved Conversations", idx=["conversation", "assistant|history",
                                     ".assistant/chats"])
    s.p("The assistant is where you talk to the AI about your scene or "
        "your project: what would Mara do here, what is a good name for "
        "the tram line, is this paragraph clear. Chapter 10 describes what "
        "it can do. What matters for this chapter is that each "
        "conversation is //kept//: after the assistant answers, the whole "
        "chat is saved in the project, in the folder `.assistant/chats`, "
        "one file per conversation. You can close the application, come "
        "back next week, and carry on. The conversations are part of the "
        "project folder, so they are copied and backed up with it.")
    s.p("A conversation is named after your first question (cut to 60 "
        "characters). It is saved //after// the assistant has answered, "
        "so a chat in which every request failed is not saved, and an "
        "answer that failed is never saved. If you regenerate an "
        "answer in the desktop application, the saved chat is rewritten "
        "with the new answer.")

    s.h3("In the Desktop Application", idx=["conversation|desktop"])
    s.p("The assistant panel is on the right of the window. Two buttons at "
        "its top concern history: **Conversation history** (the clock) "
        "and the **More AI actions** menu, whose first two entries are "
        "**New chat** and **Conversation history…**.")
    s.bullets([
        "**New chat** empties the panel and drops the attachments. Your "
        "next answer starts a new saved conversation. The old one stays "
        "in the history.",
        "**Conversation history** opens the **Conversations** dialog "
        f"({R('fig_g_chats')}): the most recent first, each with its "
        "title, the date and time of its last answer, and how many "
        "messages it has.",
    ])
    s.gfigure("fig_g_chats", "g_chats", "The Conversations dialog: saved "
              "chats, newest first, with Rename and Delete on each", width=300)
    s.proc("To go back to an old conversation, rename it or delete it:", [
        "Open the **Conversations** dialog.",
        "Click the title to open the conversation (the tooltip says "
        "//Open this conversation//). The panel switches to the "
        "assistant tab and shows the messages again, with their cited "
        "notes, the scope (//Current scene// or //Project//), and the "
        "attachments.",
        "Click **Rename** to give it a better title. The title becomes a "
        "text box; `enter` or leaving the box keeps the change, `esc` "
        "cancels. A blank title is refused: //a chat needs a title//.",
        "Click the trash button to delete it, and confirm //Delete "
        "“<title>” (N messages)?// with **Delete conversation**.",
    ])
    s.p("Deleting a conversation does not delete anything you saved from "
        "it to your notes (“Saving an Answer to Your Notes” below). If "
        "some attached files of an old conversation no longer exist, "
        "Lorewrite opens it without them and says //Some attachments of "
        "this chat no longer exist and were left off.//")

    s.h3("In the Terminal Application", idx=["conversation|terminal"])
    s.p("There is no key for the assistant in the terminal; it is in the "
        "palette. Press `ctrl+p` and choose **Action · Ask the "
        "assistant** for an ordinary chat, **Action · Research question** "
        "for a research chat, or **Action · Saved conversations** for "
        f"the history. The chat window ({R('fig_tui_assistant')}) shows "
        "what you said after //you// and what the AI said after //ai//; "
        "the line under an answer, if it used research notes, lists "
        "them.")
    s.figure("fig_tui_assistant", "tui_assistant", "The assistant window "
             "in the terminal application, with one question and one "
             "answer")
    s.table("t_chat_keys", "Keys in the assistant window (terminal)",
            ["Key", "Action"], [
        ["enter", "Send what you typed. While an answer is on its way "
         "Lorewrite says //Wait for the current answer//."],
        ["ctrl+r", "Switch between chat and research mode. The title "
         "changes between //Assistant// and //Research//."],
        ["ctrl+o", "Open a research note cited in the latest answer that "
         "cites any. If several, a list //Open which note?// appears. If "
         "none: //No answer here cites a research note//."],
        ["ctrl+s", "Save the latest answer to your notes (below). If "
         "there is none: //There is no answer to save yet//."],
        ["ctrl+t", "Open the Saved conversations window."],
        ["ctrl+n", "Start a new chat."],
        ["esc", "Close the window. The conversation stays in memory while "
         "Lorewrite runs, and reopening the window shows it again."],
    ], [0.2, 0.8], mono_cols=(0,))
    s.note("The history key is `ctrl+t`, not `ctrl+h`: many terminals send "
           "`ctrl+h` as the backspace key. The palette entry **Action · "
           "Saved conversations** opens the same window.")
    s.p(f"The **Saved conversations** window ({R('fig_tui_chats')}) lists "
        "each chat as its title, the date and time and the number of "
        "messages, with //- open now// after the current one. Its keys "
        "are in the hint line at the bottom.")
    s.figure("fig_tui_chats", "tui_chats", "The Saved conversations window "
             "in the terminal application")
    s.table("t_chats_keys", "Keys in the Saved conversations window",
            ["Key", "Action"], [
        ["enter", "Open the highlighted conversation and return to the "
         "assistant window with its messages. A damaged file gives "
         "//that chat file is damaged//."],
        ["r", "Rename it (//Rename the conversation://)."],
        ["d", "Delete it, after //Delete this saved conversation?// "
         "(answers you saved to notes stay); the button is **Delete "
         "conversation**."],
        ["n", "Start a new chat."],
        ["esc", "Go back to the assistant window."],
    ], [0.2, 0.8], mono_cols=(0,))
    s.p("If a conversation has none, the window says //No saved "
        "conversations yet. A chat is saved after the assistant answers.//")
    s.p("The terminal assistant is simpler than the desktop one: it has "
        "no attachments, no regenerate button and no way to insert an "
        "answer into the scene as a draft. It saves the scope of the "
        "chat as the open scene, or the project when no scene is open.")

    s.h3("What Is Sent to the AI", idx=["privacy|assistant"])
    s.table("t_chat_sends", "What the assistant sends with each question",
            ["Mode", "Sent with your question"], [
        ["Chat, with a scene open", "The text of the scene around the "
         "cursor, the canon (character and place notes) and the style "
         "guide. Pending AI drafts are removed first."],
        ["Chat, no scene open", "The titles of the scenes, the canon and "
         "the style guide."],
        ["Research question", "Up to five excerpts of research notes "
         "(1,500 characters each, about 9,000 together), and the canon."],
        ["All modes", "The last six turns of the conversation, each "
         "trimmed to 1,500 characters. The desktop application adds "
         "anything you attach. Comments are never sent unless you attach "
         "them."],
    ], [0.3, 0.7])
    s.p("The desktop panel's scope tag, //Current scene// or //Project//, "
        "decides which of the first two rows applies; clicking it "
        "switches. Saved conversation files themselves are never sent "
        "anywhere: only the last six turns of the one you have open.")

    # -------------------------------------------------------------- ATTACH
    s.h2("Attaching Material (Desktop Only)", idx=["attach", "attachments"])
    s.p("By default the assistant sees only what is around your cursor "
        "(chat), or the best research excerpts (research). Sometimes you "
        "want it to look at something specific: the whole of last "
        "chapter, the notes on Mara, the comments you left yourself. The "
        "desktop application lets you //attach// such material to the "
        "conversation. The terminal application has no attachments.")
    s.proc("To attach material to a chat:", [
        "Click the paperclip at the left of the composer (//Attach "
        "scenes, notes, research or comments//).",
        f"In the **Attach to this chat** dialog ({R('fig_g_attach')}), "
        "tick what you want. Type in the //Filter…// box to narrow the "
        "list by title.",
        "Watch the counter at the foot: //N attached · about X of Y "
        "words//.",
        "Click **Attach**.",
    ])
    s.gfigure("fig_g_attach", "g_attach", "The Attach to this chat dialog: "
              "scenes, comments, notes and research in groups, each with "
              "its word count, and the counter at the foot", width=300)
    s.p("Attached items appear as chips above the composer. The little "
        "cross on a chip removes it; hovering names its kind. Changing "
        "the attachments of a conversation that is already saved saves "
        "it at once, so the list is there when you return.")
    s.table("t_attach", "What can be attached and what is sent",
            ["Group", "What the AI receives"], [
        ["Scenes", "The prose of the scene only: the details block and "
         "any pending AI drafts are left out. Any scene may be attached, "
         "including unplaced ones and front matter."],
        ["Comments", "Listed only for scenes that have open comments. "
         "One line per open comment, giving the passage and your note. "
         "Resolved comments are not sent. The row shows //· N open//, "
         "and the chip reads //Comments · <scene title>//."],
        ["Notes", "A character or place note: its type and its text."],
        ["Research", "The whole text of the research note."],
    ], [0.17, 0.83])
    s.p("The dialog says that “Comments are shared only this way.” The "
        "assistant is told that what you attach is material to use. In "
        "research mode, attachments are extra reading, but only the "
        "numbered research notes can be cited.")

    s.h3("Limits and Trimming Reports", idx=["attach|limits"])
    s.p("Everything attached costs money (the AI is paid by the amount of "
        "text), so there are limits. No more than 12 items can be "
        "attached; a single item is cut after 8,000 characters; all "
        "together are cut after 24,000 characters (roughly 4,000 words). "
        "The counter in the dialog estimates the size in words and, when "
        "you are over, says //Too much: remove something (at most 12 "
        "items).// and keeps **Attach** dim. The cut is made at a word "
        "boundary and marks the item with an ellipsis.")
    s.p("When you send a question, Lorewrite reports anything it had to "
        "shorten or leave out, in a message after the answer:")
    s.bullets([
        "//Shortened to fit: <titles>.// The named items were cut.",
        "//Not attached: <title> (<reason>).// The item was left out. "
        "The reasons: //it is empty//; //too much is attached already//; "
        "//<path> no longer exists//; //“<title>” has no open "
        "comments//; or, for an item whose kind or file is not what it "
        "was, //not a scene//, //not a note//, //not a research note//.",
    ])
    s.p("An item that is skipped does not stop the question; the "
        "assistant simply answers without it. Read these messages when "
        "an answer ignores something you attached.")

    # ----------------------------------------------------------- SAVE
    s.h2("Saving an Answer to Your Notes", idx=["Save to notes",
                                                "assistant-notes.md"])
    s.p("A good answer should not disappear into a chat. **Save to "
        "notes** copies an answer into a single research note, "
        "`research/assistant-notes.md`, and from then on it is an "
        "ordinary research note: you can edit it, open it from the "
        "binder, and Research question can find it again.")
    s.table("t_save", "Saving an answer",
            ["", "Terminal application", "Desktop application"], [
        ["How", "In the assistant window, `ctrl+s`.", "The **Save to "
         "notes (research/assistant-notes.md)** button under the "
         "answer."],
        ["Which answer", "The latest answer, with the question before it.",
         "The answer whose button you click, with the question before "
         "it."],
        ["Message", "//Saved to research/assistant-notes.md//",
         "A toast //Saved to research/assistant-notes.md// with an "
         "**Open** button, which opens the note and the Research group."],
    ], [0.17, 0.38, 0.45])
    s.gfigure("fig_g_save_toast", "g_save_toast", "The toast after Save to "
              "notes, with its Open button", width=300)
    s.p("Each save appends one entry to the end of the file and leaves "
        "the earlier ones alone. The first save creates the file with a "
        "title and a line of explanation:")
    s.code("""\
# Assistant notes

Answers saved from the assistant, newest last.

## 2026-10-01 - How would Mara react to the tram?

**Prompt:** How would Mara react to the tram?

She would count the stops before she looked up. ...
""")
    s.p("The heading is the date and the question (cut at 70 characters, "
        "or //Saved reply// when there is no question). Answers from "
        "//Brainstorm// (Chapter 12) are saved the same way; saving "
        "all the ideas of a Brainstorm answer adds the numbered list as "
        "a single entry. There is nothing to save when the answer is "
        "empty: //there is nothing to save//.")
    s.p("Saving to notes is a local action. It sends nothing to the AI "
        "and is not a reason to attach anything; but because the file is "
        "a research note, anything in it can be sent later if a Research "
        "question finds it.")

    # ------------------------------------------------------------ ON DISK
    s.h2("How It Is Stored", idx=[".comments", "comments|file format"])
    s.p("Everything in this chapter is plain text in your project folder "
        "(see Appendix A for the full map).")
    s.table("t_notes_files", "Where the notes of this chapter live",
            ["Path", "Holds"], [
        ["`.comments/<scene path>.json`", "The comments of one scene, as "
         "a list. The scene's path, with `/` replaced by `__`, gives the "
         "file name. The file disappears when its last comment is "
         "deleted."],
        ["`research/**/*.md`", "Research notes, in any subfolders."],
        ["`research/assistant-notes.md`", "Answers saved from the "
         "assistant."],
        ["`.assistant/chats/<id>.json`", "One saved conversation each."],
    ], [0.38, 0.62])
    s.p("A comment is stored like this (the date and the id are written "
        "by Lorewrite):")
    s.code("""\
[
  {
    "id": "a1b2c3d4",
    "quote": "The tram never stopped.",
    "prefix": "...the text just before the quote",
    "suffix": "the text just after the quote...",
    "body": "Check whether this contradicts chapter 2.",
    "created": "2026-10-01T10:15:00",
    "resolved": false
  }
]
""")
    s.p("The `quote`, `prefix` and `suffix` are how a comment finds its "
        "passage again. Files that are damaged or not in this shape are "
        "read as empty; Lorewrite does not stop for them. A conversation "
        "file keeps its messages (at most the last 400, each cut at "
        "20,000 characters), the research notes that answers cited, and "
        "in the desktop application the scope and attachments.")

    # ------------------------------------------------------------- LIMITS
    s.h2("Limits and Things to Know", idx=["comment|limits"])
    s.bullets([
        "A comment is anchored by its words. Rewrite the passage "
        "heavily and the comment becomes detached; it is not lost.",
        "Research notes are not spell-checked and are not counted in the "
        "book's word totals.",
        "A link note does not contain the page, only its address. If the "
        "site changes or vanishes, so does your note's usefulness; paste "
        "the text you need into the note.",
        "Research search matches words, five notes at a time. It is a "
        "convenience for finding your own notes, not a search engine.",
        "A conversation is saved only after an answer. A chat that has "
        "had no successful answer is not kept.",
        "Deleting a conversation, or a comment, cannot be undone. "
        "Moving a research note to the Trash can.",
        "Comments and conversations are plain files in the project, so "
        "if you share the project folder (or put it under version "
        "control), you share them too.",
    ])


GLOSSARY = [
    ("comment", "A note attached to a passage of a scene and kept in a "
     "file beside the scene, never in its text."),
    ("detached comment", "A comment whose passage can no longer be found "
     "in the scene. It stays in the list until you delete it."),
    ("resolved comment", "A comment you have marked as done. It is kept, "
     "but no longer marks the page or goes to the AI."),
    ("research note", "A plain Markdown page of reference material in the "
     "research folder; not a scene and not part of the book."),
    ("note from a link", "A research note that holds a web address and a "
     "title made from it; the page itself is not downloaded."),
    ("Research question", "A question to the assistant answered from "
     "your research notes and canon, with the notes it used cited by "
     "number."),
    ("saved conversation", "A chat with the assistant, kept in the "
     "project's .assistant/chats folder after each answer."),
    ("attachment", "A scene, note, research note or set of comments "
     "that you add to a desktop chat so the assistant reads it."),
    ("Save to notes", "Copying an assistant answer to the end of "
     "research/assistant-notes.md."),
    ("citation", "A bracketed number, such as [1], in a research answer "
     "that points to a numbered research note."),
]

MSG_TUI = {
    "info": [
        ["Comment added (it is kept beside the scene, not in the text)",
         "The comment was saved."],
        ["Saved the link as a research note (the page is not "
         "downloaded)", "A note from a link was created and opened."],
        ["Research note moved to the Trash (Action · Open Trash "
         "restores it)", "The open research note was trashed."],
        ["Restored the research note to //path//",
         "A research note came back from the Trash."],
        ["Saved to research/assistant-notes.md",
         "An answer was appended to the notes file."],
        ["Answered (//cost//)", "The assistant replied; the provider "
         "reported the cost."],
    ],
    "warn": [
        ["Select the passage to comment on first",
         "Add comment on selection with nothing selected."],
        ["Open a scene first", "A comment action needs an open scene."],
        ["This comment is detached: its passage is no longer in the text",
         "You tried to jump to a detached comment."],
        ["Open a research note first",
         "Delete research note with no research note open."],
        ["No answer here cites a research note",
         "ctrl+o with no cited note."],
        ["There is no answer to save yet", "ctrl+s before any answer."],
        ["Wait for the current answer",
         "You sent a question while one was still running."],
        ["that is not a web link (it should start with http:// or "
         "https://)", "The link prompt was given something else."],
    ],
    "err": [
        ["There are no research notes yet. Add some under research/ (a "
         "new note, or a pasted link) and ask again.",
         "Research question with an empty research folder."],
        ["That request failed (//reason//). Nothing was changed.",
         "The AI request failed; no text was altered."],
        ["that chat file is damaged",
         "A saved conversation could not be read."],
    ],
}

MSG_GUI = [
    ["Comment added. It is kept beside the scene, not in the text.",
     "The comment was saved."],
    ["Select the passage to comment on first.",
     "The comment button was used with nothing selected."],
    ["Open a scene first.", "A comment needs an open scene."],
    ["The passage is no longer in the text",
     "Tooltip of a detached comment."],
    ["Saved the link as a research note: //title//",
     "A note from a link was created."],
    ["Moved the research note “//title//” to the Trash.",
     "A research note was trashed (button: Open Trash)."],
    ["Research answers come from your research notes. Add some under "
     "Research in the binder first (a new note, or paste a link).",
     "Research mode was switched on with no research notes."],
    ["Searching your notes…", "A research question is being answered."],
    ["Saved to research/assistant-notes.md",
     "An answer was appended to the notes file (button: Open)."],
    ["Some attachments of this chat no longer exist and were left off.",
     "An old conversation was opened after files were removed."],
    ["Shortened to fit: //titles//.",
     "Attached items were cut to the size limits."],
    ["Not attached: //title// (//reason//).",
     "Attached items were left out of the question."],
    ["That request failed. Nothing was changed.",
     "The AI request failed."],
]

PALETTE = [
    ["Scene · Add comment on selection", "Attach a note to the selected "
     "passage (kept in .comments/, never in the text).", ""],
    ["Scene · Comments", "List the scene's comments: jump to one, "
     "resolve, edit or delete it.", ""],
    ["New research note", "Add a plain Markdown note under research/.", ""],
    ["New research note from a link", "Save a web link as a research "
     "note; the page is not downloaded.", ""],
    ["Research · //title//", "Open a research note.", ""],
    ["Delete research note", "Move the open research note to the Trash, "
     "after a confirmation.", ""],
    ["Research question", "AI: answer from your research notes and the "
     "canon, citing the notes used.", ""],
    ["Ask the assistant", "Chat about the open scene or the project.", ""],
    ["Saved conversations", "List, open, rename or delete saved chats.",
     ""],
]

PROBLEMS = [
    ["A comment I wrote is in the list as detached.",
     "The passage it was about was deleted or rewritten. Read the note, "
     "then delete it or add a new comment on the new passage. Retyping "
     "the old words re-attaches it."],
    ["The Add comment button is dim.",
     "Open a scene and select some text first. Notes, research notes and "
     "the style guide cannot carry comments."],
    ["A research answer ignores a note I know I wrote.",
     "Search matches words, not meaning, and uses only the best five "
     "notes. Ask again using the words the note uses."],
    ["Pasting a link does not open the link dialog.",
     "Paste only works with the cursor outside text boxes and the editor, "
     "and with a single address (http:// or https://, no spaces) on the "
     "clipboard. Use the binder menu instead."],
    ["My attachment was left off the answer.",
     "Read the //Not attached// message: the item may be empty, may be "
     "over the limit of 12 items or about 24,000 characters, or its "
     "file may be gone."],
    ["I pressed ctrl+h in the terminal assistant and it deleted a "
     "letter.", "The history key is ctrl+t. (Many terminals send ctrl+h "
     "as backspace.) Action · Saved conversations in the palette opens "
     "the same window."],
]
