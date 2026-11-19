#!/usr/bin/env bash
# Run an update command, commit what it changed and push. If someone else pushed in between,
# start again from the latest main and run the command again (so generated files never conflict).
#   pipeline/publish.sh "commit message" command args...
set -u
msg="$1"; shift
git config user.name "nfl-hub-bot"
git config user.email "actions@users.noreply.github.com"
for i in 1 2 3 4; do
  "$@" || exit 1
  git add -A index.html pipeline/
  if git diff --cached --quiet; then echo "No changes"; exit 0; fi
  git commit -q -m "$msg"
  if git push -q origin HEAD:main; then echo "pushed"; exit 0; fi
  echo "push rejected, retrying on the latest main"
  sleep $((i * 5))
  git fetch -q origin main && git reset -q --hard origin/main
done
exit 1
