from __future__ import annotations

import json
from pathlib import Path

import uiautomator2


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "auto_py_to_exe_config.json"


def main() -> None:
    u2_assets = Path(uiautomator2.__file__).resolve().parent / "assets"
    if not (u2_assets / "u2.jar").exists():
        raise FileNotFoundError(f"uiautomator2 u2.jar not found at: {u2_assets / 'u2.jar'}")

    config = {
        "version": "auto-py-to-exe-configuration_v1",
        "pyinstallerOptions": [
            {"optionDest": "noconfirm", "value": True},
            {"optionDest": "filenames", "value": str(ROOT / "Alp_Automation.py")},
            {"optionDest": "onefile", "value": False},
            {"optionDest": "console", "value": False},
            {"optionDest": "name", "value": "ALP-Automation"},
            {"optionDest": "clean_build", "value": True},
            {"optionDest": "collect_all", "value": "uiautomator2"},
            {"optionDest": "datas", "value": f"{ROOT / 'assets'};assets"},
            {"optionDest": "datas", "value": f"{u2_assets};uiautomator2\\assets"},
        ],
        "nonPyinstallerOptions": {
            "increaseRecursionLimit": True,
            "manualArguments": "",
            "outputDirectory": str(ROOT / "output"),
        },
    }

    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"Wrote {CONFIG_PATH}")
    print("Open auto-py-to-exe with:")
    print(f'python -m auto_py_to_exe -c "{CONFIG_PATH}"')


if __name__ == "__main__":
    main()
