#!/usr/bin/env bash
# Processes the batch files given as arguments (default: every file in queue/)
# that doesn't have a finished report yet.
#
# Batch file format (queue/<batch-name>.txt), one video per line:
#   <url>
#   <url> | <optional note, e.g. platform or why it was picked>
# Blank lines and lines starting with # are ignored.
#
# Output per batch: reports/<batch-name>/
#   <n>/report.md      text report (metadata, transcript, frame list)
#   <n>/frames/*.jpg   still frames from the video
#   index.md           one line per video with status
#   DONE               marker written when the whole batch is finished

set -uo pipefail

WATCH="${WATCH_SCRIPT:-.tools/claude-video/skills/watch/scripts/watch.py}"
MAX_FRAMES="${MAX_FRAMES:-20}"
RESOLUTION="${RESOLUTION:-384}"

cookie_args=()
if [ -n "${COOKIES_FILE:-}" ] && [ -f "$COOKIES_FILE" ]; then
  cookie_args=(--cookies "$COOKIES_FILE")
fi

whisper_args=(--no-whisper)
if [ -n "${GROQ_API_KEY:-}" ]; then
  whisper_args=(--whisper groq)
fi

shopt -s nullglob
if [ "$#" -gt 0 ]; then batch_files=("$@"); else batch_files=(queue/*.txt); fi
for batch_file in "${batch_files[@]}"; do
  [ -f "$batch_file" ] || continue
  batch="$(basename "$batch_file" .txt)"
  out="reports/$batch"
  if [ -f "$out/DONE" ]; then
    continue
  fi
  echo "=== Batch: $batch ==="
  mkdir -p "$out"
  index="$out/index.md"
  printf '# Batch %s\n\n| # | Status | URL | Note |\n|---|---|---|---|\n' "$batch" > "$index"

  n=0
  while IFS= read -r line || [ -n "$line" ]; do
    line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -z "$line" ] && continue
    case "$line" in \#*) continue ;; esac
    url="$(echo "$line" | cut -d'|' -f1 | sed 's/[[:space:]]*$//')"
    note="$(echo "$line" | cut -s -d'|' -f2- | sed 's/^[[:space:]]*//')"
    n=$((n + 1))
    dest="$out/$n"
    mkdir -p "$dest"
    work_parent="$(mktemp -d)"
    echo "--- [$n] $url"

    if timeout 600 python3 -I "$WATCH" "$url" \
        --engine local --detail efficient \
        --max-frames "$MAX_FRAMES" --resolution "$RESOLUTION" \
        --out-dir "$work_parent" \
        "${whisper_args[@]}" "${cookie_args[@]}" \
        < /dev/null > "$dest/report.raw.md" 2> "$dest/log.txt"; then
      status="ok"
    else
      status="failed"
    fi

    work_dir="$(find "$work_parent" -maxdepth 1 -type d -name 'watch-*' | head -n 1)"
    if [ -n "$work_dir" ] && [ -d "$work_dir/frames" ]; then
      mkdir -p "$dest/frames"
      cp "$work_dir"/frames/*.jpg "$dest/frames/" 2>/dev/null || true
    fi
    # Make frame paths repo-relative and drop machine-specific temp paths.
    if [ -n "$work_dir" ]; then
      sed "s#${work_dir}/frames/#reports/${batch}/${n}/frames/#g; s#${work_dir}#(temp)#g" \
        "$dest/report.raw.md" > "$dest/report.md"
    else
      cp "$dest/report.raw.md" "$dest/report.md"
    fi
    rm -f "$dest/report.raw.md"
    if [ "$status" = "ok" ] && [ ! -s "$dest/report.md" ]; then
      status="failed"
    fi
    frames_count="$(ls "$dest/frames" 2>/dev/null | wc -l | tr -d ' ')"
    if [ "$status" = "ok" ] && [ "$frames_count" = "0" ] && ! grep -q '```' "$dest/report.md"; then
      status="failed"
    fi
    if [ "$status" = "failed" ]; then
      tail -n 15 "$dest/log.txt" | sed 's/^/    /'
    fi
    rm -rf "$work_parent"
    printf '| %s | %s | %s | %s |\n' "$n" "$status" "$url" "${note:-}" >> "$index"
  done < "$batch_file"

  date -u +%Y-%m-%dT%H:%M:%SZ > "$out/DONE"
  echo "=== Finished $batch ($n videos) ==="
done
