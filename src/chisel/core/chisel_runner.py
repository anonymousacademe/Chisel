"""Chisel's own runner for an author's figure script (docs/dev/plan-research-mode.md 7.4).

This file is never imported by Chisel. ``core/figscripts.py`` copies it into a temp folder and runs

    <python> -I -X utf8 chisel_runner.py --script <copy> --out <tmp.png> --data <dir> --style <mplstyle>
             --meta <meta.json> [--width <inches>]

in the user's chosen interpreter, so it uses the standard library only and must work on any Python 3.8+.
The script receives ``DATA_DIR`` (a Path), ``STYLE`` (a str path), ``OUT`` (a Path) and ``WIDTH`` (inches) as
globals; if it defines ``make_figure(data_dir, style, out)`` that function is called after it has run. It must
write one PNG to ``OUT``. matplotlib is optional here: when present it is switched to the Agg backend and the
shared figure style is applied before the script runs.

Exit codes: 0 done, 1 the script failed, 2 bad arguments, 3 matplotlib is missing.
"""

import argparse
import json
import os
import pathlib
import runpy
import sys
import traceback


def _packages():
    """Versions of the third-party packages the script actually imported (plus the usual three)."""
    out = {}
    try:
        from importlib import metadata
    except ImportError:
        return out
    try:
        dists = metadata.packages_distributions()
        stdlib = getattr(sys, "stdlib_module_names", ())
        for name in sorted({m.split(".")[0] for m in list(sys.modules)}):
            if name.startswith("_") or name in stdlib or name == "chisel_runner":
                continue
            for dist in dists.get(name, []):
                try:
                    out[dist] = metadata.version(dist)
                except Exception:
                    pass
    except Exception:
        pass
    for dist in ("matplotlib", "numpy", "pandas"):
        if dist not in out:
            try:
                out[dist] = metadata.version(dist)
            except Exception:
                pass
    return dict(sorted(out.items())[:60])


def _write_meta(path):
    data = {"python": sys.version.split()[0], "packages": _packages()}
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh)
    except OSError:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--style", default="")
    ap.add_argument("--meta", required=True)
    ap.add_argument("--width", type=float, default=0.0)
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2
    try:
        import matplotlib
        matplotlib.use("Agg")
        if args.style and os.path.isfile(args.style):
            import matplotlib.style
            matplotlib.style.use(args.style)
        if args.width > 0:
            matplotlib.rcParams["figure.figsize"] = (args.width, round(args.width * 0.62, 3))
    except ImportError:
        pass
    data_dir, out = pathlib.Path(args.data), pathlib.Path(args.out)
    code = 0
    try:
        names = runpy.run_path(
            args.script,
            init_globals={"DATA_DIR": data_dir, "STYLE": args.style, "OUT": out, "WIDTH": args.width},
            run_name="chisel_figure")
        make = names.get("make_figure")
        if callable(make):
            make(data_dir, args.style, out)
    except ModuleNotFoundError as exc:
        if (exc.name or "").split(".")[0] == "matplotlib":
            sys.stderr.write("matplotlib is not installed in this Python.\nInstall it with: "
                             f"{sys.executable} -m pip install matplotlib\n")
            code = 3
        else:
            traceback.print_exc()
            code = 1
    except BaseException:
        traceback.print_exc()
        code = 1
    _write_meta(args.meta)
    return code


if __name__ == "__main__":
    sys.exit(main())
