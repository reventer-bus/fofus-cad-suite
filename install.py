"""FOFUS CAD Suite installer - one file, all three CAD tools.

Run:  py install.py          (or double-click install.bat)
Detects installed CAD tools, copies the right adapter, prints final steps.
"""
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

APPDATA = os.environ.get("APPDATA") or os.path.expanduser("~/AppData/Roaming")

BLENDED_DIRS = [
    os.path.join(APPDATA, "Blender Foundation", "Blender"),
    os.path.expanduser("~/AppData/Roaming/Blender Foundation/Blender"),
]

FUSION_DIR = os.path.join(APPDATA, "Autodesk", "Autodesk Fusion 360", "API", "AddIns", "FofusCadSuite")

SW_DLL_SRC = os.path.join(HERE, "adapters", "solidworks", "FofusCadSuite.dll")
SW_DLL_HINT = r"C:\Program Files\SOLIDWORKS Corp"


def detect_blender():
    """Return Blender user-addons dirs for installed versions."""
    found = []
    for base in BLENDED_DIRS:
        if not os.path.isdir(base):
            continue
        for ver in sorted(os.listdir(base)):
            addons = os.path.join(base, ver, "scripts", "addons")
            if os.path.isdir(addons) and ver[:2].isdigit():
                found.append(addons)
    return found


def detect_fusion():
    return os.path.isdir(os.path.dirname(FUSION_DIR))


def detect_solidworks():
    for p in (r"C:\Program Files\SOLIDWORKS Corp", r"C:\Program Files (x86)\SOLIDWORKS Corp"):
        if os.path.isdir(p):
            return p
    return None


def main():
    print("FOFUS CAD Suite installer")
    print("=" * 50)
    any_found = False

    bl = detect_blender()
    if bl:
        any_found = True
        src = os.path.join(HERE, "adapters", "blender", "fofus_cad_suite.py")
        for addons in bl:
            shutil.copy2(src, os.path.join(addons, "fofus_cad_suite.py"))
            print("[OK] Blender %s -> addon copied. Finish in Blender:"
                  % os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(addons)))))
            print("       Edit > Preferences > Add-ons > FOFUS CAD Suite (tick it), then Log in.")
    else:
        print("[--] Blender not found (skipped)")

    if detect_fusion():
        any_found = True
        zip_src = os.path.join(HERE, "adapters", "fusion360", "FofusCadSuite-fusion360.zip")
        os.makedirs(FUSION_DIR, exist_ok=True)
        with zipfile.ZipFile(zip_src) as z:
            z.extractall(FUSION_DIR)
        print("[OK] Fusion 360 -> add-in copied to %s" % FUSION_DIR)
        print("     Finish: Utilities > Add-Ins > FofusCadSuite > Run (tick 'Run on startup').")
    else:
        print("[--] Fusion 360 not found (skipped)")

    sw = detect_solidworks()
    if sw:
        any_found = True
        if os.path.isfile(SW_DLL_SRC):
            dest = os.path.join(os.path.expanduser("~"), "FofusCadSuite")
            os.makedirs(dest, exist_ok=True)
            shutil.copy2(SW_DLL_SRC, os.path.join(dest, "FofusCadSuite.dll"))
            print("[OK] SolidWorks -> DLL copied to %s" % dest)
            print("     Finish: open an ADMIN command prompt and run:")
            print('       regasm /codebase "%s\\FofusCadSuite.dll"' % dest)
            print("       Then in SolidWorks: Tools > Add-Ins > FOFUS CAD Suite.")
        else:
            print("[!!] SolidWorks found but DLL not bundled in this zip -")
            print("     build it: see adapters/solidworks/BUILD-SOLIDWORKS.txt")
    else:
        print("[--] SolidWorks not found (skipped)")

    if not any_found:
        print("\nNo CAD tools detected. Install Blender / Fusion 360 / SolidWorks first,")
        print("then re-run this installer. The adapters stay valid either way.")
        return 1
    print("=" * 50)
    print("Next: open your CAD tool > FOFUS panel > Log in with FOFUS.")
    print("Your account, rank and wallet appear inside the tool.")
    return 0


if __name__ == "__main__":
    if sys.version_info < (3, 7):
        print("Python 3.7+ required")
        sys.exit(1)
    try:
        sys.exit(main())
    except Exception as e:
        print("Install error: %s" % e)
        sys.exit(1)