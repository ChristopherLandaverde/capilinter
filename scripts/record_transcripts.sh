#!/usr/bin/env bash
# Record the primary CLI flows into docs/transcripts/.
# Uses whichever `capilinter` is first on PATH (CI puts the installed wheel first).
# Output is deterministic: fixtures use fixed timestamps that are always older than 7 days.
set -uo pipefail
cd "$(dirname "$0")/.."
out=docs/transcripts
mkdir -p "$out"

record() {
  local name=$1; shift
  {
    local shown="" a
    for a in "$@"; do
      if [[ $a == *" "* ]]; then shown+=" \"$a\""; else shown+=" $a"; fi
    done
    echo "\$ capilinter${shown}"
    capilinter "$@" 2>&1
    echo "[exit $?]"
  } > "$out/$name.txt"
}

record 01-inspect-pass   inspect fixtures/valid_payload.json
record 02-inspect-fail   inspect fixtures/unhashed_pii.json
record 03-inspect-strict inspect fixtures/valid_payload.json --strict
record 04-inspect-json   inspect fixtures/missing_event_id.json --json
record 05-hash-email     hash "  John_Smith@gmail.com "
record 06-hash-phone     hash "(650)555-1212" --phone
record 07-hash-dob       hash "2/16/1997" --field db
record 08-hash-refused   hash "United States" --field country
record 09-hash-repair     hash "Jane.Doe@Example.com"
record 10-inspect-repaired inspect fixtures/unhashed_pii_repaired.json
