from pathlib import Path
import json

from calculator import total


def main():
    settings = json.loads((Path(__file__).resolve().parents[1] / "data" / "settings.json").read_text(encoding="utf-8"))
    result = total(values=settings["values"], multiplier=2)
    print(f"Python: {settings['label']} = {result}")


if __name__ == "__main__":
    main()
