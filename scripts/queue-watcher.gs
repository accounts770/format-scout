/**
 * Format Scout queue watcher (Google Apps Script).
 *
 * Runs every minute from a time-driven trigger. When a new file appears in the
 * Drive queue folder, it asks GitHub to start the "Watch queued videos" workflow
 * right away instead of waiting for GitHub's (often delayed) schedule.
 *
 * Setup (script.google.com, signed in as the account that owns the folder):
 *   Project Settings -> Script properties:
 *     FOLDER_ID     = the queue folder's ID
 *     GITHUB_TOKEN  = fine-grained token, only this repo, Contents: Read and write
 *     GITHUB_REPO   = accounts770/format-scout
 *   Triggers -> Add trigger -> checkQueue, time-driven, every minute.
 *
 * The token lives only in this script's properties; it is never in the repo.
 */
function checkQueue() {
  var props = PropertiesService.getScriptProperties();
  var folderId = props.getProperty('FOLDER_ID');
  var token = props.getProperty('GITHUB_TOKEN');
  var repo = props.getProperty('GITHUB_REPO');
  if (!folderId || !token || !repo) {
    throw new Error('Set FOLDER_ID, GITHUB_TOKEN and GITHUB_REPO in Script properties.');
  }

  var seen = JSON.parse(props.getProperty('SEEN') || '{}');
  var files = DriveApp.getFolderById(folderId).getFiles();
  var fresh = [];
  var current = {};
  while (files.hasNext()) {
    var f = files.next();
    current[f.getId()] = true;
    if (!seen[f.getId()]) fresh.push(f.getName());
  }
  if (!fresh.length) {
    // Forget files that have been trashed, so the list stays small.
    props.setProperty('SEEN', JSON.stringify(current));
    return;
  }

  var res = UrlFetchApp.fetch('https://api.github.com/repos/' + repo + '/dispatches', {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: 'Bearer ' + token,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28'
    },
    payload: JSON.stringify({ event_type: 'queue' }),
    muteHttpExceptions: true
  });
  if (res.getResponseCode() !== 204) {
    // Leave SEEN unchanged so the next run tries again.
    throw new Error('GitHub dispatch failed: ' + res.getResponseCode() + ' ' + res.getContentText());
  }
  props.setProperty('SEEN', JSON.stringify(current));
}
