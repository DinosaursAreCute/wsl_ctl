import toml, os, re

kind = os.environ["KIND"]
path = "pyproject.toml"

data = toml.load(path)

version = None
loc = None
if "project" in data and "version" in data["project"]:
    version = data["project"]["version"]
    loc = ("project", "version")
elif "tool" in data and "poetry" in data["tool"] and "version" in data["tool"]["poetry"]:
    version = data["tool"]["poetry"]["version"]
    loc = ("tool", "poetry", "version")
else:
    raise SystemExit("Could not find version in pyproject.toml")

m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", str(version).strip())
if not m:
    raise SystemExit(f"Unsupported version format: {version} (expected x.y.z)")

major, minor, patch = map(int, m.groups())

if kind == "patch":
    patch += 1
elif kind == "minor":
    minor += 1
    patch = 0
elif kind == "major":
    major += 1
    minor = 0
    patch = 0
else:
    raise SystemExit(f"Unsupported bump type: {kind}")

newv = f"{major}.{minor}.{patch}"

if loc == ("project", "version"):
    data["project"]["version"] = newv
elif loc == ("tool", "poetry", "version"):
    data["tool"]["poetry"]["version"] = newv

with open(path, "w", encoding="utf-8") as f:
    toml.dump(data, f)

print(newv)
