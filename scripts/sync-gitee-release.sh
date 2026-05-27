#!/usr/bin/env bash
# Sync release assets to a Gitee Release (API v5).
# Env: GITEE_TOKEN, GITEE_REPO (owner/repo), TAG, GITEE_ASSETS_DIR
# Optional: GITEE_TARGET_COMMITISH (branch/sha when tag not yet synced)
set -euo pipefail

if [[ -z "${GITEE_TOKEN:-}" ]]; then
  echo "::notice::GITEE_TOKEN not set — skipping Gitee release sync."
  exit 0
fi
if [[ -z "${GITEE_REPO:-}" || "${GITEE_REPO}" != */* ]]; then
  echo "::error::GITEE_REPO must be set as 'owner/repo'."
  exit 1
fi
if [[ ! -d "${GITEE_ASSETS_DIR:-}" ]]; then
  echo "::error::GITEE_ASSETS_DIR is not a directory: ${GITEE_ASSETS_DIR:-}"
  exit 1
fi

OWNER="${GITEE_REPO%%/*}"
REPO="${GITEE_REPO#*/}"

enc() { python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1],safe=''))" "$1"; }

# Write token to temp curl config (keeps it out of process list)
tmp_cfg="$(umask 077; mktemp)"
tmp_get="$(mktemp)"; tmp_create="$(mktemp)"
tmp_list="$(mktemp)"; tmp_del="$(mktemp)"; tmp_up="$(mktemp)"
trap 'rm -f "$tmp_cfg" "$tmp_get" "$tmp_create" "$tmp_list" "$tmp_del" "$tmp_up"' EXIT
printf 'header = "Authorization: token %s"\n' "$GITEE_TOKEN" > "$tmp_cfg"

API="https://gitee.com/api/v5"
gcurl() { curl -sS -K "$tmp_cfg" "$@"; }

ENC_OWNER="$(enc "$OWNER")"; ENC_REPO="$(enc "$REPO")"; ENC_TAG="$(enc "$TAG")"

# 1. Find or create Release
HTTP="$(gcurl -o "$tmp_get" -w "%{http_code}" "$API/repos/$ENC_OWNER/$ENC_REPO/releases/tags/$ENC_TAG")"
if [[ "$HTTP" == "200" ]]; then
  RELEASE_ID="$(jq -r '.id // empty' "$tmp_get")"
  [[ -z "$RELEASE_ID" || "$RELEASE_ID" == "null" ]] && HTTP="404"
fi

if [[ "$HTTP" == "404" ]]; then
  TGT="${GITEE_TARGET_COMMITISH:-$TAG}"
  CREATE_HTTP="$(
    jq -n --arg tag "$TAG" --arg name "$TAG" \
       --arg body "Automated sync from GitHub Actions." --arg tc "$TGT" \
       '{tag_name:$tag,name:$name,body:$body,target_commitish:$tc,prerelease:false}' \
    | gcurl -o "$tmp_create" -w "%{http_code}" \
        -X POST "$API/repos/$ENC_OWNER/$ENC_REPO/releases" \
        -H "Content-Type: application/json" -d @-
  )"
  if [[ "$CREATE_HTTP" != "201" && "$CREATE_HTTP" != "200" ]]; then
    echo "::error::Create Gitee release failed: HTTP $CREATE_HTTP"
    cat "$tmp_create"; exit 1
  fi
  RELEASE_ID="$(jq -r '.id // empty' "$tmp_create")"
elif [[ "$HTTP" != "200" ]]; then
  echo "::error::GET Gitee release failed: HTTP $HTTP"; cat "$tmp_get"; exit 1
fi
echo "Gitee release id=$RELEASE_ID for tag=$TAG"

# 2. Delete existing assets
ATTACH_URL="$API/repos/$ENC_OWNER/$ENC_REPO/releases/$RELEASE_ID/attach_files"
LIST_HTTP="$(gcurl -o "$tmp_list" -w "%{http_code}" "$ATTACH_URL")"
if [[ "$LIST_HTTP" != "200" ]]; then
  echo "::error::List attachments failed: HTTP $LIST_HTTP"; cat "$tmp_list"; exit 1
fi
while IFS= read -r aid; do
  [[ -n "$aid" && "$aid" != "null" ]] || continue
  DEL_HTTP="$(gcurl -o "$tmp_del" -w "%{http_code}" -X DELETE "$ATTACH_URL/$aid")"
  [[ "$DEL_HTTP" == "200" || "$DEL_HTTP" == "204" ]] || echo "::warning::Delete attachment $aid failed: $DEL_HTTP"
done < <(jq -r '.[]?.id // empty' "$tmp_list")

# 3. Upload new assets
shopt -s nullglob
for fpath in "$GITEE_ASSETS_DIR"/*; do
  [[ -f "$fpath" ]] || continue
  fname="$(basename "$fpath")"
  echo "Uploading $fname …"
  UP_HTTP="$(gcurl -o "$tmp_up" -w "%{http_code}" -X POST "$ATTACH_URL" -F "file=@$fpath")"
  if [[ "$UP_HTTP" != "201" && "$UP_HTTP" != "200" ]]; then
    echo "::error::Upload $fname failed: HTTP $UP_HTTP"; cat "$tmp_up"; exit 1
  fi
done
echo "Gitee sync done: $OWNER/$REPO @ $TAG"
