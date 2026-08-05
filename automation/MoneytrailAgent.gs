/**
 * MoneytrailAgent.gs
 * -------------------
 * Watches this Gmail account for incoming emails with the subject
 * "Moneytrail Details" and an .xlsx attachment. For each one found:
 *   1. Sends the attachment to the Money Trail web API for processing.
 *   2. Replies to the sender, in the same thread, with the generated
 *      HTML and PDF attached.
 *   3. Labels the thread so it's never processed twice.
 *
 * Runs entirely inside Google's infrastructure via a time-driven
 * trigger -- no separate hosting, no OAuth setup, no credentials to
 * manage. The only external call this script makes is to your own
 * deployed web API (see ../webapi/README.md).
 *
 * ---------------------------------------------------------------
 * SETUP (do this once)
 * ---------------------------------------------------------------
 * 1. Go to https://script.google.com -> New project.
 * 2. Delete the default empty function, paste this whole file in.
 * 3. Edit the three CONFIG values right below this comment.
 * 4. Select `setup` from the function dropdown at the top and click
 *    Run. The first run will prompt you to authorize the script
 *    (it needs Gmail read/send access, which is exactly what it's
 *    for) -- approve it. This creates the Gmail label used for
 *    tracking and installs the recurring trigger.
 * 5. Done. Send yourself a test email with subject "Moneytrail
 *    Details" and an .xlsx attached, then either wait up to 5
 *    minutes or run `checkForMoneytrailEmails` manually from the
 *    dropdown to process it immediately.
 * ---------------------------------------------------------------
 */

// ============================== CONFIG ==============================

// The URL you got from deploying webapi/ on Render (see ../webapi/README.md).
// No trailing slash.
const RENDER_API_URL = 'https://YOUR-APP.onrender.com';

// Exact subject line to watch for.
const SUBJECT_FILTER = 'Moneytrail Details';

// Gmail label used to mark threads that have already been handled, so
// they're never processed (or replied to) twice. Created automatically
// by setup() if it doesn't already exist.
const PROCESSED_LABEL_NAME = 'Moneytrail/Processed';

// Label applied instead, if a thread fails repeatedly (see MAX_RETRIES
// below), so it stops being retried forever and is easy to find later.
const FAILED_LABEL_NAME = 'Moneytrail/Failed';

// How many consecutive failed attempts (across trigger runs) before a
// thread is given up on and flagged instead of retried again. At a
// 5-minute trigger interval, 6 attempts is ~30 minutes of retrying.
const MAX_RETRIES = 6;

// Where to send an alert if a thread ends up in the Failed state.
// Defaults to whoever owns this Gmail account/script.
const ADMIN_EMAIL = Session.getActiveUser().getEmail();

// Only look at threads received within this many days, so a first-ever
// run (or a script that was paused for a while) doesn't suddenly try
// to bulk-process a large backlog of old, unrelated matching threads.
const ONLY_NEWER_THAN_DAYS = 2;

// =====================================================================


/**
 * Run this once, manually, from the Apps Script editor to finish setup.
 */
function setup() {
  getOrCreateLabel_(PROCESSED_LABEL_NAME);
  getOrCreateLabel_(FAILED_LABEL_NAME);
  installTrigger();
  Logger.log('Setup complete. Labels created and trigger installed.');
  Logger.log('Processed label: ' + PROCESSED_LABEL_NAME);
  Logger.log('Failed label: ' + FAILED_LABEL_NAME);
  Logger.log('Admin alerts go to: ' + ADMIN_EMAIL);
}


/**
 * Installs the recurring trigger. Safe to run more than once -- it
 * removes any existing trigger for this function first, so you never
 * end up with duplicates running in parallel.
 */
function installTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'checkForMoneytrailEmails') {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger('checkForMoneytrailEmails')
    .timeBased()
    .everyMinutes(5)
    .create();
  Logger.log('Trigger installed: checkForMoneytrailEmails every 5 minutes.');
}


/**
 * Main entry point, called by the time-driven trigger. Also safe to
 * run manually from the editor for testing.
 */
function checkForMoneytrailEmails() {
  const processedLabel = getOrCreateLabel_(PROCESSED_LABEL_NAME);
  const failedLabel = getOrCreateLabel_(FAILED_LABEL_NAME);

  const query = [
    'subject:"' + SUBJECT_FILTER + '"',
    'has:attachment',
    'filename:xlsx',
    'newer_than:' + ONLY_NEWER_THAN_DAYS + 'd',
    '-label:' + labelSearchToken_(PROCESSED_LABEL_NAME),
    '-label:' + labelSearchToken_(FAILED_LABEL_NAME),
  ].join(' ');

  const threads = GmailApp.search(query, 0, 20);
  if (threads.length === 0) {
    return; // nothing to do -- this is the common case on most runs
  }

  threads.forEach(function (thread) {
    try {
      handleThread_(thread, processedLabel, failedLabel);
    } catch (err) {
      Logger.log('Unexpected error on thread "' + thread.getFirstMessageSubject() + '": ' + err);
      recordFailureAndMaybeGiveUp_(thread, failedLabel, String(err));
    }
  });
}


function handleThread_(thread, processedLabel, failedLabel) {
  const messages = thread.getMessages();
  const target = findMessageWithXlsx_(messages);
  if (!target) {
    // Matched the search but no xlsx actually attached to any message
    // (e.g. filename search matched something odd) -- ignore silently.
    thread.addLabel(processedLabel);
    return;
  }
  const message = target.message;
  const attachment = target.attachment;

  const response = UrlFetchApp.fetch(RENDER_API_URL + '/process', {
    method: 'post',
    payload: { file: attachment.copyBlob() },
    muteHttpExceptions: true,
    // Render free tier can take up to ~60s to wake from sleep on the
    // first request in a while; give this real room.
    // (Apps Script's UrlFetchApp does not expose a configurable
    // timeout -- it uses a generous built-in one, which is fine here.)
  });

  const code = response.getResponseCode();

  if (code === 200) {
    const result = JSON.parse(response.getContentText());
    const htmlBlob = Utilities.newBlob(
      Utilities.base64Decode(result.html_base64), 'text/html', result.html_filename);
    const pdfBlob = Utilities.newBlob(
      Utilities.base64Decode(result.pdf_base64), 'application/pdf', result.pdf_filename);

    message.reply(
      'Hi,\n\n' +
      'Your Money Trail report has been generated from the attached workbook. ' +
      'Please find the interactive HTML flowchart and the single-sheet PDF attached to this email.\n\n' +
      'This is an automated response.',
      { attachments: [htmlBlob, pdfBlob] }
    );
    thread.addLabel(processedLabel);
    clearFailureCount_(thread);
    return;
  }

  if (code >= 400 && code < 500) {
    // Not a transient problem -- the workbook itself was rejected
    // (wrong format, missing required sheet, etc). Tell the sender
    // and stop retrying; retrying won't fix a bad file.
    let message_text = 'Could not process the attached file.';
    try {
      const errBody = JSON.parse(response.getContentText());
      if (errBody && errBody.message) message_text = errBody.message;
    } catch (e) { /* fall back to the generic message above */ }

    message.reply(
      'Hi,\n\n' +
      "We couldn't generate a Money Trail report from the attached file:\n\n" +
      message_text + '\n\n' +
      'Please check the file and resend if needed.\n\n' +
      'This is an automated response.'
    );
    thread.addLabel(processedLabel);
    clearFailureCount_(thread);
    return;
  }

  // 5xx or unexpected response -- treat as transient, retry on the
  // next trigger run rather than replying with an error immediately.
  Logger.log('Transient failure (HTTP ' + code + ') processing thread: ' + thread.getFirstMessageSubject());
  recordFailureAndMaybeGiveUp_(thread, failedLabel, 'HTTP ' + code + ': ' + response.getContentText());
}


function findMessageWithXlsx_(messages) {
  for (let i = messages.length - 1; i >= 0; i--) { // most recent first
    const atts = messages[i].getAttachments();
    for (let j = 0; j < atts.length; j++) {
      if (atts[j].getName().toLowerCase().endsWith('.xlsx')) {
        return { message: messages[i], attachment: atts[j] };
      }
    }
  }
  return null;
}


// ---------------------------- helpers ----------------------------

function getOrCreateLabel_(name) {
  return GmailApp.getUserLabelByName(name) || GmailApp.createLabel(name);
}

// Gmail search syntax needs a label's path quoted/escaped a certain
// way when it contains a slash; wrapping in quotes handles that.
function labelSearchToken_(name) {
  return '"' + name + '"';
}

function failureKey_(thread) {
  return 'fail_count_' + thread.getId();
}

function recordFailureAndMaybeGiveUp_(thread, failedLabel, detail) {
  const props = PropertiesService.getScriptProperties();
  const key = failureKey_(thread);
  const count = (parseInt(props.getProperty(key), 10) || 0) + 1;
  props.setProperty(key, String(count));

  if (count >= MAX_RETRIES) {
    thread.addLabel(failedLabel);
    props.deleteProperty(key);
    MailApp.sendEmail(
      ADMIN_EMAIL,
      'Moneytrail agent: a request failed repeatedly',
      'The Moneytrail agent could not process this thread after ' + MAX_RETRIES + ' attempts:\n\n' +
      'Subject: ' + thread.getFirstMessageSubject() + '\n' +
      'Last error: ' + detail + '\n\n' +
      'It has been labeled "' + FAILED_LABEL_NAME + '" and will not be retried automatically. ' +
      'Check that the web API is deployed and reachable at ' + RENDER_API_URL + ', then remove the label to retry.'
    );
  }
}

function clearFailureCount_(thread) {
  PropertiesService.getScriptProperties().deleteProperty(failureKey_(thread));
}
