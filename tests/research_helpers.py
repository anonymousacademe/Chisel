"""Shared by research tests that need an empty book: a new research project starts with an outline."""

import shutil


def clear_starter(project):
    """Remove the starter outline and the parked "Start here" note of a new research project, leaving
    ``manuscript/`` empty (what a bare research project looked like before starter outlines)."""
    for entry in list(project.manuscript_dir.iterdir()):
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    return project
