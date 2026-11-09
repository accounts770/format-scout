# format-scout

Watches short-form videos so they can be broken down into reusable formats. Lists of public TikTok, Instagram, and YouTube links come in through a shared queue folder; GitHub downloads each video, pulls still frames and a transcript, and saves the results to `reports/`.

## How it runs

1. A batch file appears in the queue folder (plain text, named like `2026-12-a1b2c3d4-7f3e`, one link per line). Batch names are codes; nothing in this repo names who a batch is for.
2. Every 10 minutes the **Watch queued videos** workflow (`.github/workflows/watch.yml`) checks the folder with `scripts/fetch_drive_queue.py`. Only TikTok, Instagram, and YouTube links are accepted.
3. For each new batch, `scripts/process_queue.sh` runs the `watch` tool from [bradautomates/claude-video](https://github.com/bradautomates/claude-video), pinned to a reviewed commit.
4. Results are committed to `reports/<batch>/`:
   - `<n>/report.md`: title, creator, duration, transcript, and the frame list
   - `<n>/frames/`: up to 20 still frames
   - `<n>/log.txt`: run log (check this when a video fails)
   - `index.md`: ok/failed status for every video in the batch
   - `DONE`: written when the batch is finished
5. Reports older than 60 days are removed automatically.

You can also run it by hand: **Actions → Watch queued videos → Run workflow**.

## Building the doc

`scripts/build_doc.py spec.json` builds the monthly .docx in house style from `template/house-style.docx` (Letter, 1" margins, Roboto Slab 12pt, numbered list), with a **Format Ideas** section of shoot cards at the end. The spec format is documented at the top of the script.

## Secrets (Settings → Secrets and variables → Actions)

Secrets are never shown in the repo or in run logs.

| Secret | Required | What it does |
|---|---|---|
| `QUEUE_FOLDER_ID` | Yes | ID of the shared Drive queue folder. |
| `GROQ_API_KEY` | Recommended | Transcribes speech when a video has no captions. |
| `DRIVE_API_KEY` | Optional | Lists the queue folder through the Drive API instead of Drive's public folder view. Only needed if listing ever stops working. |

## Updating the video tool

`CLAUDE_VIDEO_SHA` in the workflow pins the exact version of the third-party tool. Don't change it until the new version has been reviewed.
