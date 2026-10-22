"""Apply the reviewed RFID-list play change to the pinned source files.

The CI preparation job commits the resulting source changes before compiling.
This script is idempotent and refuses to patch a different source revision.
"""
import hashlib
import json
from pathlib import Path


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f"Expected exactly one patch anchor: {old[:80]!r}")
    return text.replace(old, new, 1)


def checked_source(path, original_sha, marker):
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8")
    if marker in text:
        return None
    sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if sha != original_sha:
        raise RuntimeError(f"Refusing to patch unexpected source: {path} ({sha})")
    return text


web = checked_source("src/Web.cpp", "9ee3bbe7fe6abb05a4f6325416f8ca752ba71ab6", "static void handlePlayRFIDRequest(")
if web is not None:
    web = replace_once(web, '#include "Rfid.h"', '#include "Queues.h"\n#include "Rfid.h"')
    declaration = 'static void handleDeleteRFIDRequest(AsyncWebServerRequest *request);'
    web = replace_once(web, declaration, declaration + '\nstatic void handlePlayRFIDRequest(AsyncWebServerRequest *request);')
    route = '\t\twServer.on("/rfid", HTTP_DELETE, handleDeleteRFIDRequest);'
    web = replace_once(web, route, route + '\n\t\twServer.on("/rfidplay", HTTP_POST, handlePlayRFIDRequest);')
    handler = '''// Queue a saved card exactly like a reader event; never bypass RFID lookup.
static void handlePlayRFIDRequest(AsyncWebServerRequest *request) {
#if defined(RFID_READER_TYPE_RUNTIME)
	if (!request->hasParam("id")) {
		request->send(400, "text/plain; charset=utf-8", "Missing RFID id");
		return;
	}
	const String id = request->getParam("id")->value();
	char tagId[cardIdStringSize] = {0};
	if (id.length() == 0 || id.length() >= sizeof(tagId)) {
		request->send(400, "text/plain; charset=utf-8", "Invalid RFID id length");
		return;
	}
	for (size_t i = 0; i < id.length(); ++i) {
		if (id[i] < '0' || id[i] > '9') {
			request->send(400, "text/plain; charset=utf-8", "RFID id must contain digits only");
			return;
		}
	}
	if (!gPrefsRfid.isKey(id.c_str())) {
		request->send(404, "text/plain; charset=utf-8", "RFID assignment not found");
		return;
	}
	id.toCharArray(tagId, sizeof(tagId));
	// Zero-initialized, fixed-size queue item; retain leading zeroes in the id.
	if (gRfidCardQueue == nullptr || xQueueSend(gRfidCardQueue, tagId, 0) != pdPASS) {
		request->send(503, "text/plain; charset=utf-8", "RFID queue unavailable or busy");
		return;
	}
	// Acceptance is not a promise that playback has already started.
	request->send(202, "application/json", "{\\"status\\":\\"queued\\"}");
#else
	request->send(501, "text/plain; charset=utf-8", "RFID processing is not enabled in this build");
#endif
}

'''
    web = replace_once(web, '// handle get settings\n', handler + '// handle get settings\n')
    Path("src/Web.cpp").write_text(web, encoding="utf-8")

html = checked_source("html/management.html", "709543b45d4ebfcdd757b73aff6e96c4feb43c27", "async function playRFID(")
if html is not None:
    start = html.index('\t\tasync function rebuildRFIDList() {')
    end = html.index('\t\tasync function deleteRFID(tagId) {', start)
    section = html[start:end]
    anchor = '\t\t\t\tdeleteSpan.classList.add("button-group");'
    buttons = '''				deleteSpan.classList.add("button-group", "d-inline-flex", "gap-2");
				let playButton = document.createElement("button");
				playButton.type = "button";
				playButton.classList.add("btn", "btn-success");
				playButton.title = i18next.t("rfidPlayback.trigger");
				playButton.setAttribute("aria-label", playButton.title + " " + rfid.id);
				let playIcon = document.createElement("i");
				playIcon.classList.add("fa", "fa-play");
				playIcon.setAttribute("aria-hidden", "true");
				playButton.appendChild(playIcon);
				playButton.addEventListener("click", () => playRFID(rfid.id, playButton));
				deleteSpan.appendChild(playButton);'''
    section = replace_once(section, anchor, buttons)
    section = replace_once(section, '\t\t\t\tlet deleteButton = document.createElement("button");', '\t\t\t\tlet deleteButton = document.createElement("button");\n\t\t\t\tdeleteButton.type = "button";')
    html = html[:start] + section + html[end:]
    function = '''		async function playRFID(tagId, button) {
			if (button.disabled) {
				return;
			}
			button.disabled = true;
			const controller = new AbortController();
			const timeout = setTimeout(() => controller.abort(), 15000);
			try {
				const response = await fetch("http://" + host + "/rfidplay?id=" + encodeURIComponent(tagId), {
					method: "POST",
					signal: controller.signal
				});
				// A legacy firmware may return its HTML 404 page with HTTP 200.
				if (response.status !== 202) {
					throw new Error(response.statusText || "HTTP " + response.status);
				}
				toaster.success(i18next.t("rfidPlayback.queued"));
			} catch (error) {
				toaster.error(i18next.t("rfidPlayback.error") + ": " + error.message);
			} finally {
				clearTimeout(timeout);
				button.disabled = false;
			}
		}
'''
    html = replace_once(html, '\t\tasync function deleteRFID(tagId) {', function + '\t\tasync function deleteRFID(tagId) {')
    Path("html/management.html").write_text(html, encoding="utf-8")

translations = {
    "de": {"trigger": "RFID-Karte ausl\u00f6sen", "queued": "RFID-Karte zur Verarbeitung \u00fcbergeben", "error": "RFID-Karte konnte nicht ausgel\u00f6st werden"},
    "en": {"trigger": "Trigger RFID card", "queued": "RFID card queued for processing", "error": "Could not trigger RFID card"},
    "fr": {"trigger": "D\u00e9clencher la carte RFID", "queued": "Carte RFID transmise pour traitement", "error": "Impossible de d\u00e9clencher la carte RFID"},
}
for language, labels in translations.items():
    path = Path(f"html/locales/{language}.json")
    text = path.read_text(encoding="utf-8")
    if "rfidPlayback" not in json.loads(text):
        addition = json.dumps(labels, ensure_ascii=False, indent=4).replace("\n", "\n    ")
        text = text[:text.rfind("}")].rstrip() + ',\n    "rfidPlayback": ' + addition + '\n}\n'
        json.loads(text)
        path.write_text(text, encoding="utf-8")

api = Path("REST-API.yaml")
text = api.read_text(encoding="utf-8")
if "  /rfidplay:\n" not in text:
    endpoint = '''  /rfidplay:
    post:
      summary: Trigger a saved RFID card without placing it on the reader.
      description: >-
        Enqueues the card ID for the normal RFID lookup handler. Saved playback
        mode, audiobook position, modification commands and duplicate-card
        settings are preserved. Does not emulate physical card removal.
        A 202 response confirms queue acceptance, not successful playback.
      parameters:
        - in: query
          name: id
          required: true
          schema:
            type: string
            minLength: 1
            maxLength: 12
            pattern: '^[0-9]+$'
          description: Saved RFID ID as a string; leading zeroes are significant.
      responses:
        "202":
          description: Card queued for processing.
        "400":
          description: Missing or invalid card ID.
        "404":
          description: Card assignment not found.
        "501":
          description: Firmware compiled without RFID processing.
        "503":
          description: RFID queue unavailable or full. No event was queued.
'''
    text = replace_once(text, "  /rfid/ids-only:\n", endpoint + "  /rfid/ids-only:\n")
    api.write_text(text, encoding="utf-8")
print("RFID-list play source is ready.")
