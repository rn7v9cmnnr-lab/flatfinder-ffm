#!/usr/bin/env bash
# flatfinder starten. Einmal ausfuehrbar machen: chmod +x start.sh
# Danach reicht:  ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

MIN="3.11"

# --- passendes Python finden ---------------------------------------------
# Wichtig auf dem Mac: das mitgelieferte "python3" ist oft 3.9 und bringt
# ein pip mit, das moderne pyproject-Projekte nicht installieren kann.
PY=""
for cand in python3.14 python3.13 python3.12 python3.11 python3 python; do
  command -v "$cand" >/dev/null 2>&1 || continue
  if "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
    PY="$cand"; break
  fi
done

if [ -z "$PY" ]; then
  have=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "keins")
  cat >&2 <<EOF

  Es fehlt Python $MIN oder neuer. Gefunden: $have

  Auf dem Mac installierst du es so:

      brew install python@3.12

  Falls Homebrew fehlt, steht die eine Zeile zum Installieren auf
  https://brew.sh — danach dieses Skript einfach nochmal starten.

EOF
  exit 1
fi

echo "==> Python: $("$PY" --version) ($PY)"

# --- venv ------------------------------------------------------------------
# Eine .venv, die von einem frueheren Versuch mit zu altem Python stammt,
# ist unbrauchbar - und der haeufigste Grund, warum es beim zweiten Anlauf
# immer noch nicht laeuft. Deshalb pruefen wir sie, statt sie blind zu
# uebernehmen.
venv_ok() {
  [ -x .venv/bin/python ] || return 1
  ./.venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null
}

if [ -d .venv ] && ! venv_ok; then
  alt=$(./.venv/bin/python --version 2>&1 || echo "defekt")
  echo "==> Vorhandene .venv ist unbrauchbar ($alt), lege sie neu an"
  rm -rf .venv
fi

if [ ! -d .venv ]; then
  echo "==> Lege .venv an"
  "$PY" -m venv .venv
fi

# pip in der venv MUSS aktuell sein, sonst scheitert die Installation unten.
echo "==> Aktualisiere pip"
./.venv/bin/python -m pip install --quiet --upgrade pip setuptools wheel

echo "==> Installiere Abhaengigkeiten"
if ! ./.venv/bin/python -m pip install --quiet -e ".[dev]"; then
  cat >&2 <<EOF

  Die Installation ist fehlgeschlagen. Meistens hilft ein sauberer Neuanfang:

      rm -rf .venv && ./start.sh

  Wenn es danach immer noch klemmt, schick die Ausgabe von:

      ./.venv/bin/python -m pip install -e ".[dev]"

EOF
  exit 1
fi

# --- Konfiguration ---------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> .env aus .env.example angelegt."
  echo "    Suchkriterien stehen dort unter SEARCH_ - kannst du jederzeit aendern."
fi

# --- los -------------------------------------------------------------------
PORT="${PORT:-8000}"

# Belegten Port frueh und verstaendlich melden, statt uvicorn stolpern zu
# lassen - meist laeuft flatfinder schon in einem anderen Fenster.
if ./.venv/bin/python - "$PORT" <<'EOP' 2>/dev/null
import socket, sys
s = socket.socket()
try:
    s.bind(("127.0.0.1", int(sys.argv[1]))); sys.exit(1)
except OSError:
    sys.exit(0)
finally:
    s.close()
EOP
then
  cat >&2 <<EOF

  Port $PORT ist schon belegt - vermutlich laeuft flatfinder bereits
  in einem anderen Terminal-Fenster. Schau mal unter
  http://localhost:$PORT nach.

  Anderer Port:  PORT=8080 ./start.sh

EOF
  exit 1
fi

cat <<EOF

  ────────────────────────────────────────────────
   flatfinder laeuft:  http://localhost:$PORT
   Beenden mit Strg+C. Das Fenster muss offen bleiben.
  ────────────────────────────────────────────────

EOF
exec ./.venv/bin/uvicorn flatfinder.web.app:app --host 127.0.0.1 --port "$PORT"
