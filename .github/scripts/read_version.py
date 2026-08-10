import toml

d = toml.load("pyproject.toml")
v = (d.get("project") or {}).get("version") or (d.get("tool") or {}).get("poetry", {}).get("version")
if not v:
    raise SystemExit("Version not found in pyproject.toml")
with open("version.txt", "w", encoding="utf-8") as f:
    f.write(str(v).strip())
print(v)
