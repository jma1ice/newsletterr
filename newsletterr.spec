# PyInstaller spec for release binaries (onedir mode).
#
# onedir is deliberate: onefile would extract static/ to a temp dir on every
# run, which breaks persistent uploads. In onedir, templates/ and static/
# live under _internal/ next to the executable and app/config.py resolves
# them via sys._MEIPASS (ASSET_ROOT). The database/ and env/ directories are
# created beside the executable at first run (config.ROOT).
#
# Build: pyinstaller newsletterr.spec
# Note: chart images in scheduled emails need playwright browsers on the
# host (playwright install chromium); without them emails send chart-free.

from PyInstaller.utils.hooks import collect_all

datas = [
    ("templates", "templates"),
    ("static", "static"),
    ("VERSION", "."),
]
binaries = []
hiddenimports = []

for pkg in ("playwright", "plex_api_client"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["newsletterr.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tests"],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="newsletterr",
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="newsletterr",
)
