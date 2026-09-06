/*!
 * ClaimReady companion overlay
 * -----------------------------------------------------------------------
 * A self-contained, drop-in widget: include this one file on any page
 * (<script src="claimready-overlay.js" defer></script>) and it injects its
 * own styles and markup, then floats a launcher button + guide panel on
 * top of the host page. No build step, no external CSS/JS dependencies.
 *
 * Visual language follows DESIGN.md ("Civic Justice Portal"): judicial
 * maroon primary, slate neutrals, Public Sans, soft 4px corners, minimal
 * shadows, ghost-border elevation.
 *
 * This build supports four content modes, and does not expose a
 * tab switcher to the visitor any more:
 *   - "route" — the simplified "Find my route" flow (a single "approximate
 *     my route" option, since every other route option was removed).
 *   - "dashboard" — shown on the mock SCT portal (Page 1.75), right after the
 *     eligibility check. Auto-opens (unlike every other mode, which waits
 *     for the visitor to tap the launcher) since its whole point is to
 *     greet the visitor with their pre-filing assessment ID, an overall
 *     progress meter, and a one-tap "File a Claim" handoff.
 *   - "after" — the "After filing" checklist. Also shows the same progress
 *     meter as "dashboard", one step further along.
 *   - "upload" — an in-widget "add more documents" panel, reached from
 *     Page 2's own "Add more documents" button. It reuses this widget's
 *     existing state.files (attached earlier via "approximate my route"),
 *     so it never resets on entry — see setContext() below.
 * "Form help" is no longer part of this widget: it moved into Page 2's own
 * inline (i) reference icons, built directly into dummy-website.html.
 *
 * Which mode is shown, and whether the widget appears at all, is decided
 * by the host page, not by the visitor: call
 *   window.ClaimReadyOverlay.setContext("route" | "dashboard" | "after" | "upload" | "hidden", data)
 * whenever the host page's own view changes (see dummy-website.html's
 * showPage()). `data` is only used by "dashboard"/"after", to hand over
 * host-page state this widget has no way to know on its own — the pre-filing
 * assessment ID and how far along the overall flow the visitor is
 * ({ assessmentId, progressStep, progressTotal, progressLabel }). This keeps
 * the widget generic/reusable while letting each host page decide what
 * belongs on screen.
 *
 * All interactions below are wired to real, working state – nothing here
 * is a decorative dead end. The "approximate my route" and "add documents"
 * flows call the ClaimReady FastAPI backend on the same origin
 * (POST /api/extract-fields, /api/extract-document) and hand the extracted
 * field_help/documents back to the host page as event payloads.
 * -----------------------------------------------------------------------
 */
(() => {
  "use strict";

  // Guard against double-inclusion on the same page.
  if (window.__claimReadyOverlayLoaded) return;
  window.__claimReadyOverlayLoaded = true;

  /* ---------------------------------------------------------------------
   * Icons – small hand-drawn stroke icons (no external icon font/CDN).
   * ------------------------------------------------------------------- */
  const ICONS = {
    compass:
      '<circle cx="12" cy="12" r="9"/><path d="M14.8 9.2l-1.9 4.7-4.7 1.9 1.9-4.7z"/>',
    chevron:
      '<path d="M9 6l6 6-6 6"/>',
    upload:
      '<path d="M12 3v12"/><path d="M7 8l5-5 5 5"/><rect x="4" y="15" width="16" height="6" rx="1.5"/>',
  };
  function svg(name, size = 18) {
    const body = ICONS[name] || ICONS.chevron;
    return (
      '<svg xmlns="http://www.w3.org/2000/svg" width="' +
      size +
      '" height="' +
      size +
      '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      body +
      "</svg>"
    );
  }

  /* ---------------------------------------------------------------------
   * Styles – scoped to #claimready-widget, tokens mirror DESIGN.md.
   * ------------------------------------------------------------------- */
  const CSS = `
#claimready-widget, #claimready-widget * { box-sizing: border-box; }
#claimready-widget {
  --cr-font: 'Public Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --cr-primary: #8b1d3d;
  --cr-primary-deep: #6b0028;
  --cr-primary-hover: #731631;
  --cr-primary-active: #5c1026;
  --cr-on-primary: #ffffff;
  --cr-primary-tint: #fdf8f9;
  --cr-nav-tint: #f8f1f3;
  --cr-secondary: #4e6073;
  --cr-on-surface: #111c2d;
  --cr-on-surface-variant: #564144;
  --cr-surface: #ffffff;
  --cr-surface-muted: #f0f3ff;
  --cr-surface-container: #e7eeff;
  --cr-outline: #ddbfc3;
  --cr-outline-strong: #8a7174;
  --cr-error: #ba1a1a;
  --cr-error-bg: #ffdad6;
  --cr-on-error-container: #93000a;
  --cr-success: #166534;
  --cr-success-bg: #e3f3e8;
  --cr-radius: 4px;
  --cr-radius-lg: 8px;
  position: fixed;
  inset: auto 20px 20px auto;
  z-index: 2147483000;
  font-family: var(--cr-font);
  color: var(--cr-on-surface);
  -webkit-font-smoothing: antialiased;
}
#claimready-widget button { font: inherit; }
#claimready-widget a { color: var(--cr-primary); }

#cr-launcher {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 18px 12px 14px;
  border: none;
  border-radius: 9999px;
  background: var(--cr-primary);
  color: var(--cr-on-primary);
  font-weight: 600;
  font-size: 14px;
  letter-spacing: 0.01em;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.18);
  transition: background-color 150ms ease, transform 150ms ease;
}
#cr-launcher:hover { background: var(--cr-primary-hover); }
#cr-launcher:active { background: var(--cr-primary-active); transform: scale(0.98); }
#cr-launcher:focus-visible { outline: 2px solid var(--cr-primary-deep); outline-offset: 2px; }
#claimready-widget[data-open="true"] #cr-launcher { display: none; }

#cr-panel {
  display: flex;
  flex-direction: column;
  width: min(400px, calc(100vw - 40px));
  max-height: min(640px, calc(100vh - 40px));
  background: var(--cr-surface);
  border: 1px solid var(--cr-outline);
  border-radius: var(--cr-radius-lg);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.12);
  overflow: hidden;
}
#claimready-widget[data-open="true"] #cr-panel { display: flex; }
#claimready-widget:not([data-open="true"]) #cr-panel { display: none; }

.cr-header {
  flex: none;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 16px 16px 12px;
  border-top: 4px solid var(--cr-primary);
  border-bottom: 1px solid var(--cr-outline);
  background: var(--cr-surface);
}
.cr-brand { display: flex; align-items: center; gap: 8px; font-size: 18px; line-height: 26px; font-weight: 600; color: var(--cr-primary-deep); }
.cr-brand span.cr-brand-sub { display: block; font-size: 12px; line-height: 18px; font-weight: 400; color: var(--cr-on-surface-variant); }
.cr-brand-text { display: flex; flex-direction: column; }
.cr-icon-badge { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 9999px; background: var(--cr-surface-container); color: var(--cr-primary); flex: none; }
/* Header brand mark: the real logo already has its own maroon rounded-square
   background baked in, so it skips the circular tint background above (that
   would double up two clashing shapes/colors) but keeps the same 28x28
   footprint, just with a couple of px of breathing room around the image. */
.cr-icon-badge--logo { background: transparent; }
.cr-icon-badge--logo img { display: block; width: 24px; height: 24px; border-radius: 6px; }
#cr-close {
  flex: none;
  width: 28px; height: 28px;
  display: inline-flex; align-items: center; justify-content: center;
  border: 1px solid var(--cr-outline);
  border-radius: 9999px;
  background: var(--cr-surface);
  color: var(--cr-on-surface-variant);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
}
#cr-close:hover { background: var(--cr-surface-muted); color: var(--cr-on-surface); }
#cr-close:focus-visible { outline: 2px solid var(--cr-primary-deep); outline-offset: 2px; }

.cr-context-label {
  flex: none;
  padding: 8px 16px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--cr-primary);
  background: var(--cr-nav-tint);
  border-bottom: 1px solid var(--cr-outline);
}

.cr-body { flex: 1 1 auto; overflow-y: auto; padding: 16px; font-size: 14px; line-height: 22px; }
.cr-body::-webkit-scrollbar { width: 8px; }
.cr-body::-webkit-scrollbar-thumb { background: var(--cr-outline); border-radius: 9999px; }

.cr-eyebrow { font-size: 11px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; color: var(--cr-secondary); }
.cr-h { font-size: 18px; line-height: 26px; font-weight: 700; color: var(--cr-on-surface); margin: 6px 0 4px; }
.cr-copy { color: var(--cr-on-surface-variant); margin: 0 0 12px; }
.cr-body p { margin: 0 0 12px; }

.cr-choices { display: grid; gap: 8px; margin: 10px 0 14px; }
.cr-choice {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  text-align: left;
  padding: 10px 12px;
  border: 1px solid var(--cr-outline);
  border-radius: var(--cr-radius);
  background: var(--cr-surface);
  color: var(--cr-on-surface);
  cursor: pointer;
}
.cr-choice:hover, .cr-choice:focus-visible { border-color: var(--cr-primary); background: var(--cr-primary-tint); outline: none; }
.cr-choice .cr-icon-badge { background: var(--cr-surface-muted); }
.cr-choice b { display: block; font-size: 13px; font-weight: 600; }
.cr-choice small { display: block; font-size: 12px; color: var(--cr-secondary); margin-top: 2px; }

.cr-note, .cr-warning {
  border-radius: var(--cr-radius);
  padding: 12px 14px;
  margin: 12px 0;
}
.cr-note { background: var(--cr-surface-muted); border-left: 4px solid var(--cr-primary); }
.cr-warning { background: var(--cr-error-bg); color: var(--cr-on-error-container); border-left: 4px solid var(--cr-error); }
.cr-warning strong { display: block; margin-bottom: 4px; }
.cr-note strong { display: block; margin-bottom: 4px; color: var(--cr-on-surface); }

/* "Dashboard"/"after" modes only: pre-filing assessment ID + overall progress meter. */
.cr-id-badge {
  display: flex; flex-direction: column; gap: 2px;
  border: 1px solid var(--cr-outline);
  border-radius: var(--cr-radius);
  background: var(--cr-surface-muted);
  padding: 10px 12px;
  margin: 0 0 14px;
}
.cr-id-badge span { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--cr-secondary); }
.cr-id-badge strong { font-size: 14px; font-family: 'Courier New', monospace; color: var(--cr-on-surface); }

.cr-progress { margin: 0 0 16px; }
.cr-progress-track { height: 8px; border-radius: 9999px; background: var(--cr-surface-container); overflow: hidden; }
.cr-progress-fill { height: 100%; border-radius: 9999px; background: var(--cr-primary); transition: width 200ms ease; }
.cr-progress-label { font-size: 12px; color: var(--cr-secondary); margin: 6px 0 0; }

.cr-field { display: block; margin: 6px 0 12px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.02em; color: var(--cr-on-surface-variant); }
.cr-field input, .cr-field textarea {
  display: block; width: 100%; margin-top: 6px;
  padding: 10px 12px;
  border: 1px solid var(--cr-outline-strong);
  border-radius: var(--cr-radius);
  background: var(--cr-surface-muted);
  color: var(--cr-on-surface);
  font-size: 14px; font-weight: 400; text-transform: none; letter-spacing: normal;
  font-family: var(--cr-font);
}
.cr-field input { height: 40px; }
.cr-field textarea { resize: vertical; }

.cr-upload-row { display: flex; margin: 4px 0 8px; }
.cr-upload-row .cr-btn { width: auto; margin: 0; }

details { border-top: 1px solid var(--cr-outline); padding: 10px 0; font-size: 13px; }
summary { cursor: pointer; color: var(--cr-primary); font-weight: 600; }
summary:hover { text-decoration: underline; }
details p { margin: 8px 0 0; color: var(--cr-on-surface-variant); }

.cr-link { color: var(--cr-primary); text-decoration: underline; text-underline-offset: 3px; font-weight: 600; }
.cr-link:hover { color: var(--cr-primary-hover); }

.cr-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  width: 100%;
  min-height: 40px;
  padding: 10px 20px;
  border-radius: var(--cr-radius);
  border: 1px solid var(--cr-outline);
  background: var(--cr-surface);
  color: var(--cr-on-surface);
  font-size: 14px; font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  margin: 4px 0;
}
.cr-btn:hover { background: var(--cr-surface-muted); }
.cr-btn:disabled { opacity: 0.6; cursor: not-allowed; }
/* ID + two classes beats the plain "#claimready-widget a" color rule above
   (equal ID count, more classes wins), so primary button text stays white
   instead of inheriting the maroon link color. */
#claimready-widget .cr-btn.cr-primary { border-color: transparent; background: var(--cr-primary); color: var(--cr-on-primary); }
#claimready-widget .cr-btn.cr-primary:hover { background: var(--cr-primary-hover); }
#claimready-widget .cr-btn.cr-primary:active { background: var(--cr-primary-active); }

.cr-back {
  border: none; background: transparent; color: var(--cr-secondary);
  text-decoration: underline; text-underline-offset: 3px;
  padding: 8px 0; margin-top: 6px; cursor: pointer; font-size: 13px;
}
.cr-back:hover { color: var(--cr-on-surface); }

.cr-check { display: flex; gap: 10px; align-items: flex-start; padding: 10px 0; border-bottom: 1px solid var(--cr-outline); font-size: 14px; }
.cr-check:last-of-type { border-bottom: none; }
.cr-check input { width: 18px; height: 18px; flex: none; margin: 2px 0; accent-color: var(--cr-primary); }

.cr-list { list-style: none; padding: 0; margin: 0 0 12px; color: var(--cr-on-surface-variant); }
.cr-list li {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 6px 0; border-bottom: 1px solid var(--cr-outline);
}
.cr-list li:last-child { border-bottom: none; }
.cr-list li span { overflow-wrap: anywhere; }
.cr-file-remove {
  flex: none; border: none; background: transparent; color: var(--cr-on-surface-variant);
  width: 22px; height: 22px; border-radius: 50%; font-size: 16px; line-height: 1; cursor: pointer;
}
.cr-file-remove:hover { background: var(--cr-error-bg); color: var(--cr-error); }
.cr-file-remove:focus-visible { outline: 2px solid var(--cr-primary-deep); outline-offset: 2px; }

.cr-status { font-size: 12px; color: var(--cr-secondary); margin-top: 8px; }

.cr-footer {
  flex: none;
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 10px 16px;
  border-top: 1px solid var(--cr-outline);
  background: var(--cr-surface-muted);
  font-size: 11px; color: var(--cr-secondary);
}
.cr-footer button { border: none; background: transparent; color: var(--cr-primary); font-weight: 600; cursor: pointer; font-size: 11px; text-decoration: underline; text-underline-offset: 2px; }

@media (max-width: 480px) {
  #claimready-widget { inset: auto 0 0 0; }
  #cr-launcher { border-radius: 0; width: 100%; justify-content: center; }
  #cr-panel { width: 100%; max-height: 85vh; border-radius: var(--cr-radius-lg) var(--cr-radius-lg) 0 0; }
}
`;

  /* ---------------------------------------------------------------------
   * Markup
   * ------------------------------------------------------------------- */
  const HTML = `
<button type="button" id="cr-launcher" aria-haspopup="dialog" aria-expanded="false" aria-controls="cr-panel">
  ${svg("compass", 18)}
  <span>ClaimReady guide</span>
</button>
<section id="cr-panel" role="dialog" aria-modal="false" aria-label="ClaimReady independent filing guide">
  <div class="cr-header">
    <div class="cr-brand">
      <span class="cr-icon-badge cr-icon-badge--logo"><img src="assets/images/claimready-icon-mark.svg" alt="ClaimReady logo" width="24" height="24"></span>
      <span class="cr-brand-text">ClaimReady<span class="cr-brand-sub">Independent preparation guide</span></span>
    </div>
    <button type="button" id="cr-close" aria-label="Minimise guide">&#8722;</button>
  </div>
  <div class="cr-context-label" id="cr-context-label">Find my route</div>
  <div class="cr-body" id="cr-screen" aria-live="polite"></div>
  <div class="cr-footer">
    <span>Guidance, not a court decision.</span>
    <button type="button" id="cr-reset">Start over</button>
  </div>
</section>
`;

  /* ---------------------------------------------------------------------
   * Reference links (illustrative, point at the real public guidance).
   * ------------------------------------------------------------------- */
  const sources = {
    eligibility: "https://www.judiciary.gov.sg/civil/cases-eligible-small-claim",
    filing: "https://www.judiciary.gov.sg/civil/how-to-file-serve-small-claim",
  };

  function defaultState() {
    return {
      mode: "route", // "route" | "dashboard" | "after" | "upload" — set by the host page via setContext(), not user-switchable
      step: "start", // route: "start" -> "approximate"
      incidentText: "",
      files: [], // [{id, name, file}] — real File objects picked from <input type="file">
      approxStatus: "idle", // "idle" | "connecting" | "done"
      approxError: "",
      analysis: null, // latest {field_help, documents} from the backend (null = none yet)
      dirty: false, // inputs changed since the last successful analysis
      checks: [false, false, false], // after-filing task checklist
      assessmentId: "", // handed over by the host page via setContext("dashboard", data) — "dashboard" mode only
      progressStep: 0, // how far along the overall flow the visitor is — "dashboard"/"after" modes only
      progressTotal: 0, // 0 means "don't show the progress meter" (route/upload modes never set this)
      progressLabel: "", // short caption under the progress bar; falls back to "N of M steps complete" if blank
    };
  }
  let state = defaultState();
  let nextFileId = 1;

  /* ---------------------------------------------------------------------
   * Backend client
   * ------------------------------------------------------------------- */
  const API_BASE = (window.CLAIMREADY_API_BASE || "/api").replace(/\/+$/, "");

  // UI labels of the four dispute categories the SCT handles (matching the
  // backend's _UI_NATURES mapping used for field_help.claimNature.suggestion).
  const SCT_NATURES = new Set([
    "Contract for Sale of Goods",
    "Contract for Provision of Services",
    "Damage to Property",
    "Tenancy / Residential Lease",
  ]);

  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (ch) => {
      const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
      return map[ch];
    });

  // One row in an attached-documents list, with a way to remove a
  // mistakenly-attached file — see the "remove-file" click handler below.
  const fileRow = (f) =>
    `<li><span>${esc(f.name)}</span><button type="button" class="cr-file-remove" data-action="remove-file" data-file-id="${f.id}" aria-label="Remove ${esc(f.name)}">&times;</button></li>`;

  async function apiFetch(path, options) {
    let response;
    try {
      response = await fetch(`${API_BASE}${path}`, options);
    } catch (_err) {
      throw new Error("Cannot reach the assistant service. Check that the app is running, then try again.");
    }
    if (!response.ok) {
      let message = `Request failed (${response.status}).`;
      try {
        const body = await response.json();
        const detail = body && body.detail;
        if (typeof detail === "string") message = detail;
        else if (detail && detail.message) message = detail.message;
      } catch (_err) {
        /* keep the status-based message */
      }
      throw new Error(message);
    }
    return response;
  }

  async function extractFields(text) {
    const response = await apiFetch("/extract-fields", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    return response.json();
  }

  async function extractDocument(files, text) {
    const formData = new FormData();
    files.forEach((entry) => formData.append("files", entry.file, entry.name));
    if (text && text.trim()) formData.append("text", text);
    const response = await apiFetch("/extract-document", { method: "POST", body: formData });
    return response.json();
  }

  async function analyse(text) {
    // Runs field extraction over typed text and/or uploaded documents and
    // stores the result on state.analysis.
    const trimmed = text ? text.trim() : "";
    if (state.files.length === 0) {
      return extractFields(trimmed);
    }
    return extractDocument(state.files, trimmed);
  }


  /* ---------------------------------------------------------------------
   * Small HTML builder helpers
   * ------------------------------------------------------------------- */
  const link = (key, label) =>
    `<a class="cr-link" href="${sources[key]}" target="_blank" rel="noopener noreferrer">${label} &#8599;</a>`;
  const choice = (value, title, desc, icon) =>
    `<button type="button" class="cr-choice" data-choice="${value}">` +
    `<span class="cr-icon-badge">${svg(icon || "chevron", 16)}</span>` +
    `<span><b>${title}</b>${desc ? `<small>${desc}</small>` : ""}</span>` +
    `</button>`;
  const choices = (items) => `<div class="cr-choices">${items.join("")}</div>`;
  const back = () =>
    state.step === "approximate"
      ? '<button type="button" class="cr-back" data-action="back">&larr; Back</button>'
      : "";
  const intro = (small, title, copy) =>
    `<div class="cr-eyebrow">${small}</div><h3 class="cr-h">${title}</h3>${
      copy ? `<p class="cr-copy">${copy}</p>` : ""
    }`;
  // Shared by "dashboard" and "after" modes — state.progressTotal is 0 (falsy) for
  // every other mode, so this quietly renders nothing there.
  const progressMeter = () => {
    if (!state.progressTotal) return "";
    const pct = Math.round((state.progressStep / state.progressTotal) * 100);
    return (
      `<div class="cr-progress" role="progressbar" aria-valuenow="${state.progressStep}" aria-valuemin="0" aria-valuemax="${state.progressTotal}">` +
      `<div class="cr-progress-track"><div class="cr-progress-fill" style="width:${pct}%"></div></div>` +
      `<p class="cr-progress-label">${
        state.progressLabel || state.progressStep + " of " + state.progressTotal + " steps complete"
      }</p>` +
      `</div>`
    );
  };

  /* ---------------------------------------------------------------------
   * Render
   * ------------------------------------------------------------------- */
  let root, screen;

  function renderApproxDone() {
    const fieldHelp = (state.analysis && state.analysis.field_help) || {};
    const entry = (key) => fieldHelp[key] || {};
    const nature = entry("claimNature").available ? entry("claimNature").suggestion : "";
    const detected = [];
    const addDetected = (key) => {
      const e = entry(key);
      if (e.available && e.suggestion) detected.push(esc(e.suggestion));
    };
    addDetected("claimantName");
    addDetected("respondentName");
    addDetected("claimAmount");
    addDetected("claimDate");

    const readout = nature
      ? SCT_NATURES.has(nature)
        ? `Based on what you described, this may be a <strong>${esc(nature)}</strong> dispute, which is usually handled by the Small Claims Tribunal (SCT).`
        : `Based on what you described, this may be a <strong>${esc(nature)}</strong> dispute. Double-check whether it falls under the Small Claims Tribunal's jurisdiction.`
      : "We could not confidently identify a dispute category yet. You can still continue to the form and review the suggestions for each field.";
    const spotted = detected.length
      ? `<p class="cr-copy">We also spotted: ${detected.join(" · ")}.</p>`
      : "";

    return (
      `<div class="cr-note"><strong>Suggestion</strong><p>${readout}</p>${spotted}</div>` +
      `<div class="cr-warning"><strong>Always double-check this.</strong><p>This is only a suggestion, not a legal determination. Verify it against the official eligibility rules and your own documents before relying on it.</p>${link(
        "eligibility",
        "Check official eligibility rules"
      )}</div>` +
      `<button type="button" class="cr-btn cr-primary" data-action="continue-to-form">Continue to pre-filing form &rarr;</button>`
    );
  }

  function render() {
    const label = root.querySelector("#cr-context-label");
    if (label) {
      label.textContent =
        state.mode === "after"
          ? "After filing"
          : state.mode === "dashboard"
          ? "Your dashboard"
          : state.mode === "upload"
          ? "Add documents"
          : "Find my route";
    }

    let html = "";
    if (state.mode === "dashboard") {
      html =
        (state.assessmentId
          ? `<div class="cr-id-badge"><span>Pre-Filing Assessment ID</span><strong>${state.assessmentId}</strong></div>`
          : "") +
        progressMeter() +
        intro(
          "NEXT STEP",
          "File your claim",
          "Your pre-filing assessment is complete. When you're ready, file your claim with the Small Claims Tribunal — this hands you straight to the claim form."
        ) +
        `<button type="button" class="cr-btn cr-primary" data-action="go-to-claim-form">File a Claim &rarr;</button>`;
    } else if (state.mode === "after") {
      html =
        progressMeter() +
        intro(
          "AFTER YOU FILE",
          "There are still steps to complete.",
          "Use your court notice and official instructions to check what is due."
        ) +
        `<div class="cr-warning"><strong>Deliver the documents within 7 days of filing.</strong><p>This is called “serving” the claim.</p></div>` +
        [
          "Deliver the claim and Notice of Consultation using an allowed method.",
          "Keep proof of delivery and file the Declaration of Service before the first consultation.",
          "Check the consultation date and prepare to attend.",
        ]
          .map(
            (t, i) =>
              `<label class="cr-check"><input type="checkbox" data-check="${i}" ${
                state.checks[i] ? "checked" : ""
              }><span>${t}</span></label>`
          )
          .join("") +
        `<p class="cr-status" id="cr-task-status">${
          state.checks.filter(Boolean).length
        } of 3 tasks marked done by you</p>` +
        `<details><summary>I could not deliver the documents</summary><p>Still attend the consultation. The registrar may give directions for another method of service.</p></details>` +
        link("filing", "Check service methods and requirements");
    } else if (state.mode === "upload") {
      html =
        intro(
          "ADD DOCUMENTS",
          "Add more documents",
          "Anything you attach here is in addition to what you already attached — nothing you attached earlier is removed or replaced."
        ) +
        `<div class="cr-upload-row"><button type="button" class="cr-btn" id="cr-attach-btn">${svg(
          "upload",
          16
        )}<span>Attach documents</span></button><input type="file" id="cr-file-input" multiple style="display:none"></div>` +
        (state.files.length
          ? `<ul class="cr-list">${state.files.map((f) => fileRow(f)).join("")}</ul>`
          : `<p class="cr-copy">No documents attached yet.</p>`) +
        (state.approxError
          ? `<p class="cr-status" style="color:var(--cr-error)">${esc(state.approxError)}</p>`
          : "") +
        `<button type="button" class="cr-btn cr-primary" id="cr-resume-btn" data-action="resume-to-form">Continue to questionnaire &rarr;</button>`;
    } else if (state.step === "approximate") {
      const showForm = state.approxStatus !== "done";
      html =
        intro(
          "APPROXIMATE MY ROUTE",
          "Tell us briefly what happened",
          "Describe the situation in your own words and attach any documents you have. This goes to an assistant that suggests a possible starting point."
        ) +
        (showForm
          ? `<div class="cr-warning"><strong>This is only a suggestion.</strong><p>Always double-check any suggested route against your actual claim and the official eligibility rules before relying on it.</p></div>` +
            `<label class="cr-field">Brief incident overview<textarea id="cr-incident-text" rows="4" placeholder="e.g. I paid a deposit for goods that were never delivered...">${
              state.incidentText
            }</textarea></label>` +
            `<div class="cr-upload-row"><button type="button" class="cr-btn" id="cr-attach-btn">${svg(
              "upload",
              16
            )}<span>Attach documents</span></button><input type="file" id="cr-file-input" multiple style="display:none"></div>` +
            (state.files.length
              ? `<ul class="cr-list">${state.files.map((f) => fileRow(f)).join("")}</ul>`
              : "") +
            (state.approxError
              ? `<p class="cr-status" style="color:var(--cr-error)">${state.approxError}</p>`
              : "") +
            `<button type="button" class="cr-btn cr-primary" data-action="approximate-submit" ${
              state.approxStatus === "connecting" ? "disabled" : ""
            }>${
              state.approxStatus === "connecting" ? "Connecting to assistant…" : "Get an approximate route"
            }</button>`
          : renderApproxDone()) +
        back();
    } else {
      // state.step === "start"
      html =
        intro(
          "FIND MY ROUTE",
          "Not sure which type of claim or tribunal applies to you?",
          "This option gives a rough starting point — it is not a substitute for checking the official eligibility rules yourself."
        ) +
        choices([
          choice(
            "approximate",
            "Let us approximate your route for you",
            "For people who don’t know what claim or tribunal route applies to them.",
            "compass"
          ),
        ]);
    }

    screen.innerHTML = html;
    wireDynamicControls();
  }

  function wireDynamicControls() {
    const textarea = screen.querySelector("#cr-incident-text");
    if (textarea) {
      textarea.addEventListener("input", () => {
        state.incidentText = textarea.value;
        state.dirty = true;
      });
    }
    const attachBtn = screen.querySelector("#cr-attach-btn");
    const fileInput = screen.querySelector("#cr-file-input");
    if (attachBtn && fileInput) {
      attachBtn.addEventListener("click", () => fileInput.click());
      fileInput.addEventListener("change", () => {
        Array.from(fileInput.files).forEach((f) =>
          state.files.push({ id: nextFileId++, name: f.name, file: f })
        );
        state.dirty = true;
        fileInput.value = "";
        render();
      });
    }
  }

  /* ---------------------------------------------------------------------
   * Wire up
   * ------------------------------------------------------------------- */
  function mount() {
    const style = document.createElement("style");
    style.id = "claimready-overlay-styles";
    style.textContent = CSS;
    document.head.appendChild(style);

    root = document.createElement("div");
    root.id = "claimready-widget";
    root.dataset.open = "false";
    root.innerHTML = HTML;
    document.body.appendChild(root);

    screen = root.querySelector("#cr-screen");
    const launcher = root.querySelector("#cr-launcher");
    const closeBtn = root.querySelector("#cr-close");

    function open() {
      root.dataset.open = "true";
      launcher.setAttribute("aria-expanded", "true");
      closeBtn.focus();
    }
    function close() {
      root.dataset.open = "false";
      launcher.setAttribute("aria-expanded", "false");
      launcher.focus();
      // Page 2 has no visible launcher bubble for this widget (setContext
      // sets root.style.display = "none" there) — so if the visitor closes
      // the upload panel some way other than "Continue to questionnaire"
      // (the X button, Escape), re-hide the root too, or the launcher would
      // be left floating on Page 2 with nothing that reopens it.
      if (state.mode === "upload") root.style.display = "none";
    }

    launcher.addEventListener("click", open);
    closeBtn.addEventListener("click", close);
    root.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && root.dataset.open === "true") close();
    });

    root.querySelector("#cr-reset").addEventListener("click", () => {
      if (state.mode === "upload") {
        // Resetting here would wipe state.files, which defeats the point of
        // this panel (showing documents already attached). There's nothing
        // else in upload mode to reset, so this is a no-op.
        return;
      }
      const preservedMode = state.mode;
      // "Start over" only means "reset the route-finder wizard" — it isn't
      // meant to also throw away the assessment ID/progress the host page
      // handed over via setContext(), which this widget has no way to
      // re-fetch on its own.
      const preservedDashboardData = {
        assessmentId: state.assessmentId,
        progressStep: state.progressStep,
        progressTotal: state.progressTotal,
        progressLabel: state.progressLabel,
      };
      state = defaultState();
      state.mode = preservedMode;
      if (preservedMode === "dashboard" || preservedMode === "after") Object.assign(state, preservedDashboardData);
      render();
    });

    root.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button || !root.contains(button)) return;
      const action = button.dataset.action;
      if (action === "back") {
        state.step = "start";
        state.approxStatus = "idle";
        state.approxError = "";
        render();
        return;
      }
      if (action === "remove-file") {
        // Lets someone undo a mistaken attachment. Also clears any cached
        // analysis and marks state dirty, so the next continue/resume click
        // re-runs extraction over the remaining files instead of handing the
        // host page suggestions drawn from a document that's no longer attached.
        const id = Number(button.dataset.fileId);
        state.files = state.files.filter((f) => f.id !== id);
        state.analysis = null;
        state.dirty = true;
        render();
        return;
      }
      if (action === "approximate-submit") {
        if (!state.incidentText.trim() && state.files.length === 0) {
          state.approxError = "Please describe what happened or attach a document first.";
          render();
          return;
        }
        state.approxError = "";
        state.approxStatus = "connecting";
        render();
        (async () => {
          try {
            state.analysis = await analyse(state.incidentText);
            state.dirty = false;
            state.approxStatus = "done";
          } catch (error) {
            state.approxStatus = "idle";
            state.approxError = error && error.message ? error.message : "Something went wrong. Please try again.";
          }
          render();
        })();
        return;
      }
      if (action === "continue-to-form") {
        // Generic event rather than a direct navigation call, so this
        // widget file stays reusable across different host pages.
        const payload = {
          field_help: (state.analysis && state.analysis.field_help) || {},
          documents: (state.analysis && state.analysis.documents) || [],
        };
        window.dispatchEvent(new CustomEvent("claimready:route-complete", { detail: payload }));
        close();
        return;
      }
      if (action === "resume-to-form") {
        // Same generic-event pattern as "continue-to-form" above — lets
        // Page 2 restore its saved answers and re-hide this widget. When
        // new documents were attached since the last analysis, re-run the
        // extraction first so the payload is fresh.
        const shouldAnalyse = state.files.length > 0 && (!state.analysis || state.dirty);
        const finish = () => {
          const payload = {
            field_help: (state.analysis && state.analysis.field_help) || {},
            documents: (state.analysis && state.analysis.documents) || [],
          };
          window.dispatchEvent(new CustomEvent("claimready:resume-to-form", { detail: payload }));
          close();
        };
        if (!shouldAnalyse) {
          finish();
          return;
        }
        const resumeButton = root.querySelector("#cr-resume-btn");
        if (resumeButton) {
          resumeButton.disabled = true;
          resumeButton.textContent = "Analysing documents…";
        }
        (async () => {
          try {
            state.analysis = await analyse("");
            state.dirty = false;
            finish();
          } catch (error) {
            state.approxError = error && error.message ? error.message : "Something went wrong analysing your documents.";
            render();
          }
        })();
        return;
      }
      if (action === "go-to-claim-form") {
        // Dashboard mode's one-tap handoff to the claim form — same
        // generic-event pattern as the two above, so this widget file
        // doesn't need to know the host page calls it "prefiling-form".
        window.dispatchEvent(new CustomEvent("claimready:go-to-claim-form"));
        close();
        return;
      }
      const value = button.dataset.choice;
      if (value === "approximate" && state.step === "start") {
        state.step = "approximate";
        render();
      }
    });

    root.addEventListener("change", (event) => {
      const el = event.target;
      if (el.dataset.check !== undefined) {
        state.checks[Number(el.dataset.check)] = el.checked;
        const status = root.querySelector("#cr-task-status");
        if (status) status.textContent = state.checks.filter(Boolean).length + " of 3 tasks marked done by you";
      }
    });

    // Small integration surface for the host page to control this widget:
    // which content it shows, and whether it appears at all. A real
    // integration might instead derive this from routing/URL state.
    window.ClaimReadyOverlay = {
      open,
      close,
      setContext(ctx, data) {
        if (ctx === "hidden") {
          root.style.display = "none";
          close();
          return;
        }
        root.style.display = "";
        if (ctx === "upload") {
          // Unlike "route"/"after", upload mode must NOT reset state — it
          // needs to keep whatever is already in state.files from an
          // earlier "approximate my route" visit.
          state.mode = "upload";
          render();
          return;
        }
        state = defaultState();
        state.mode = ctx === "after" ? "after" : ctx === "dashboard" ? "dashboard" : "route";
        if ((ctx === "dashboard" || ctx === "after") && data) {
          state.assessmentId = data.assessmentId || "";
          state.progressStep = data.progressStep || 0;
          state.progressTotal = data.progressTotal || 0;
          state.progressLabel = data.progressLabel || "";
        }
        render();
        // Dashboard mode's whole point is to greet the visitor as soon as they
        // land on the SCT portal — unlike every other mode, which waits for
        // them to tap the launcher bubble themselves.
        if (ctx === "dashboard") open();
      },
    };

    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount, { once: true });
  } else {
    mount();
  }
})();
