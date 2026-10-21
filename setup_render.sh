#!/bin/bash
# Puts materials-bot on Render (free), with the user list on Neon (free).
# Run from this folder:   bash setup_render.sh
# Safe to run again: steps already done are skipped.
set -e
cd "$(dirname "$0")"

say() { printf "\n\033[1;32m== %s\033[0m\n" "$1"; }
fail() { printf "\n\033[1;31m!! %s\033[0m\n" "$1"; exit 1; }

# ---------------------------------------------------------------- tools
say "1/5  Checking tools"
command -v brew >/dev/null || fail "Homebrew is missing. Install it from https://brew.sh, then run this again."
command -v git >/dev/null || fail "git is missing. Run: xcode-select --install"
command -v gh >/dev/null || brew install gh
command -v python3 >/dev/null || fail "python3 is missing."
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q asyncpg==0.30.0
fi
echo "OK"

# ---------------------------------------------------------------- GitHub
say "2/5  GitHub (private copy of the code)"
gh auth status >/dev/null 2>&1 || gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
GH_USER=$(gh api user -q .login)

cat > .gitignore <<'EOF'
__pycache__/
.env
neon_url.txt
render_url.txt
users-*.json
.venv/
EOF

if [ ! -d .git ]; then
  git init -q -b main
fi
git config user.name >/dev/null || git config user.name "$GH_USER"
git config user.email >/dev/null || git config user.email "$GH_USER@users.noreply.github.com"
git add -A
git commit -q -m "materials-bot" || true

if gh repo view "$GH_USER/materials-bot" >/dev/null 2>&1; then
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$GH_USER/materials-bot.git"
  git push -q -u origin main
else
  gh repo create materials-bot --private --source=. --push
fi
REPO_URL="https://github.com/$GH_USER/materials-bot"
echo "Code is at $REPO_URL"

# ---------------------------------------------------------------- Neon
say "3/5  Neon (free database for the user list)"
if [ ! -s neon_url.txt ]; then
  echo "In the browser that opens, click 'Create new API key', name it materials-bot, copy it."
  open "https://console.neon.tech/app/settings/api-keys" 2>/dev/null || true
  printf "Paste the Neon API key here (hidden), then Enter: "
  read -s NEON_KEY; echo
  NH=(-H "Authorization: Bearer $NEON_KEY" -H "Accept: application/json" -H "Content-Type: application/json")
  ORG_ID=$(curl -sS "${NH[@]}" https://console.neon.tech/api/v2/users/me/organizations \
    | python3 -c "import json,sys;d=json.load(sys.stdin).get('organizations',[]);print(d[0]['id'] if d else '')" 2>/dev/null || true)
  export ORG_ID
  BODY=$(python3 -c "import json,os;p={'name':'materials-bot','region_id':'aws-eu-central-1'};o=os.environ.get('ORG_ID');o and p.update(org_id=o);print(json.dumps({'project':p}))")
  curl -sS "${NH[@]}" -X POST https://console.neon.tech/api/v2/projects --data "$BODY" > .neon.json
  python3 -c "import json;print(json.load(open('.neon.json'))['connection_uris'][0]['connection_uri'])" > neon_url.txt 2>/dev/null \
    || { cat .neon.json; echo; rm -f .neon.json neon_url.txt; fail "Neon refused (see message above). Send it to Claude."; }
  rm -f .neon.json
fi
grep -q '^postgres' neon_url.txt || { rm -f neon_url.txt; fail "Could not get the Neon link. Run the script again."; }
echo "Database ready (link saved in neon_url.txt — keep it private)"

# ---------------------------------------------------------------- Render
say "4/5  Render (free hosting)"
echo "In the browser that opens:"
echo "  a) Sign up / log in with GitHub, and allow Render to see the materials-bot repo"
echo "  b) Click 'Create API Key', name it materials-bot, copy it"
open "https://dashboard.render.com/u/settings#api-keys" 2>/dev/null || true
printf "Paste the Render API key here (it stays hidden), then Enter: "
read -s RENDER_KEY; echo
printf "Paste the bot token from BotFather (hidden), then Enter: "
read -s BOT_TOKEN; echo
printf "Choose an admin panel password (hidden), then Enter: "
read -s ADMIN_PASSWORD; echo

api() {  # api METHOD PATH [BODY_FILE]
  if [ -n "$3" ]; then
    curl -sS -X "$1" "https://api.render.com/v1$2" -H "Authorization: Bearer $RENDER_KEY" \
      -H "Accept: application/json" -H "Content-Type: application/json" --data @"$3"
  else
    curl -sS -X "$1" "https://api.render.com/v1$2" -H "Authorization: Bearer $RENDER_KEY" \
      -H "Accept: application/json"
  fi
}

OWNER_ID=$(api GET "/owners?limit=20" | python3 -c "import json,sys;print(json.load(sys.stdin)[0]['owner']['id'])") \
  || fail "Render did not accept the API key. Run this again and paste it carefully."

api GET "/services?name=materials-bot&limit=20" > .render.json
if python3 -c "import json;d=json.load(open('.render.json'));exit(0 if isinstance(d,list) and d else 1)"; then
  echo "Service already exists — skipping create."
  python3 -c "import json;print(json.dumps(json.load(open('.render.json'))[0]['service']))" > .svc.json
else
  export OWNER_ID BOT_TOKEN ADMIN_PASSWORD REPO_URL
  python3 - > .body.json <<'EOF'
import json, os
env = {
    "BOT_TOKEN": os.environ["BOT_TOKEN"],
    "DATABASE_URL": open("neon_url.txt").read().strip(),
    "ADMIN_TELEGRAM_IDS": "8233724149",
    "ADMIN_USERNAME": "baxti",
    "ADMIN_PASSWORD": os.environ["ADMIN_PASSWORD"],
    "PYTHON_VERSION": "3.12.7",
}
print(json.dumps({
    "type": "web_service",
    "name": "materials-bot",
    "ownerId": os.environ["OWNER_ID"],
    "repo": os.environ["REPO_URL"],
    "branch": "main",
    "autoDeploy": "yes",
    "envVars": [{"key": k, "value": v} for k, v in env.items()],
    "serviceDetails": {
        "runtime": "python",
        "plan": "free",
        "region": "frankfurt",
        "envSpecificDetails": {
            "buildCommand": "pip install -r requirements.txt",
            "startCommand": "uvicorn render_app:app --host 0.0.0.0 --port $PORT",
        },
    },
}))
EOF
  api POST /services .body.json > .res.json
  rm -f .body.json
  python3 -c "import json;d=json.load(open('.res.json'));print(json.dumps(d['service']))" > .svc.json 2>/dev/null \
    || { cat .res.json; rm -f .res.json .render.json; echo; echo "If it mentions the repo: open https://dashboard.render.com/web/new , click 'Configure GitHub',"; echo "give Render access to materials-bot (don't create anything there), then run this script again."; fail "Render refused (see message above). Send it to Claude if it's something else."; }
  rm -f .res.json
fi
rm -f .render.json
python3 - <<'EOF'
import json
s = json.load(open(".svc.json"))
url = s.get("serviceDetails", {}).get("url", "")
dash = s.get("dashboardUrl", "")
open("render_url.txt", "w").write(url + "\n" + dash + "\n")
print("Admin panel:", url)
print("Render page:", dash)
EOF
rm -f .svc.json

# ---------------------------------------------------------------- done
say "5/5  Done"
echo "Render is now building the bot (takes about 3-5 minutes)."
echo "Watch it on the Render page above. When it says 'Live', press /start in your bot."
echo "Admin panel login: baxti + the password you chose."
echo
echo "Save a copy of the user list to your Mac any time:"
echo "   .venv/bin/python backup.py save"
