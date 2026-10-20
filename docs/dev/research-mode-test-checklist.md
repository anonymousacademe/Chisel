# Research mode: hands-on test checklist (2026-10-20, main at 17f21c2)

Nothing below has been seen in a running window by the people who wrote it; the code is tested, the look and feel is not.
Start the app: `& "$env:USERPROFILE\.chisel-dev\venv\Scripts\chisel-gui.exe"` (close the installed 0.5.0 first).
Make a fresh project for this (Research, Manuscript, Environmental Modelling & Software). Tell me what is confusing, ugly or wrong,
not only what breaks. Use the project menu: the three dots (More) in the title bar.

## 1. Start (2 min)
- [ ] New project: Research, Manuscript, journal "Environmental Modelling & Software": 15 sections appear in the binder in order.
- [ ] "Start here" is under Parked sections, not in the book.
- [ ] More > Journal requirements: warnings for every empty required section; nothing green that should not be.

## 2. Zotero and sources (5 min)
- [ ] More > Zotero settings > Check connection (local and, if you saved the key, web).
- [ ] More > Sync sources from Zotero: tick the WRRI collection, Preview (spinner shows), tick some papers, Apply.
- [ ] Sources group lists names like "Wang et al. 2026"; open one: readable block, no raw YAML, banner, dimmed markers.
- [ ] The Source card (Notes panel): Cite as, Copy, Open in Zotero, collections.

## 3. Citing (3 min)
- [ ] Type `[[@` in a section: a list appears, pick one. Also try Ctrl+Shift+L (Cite a source...) with a page number.
- [ ] The citation shows as "(Name and Name, 2026)" style; click it: raw text appears; move away: it folds back.
- [ ] A made-up key is marked as unresolved.

## 4. Writing checks (3 min)
- [ ] Write 200 words in Abstract: requirements warn "over 150"; cut it: ok. Add 6 highlights over 85 characters: warns.
- [ ] More > Guidelines: add your guide PDF; View text.
- [ ] Guidelines > Suggest requirements from guidelines: tick the PDF, Suggest, read the quoted rules, untick bad ones, Add.
      Unverified quotes must be unticked and flagged. Your new rules show in Journal requirements under "Your requirements".

## 5. Outline assistant (5 min)
- [ ] More > Outline assistant (or the button in the Outline view): write a paragraph about a paper, Suggest an outline (try
      with and without a guideline ticked; the "What was sent" box lists what went).
- [ ] Review: untick one item, read "before / after", Apply: sections appear. Check that nothing was deleted and your text is intact.
- [ ] "Use the standard structure" works with no AI.

## 6. Figures, tables, equations (10 min)  [newest, least settled]
- [ ] More > Insert figure: choose a PNG, give a caption, insert: the figure shows in the text, numbered, with its caption.
- [ ] Select a sentence, right-click, Insert table: your sentence must NOT be replaced (the placement goes on its own line below).
- [ ] Table: grid editor (add row and column, alignment, paste from Excel), insert; it shows as a table with "Table 1".
- [ ] Equation: type LaTeX, see the preview; try bad LaTeX (no crash); try "Suggest LaTeX with AI" (Stop works, you must click Use this).
- [ ] Type `[[fig:your-label]]` in a sentence: it shows "Fig. 1"; click it: the object card opens.
- [ ] Click a figure or table in the text: the card opens (caption, alt, width, where used, Delete goes to Trash and warns).
- [ ] Typing in a section with several figures stays smooth.
- [ ] A generated figure (script): the card shows the script, the interpreter and a Trust button; nothing runs until you click.

## 7. Sections wording and numbering (2 min)
- [ ] Menus and dialogs say "section", not "scene". Delete a section: the rest renumber.

Known gaps: no export screen yet (the backend writes Word, LaTeX and PDF through pandoc, which is not installed here);
the data-aware review of Results and Discussion is not built; pictures and data are not sent to any AI.
