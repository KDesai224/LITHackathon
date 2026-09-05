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
 * All interactions below are wired to real, working state â€“ nothing here
 * is a decorative dead end. The backend (form submission, document
 * scanning, account state, etc.) is intentionally out of scope; every
 * link that would require it is labelled as illustrative.
 * -----------------------------------------------------------------------
 */
(() => {
  "use strict";

  // Guard against double-inclusion on the same page.
  if (window.__claimReadyOverlayLoaded) return;
  window.__claimReadyOverlayLoaded = true;

  /* ---------------------------------------------------------------------
   * Icons â€“ small hand-drawn stroke icons (no external icon font/CDN).
   * ------------------------------------------------------------------- */
  const ICONS = {
    compass:
      '<circle cx="12" cy="12" r="9"/><path d="M14.8 9.2l-1.9 4.7-4.7 1.9 1.9-4.7z"/>',
    chevron:
      '<path d="M9 6l6 6-6 6"/>',
    "file-plus":
      '<path d="M13 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9z"/><path d="M13 3v6h6"/><path d="M12 12v6M9 15h6"/>',
    mail:
      '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    "list-checks":
      '<path d="M4 6l1.5 1.5L8 5"/><path d="M4 12l1.5 1.5L8 11"/><path d="M4 18l1.5 1.5L8 17"/><path d="M11 6h9M11 12h9M11 18h9"/>',
    bag:
      '<path d="M6 8h12l1 12H5z"/><path d="M9 8a3 3 0 0 1 6 0"/>',
    wrench:
      '<path d="M14.7 6.3a4 4 0 0 0-5.4 4.6L3 17.2 6.8 21l6.3-6.3a4 4 0 0 0 4.6-5.4l-2.9 2.9-2.1-2.1z"/>',
    house:
      '<path d="M4 11.5L12 4l8 7.5"/><path d="M6 10v10h12V10"/>',
    badge:
      '<circle cx="12" cy="8" r="4"/><path d="M8 13l-2 8 6-3 6 3-2-8"/>',
    users:
      '<circle cx="9" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3 20c0-3 2.7-5 6-5s6 2 6 5"/><path d="M15.5 15c2.5.3 4.5 2 4.5 5"/>',
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
   * Styles â€“ scoped to #claimready-widget, tokens mirror DESIGN.md.
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

.cr-tabs { flex: none; display: flex; gap: 4px; padding: 8px 12px; border-bottom: 1px solid var(--cr-outline); }
.cr-tabs button {
  flex: 1;
  padding: 8px 6px;
  border: none;
  border-radius: var(--cr-radius);
  background: transparent;
  color: var(--cr-on-surface-variant);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.01em;
  cursor: pointer;
  text-align: center;
}
.cr-tabs button:hover { background: var(--cr-surface-muted); }
.cr-tabs button[aria-selected="true"] { background: var(--cr-nav-tint); color: var(--cr-primary); }
.cr-tabs button:focus-visible { outline: 2px solid var(--cr-primary-deep); outline-offset: -2px; }

.cr-stepper { flex: none; display: flex; gap: 4px; padding: 10px 16px 0; }
.cr-stepper .cr-dot { flex: 1; height: 4px; border-radius: 9999px; background: var(--cr-surface-container); }
.cr-stepper .cr-dot[data-active="true"] { background: var(--cr-primary); }

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

.cr-note, .cr-warning, .cr-highlight {
  border-radius: var(--cr-radius);
  padding: 12px 14px;
  margin: 12px 0;
}
.cr-note { background: var(--cr-surface-muted); border-left: 4px solid var(--cr-primary); }
.cr-warning { background: var(--cr-error-bg); color: var(--cr-on-error-container); border-left: 4px solid var(--cr-error); }
.cr-warning strong { display: block; margin-bottom: 4px; }
.cr-note strong { display: block; margin-bottom: 4px; color: var(--cr-on-surface); }
.cr-highlight { border: 2px solid var(--cr-primary); }

.cr-field { display: block; margin: 6px 0 12px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.02em; color: var(--cr-on-surface-variant); }
.cr-field input {
  display: block; width: 100%; margin-top: 6px;
  height: 40px; padding: 0 12px;
  border: 1px solid var(--cr-outline-strong);
  border-radius: var(--cr-radius);
  background: var(--cr-surface-muted);
  color: var(--cr-on-surface);
  font-size: 14px; font-weight: 400; text-transform: none; letter-spacing: normal;
}

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
.cr-btn.cr-primary { border-color: transparent; background: var(--cr-primary); color: var(--cr-on-primary); }
.cr-btn.cr-primary:hover { background: var(--cr-primary-hover); }
.cr-btn.cr-primary:active { background: var(--cr-primary-active); }

.cr-back {
  border: none; background: transparent; color: var(--cr-secondary);
  text-decoration: underline; text-underline-offset: 3px;
  padding: 8px 0; margin-top: 6px; cursor: pointer; font-size: 13px;
}
.cr-back:hover { color: var(--cr-on-surface); }

.cr-check { display: flex; gap: 10px; align-items: flex-start; padding: 10px 0; border-bottom: 1px solid var(--cr-outline); font-size: 14px; }
.cr-check:last-of-type { border-bottom: none; }
.cr-check input { width: 18px; height: 18px; flex: none; margin: 2px 0; accent-color: var(--cr-primary); }

.cr-result-row { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--cr-outline); font-size: 13px; }
.cr-result-row strong { text-align: right; }
.cr-result-row:last-of-type { border-bottom: none; }

.cr-list { padding-left: 20px; margin: 0 0 12px; color: var(--cr-on-surface-variant); }
.cr-list li { margin: 6px 0; }

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
      <span class="cr-icon-badge">${svg("compass", 16)}</span>
      <span class="cr-brand-text">ClaimReady<span class="cr-brand-sub">Independent preparation guide</span></span>
    </div>
    <button type="button" id="cr-close" aria-label="Minimise guide">&#8722;</button>
  </div>
  <nav class="cr-tabs" role="tablist" aria-label="What you need help with">
    <button type="button" role="tab" data-mode="route" aria-selected="true">Find my route</button>
    <button type="button" role="tab" data-mode="form" aria-selected="false">Form help</button>
    <button type="button" role="tab" data-mode="after" aria-selected="false">After filing</button>
  </nav>
  <div class="cr-stepper" id="cr-stepper" aria-hidden="true">
    <span class="cr-dot"></span><span class="cr-dot"></span><span class="cr-dot"></span><span class="cr-dot"></span><span class="cr-dot"></span>
  </div>
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
    respond: "https://www.judiciary.gov.sg/civil/how-to-respond-small-claim",
    employment: "https://www.judiciary.gov.sg/civil/how-to-file-serve-employment-claim",
    neighbour: "https://cmc.mlaw.gov.sg/our-service/faqs/",
    cjts: "https://cjts.judiciary.gov.sg/",
    help: "https://www.judiciary.gov.sg/legal-help-support",
  };
  const labels = {
    goods: "Something I bought",
    services: "A service I paid for",
    rent: "My rental home",
    employment: "My salary or dismissal",
    neighbour: "Noise or nuisance from a neighbour",
    other: "Something else / I am not sure",
  };
  const kindIcon = {
    goods: "bag",
    services: "wrench",
    rent: "house",
    employment: "badge",
    neighbour: "users",
    other: "chevron",
  };

  function defaultState() {
    return {
      mode: "route",
      step: "start",
      kind: "",
      amount: "",
      time: "",
      service: "",
      special: "",
      consent: "",
      history: [],
      checks: [false, false, false],
      formReviewed: false,
    };
  }
  let state = defaultState();

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
  const info = (text, key = "eligibility") =>
    `<details><summary>Why we ask</summary><p>${text}</p>${link(key, "Read the official guidance")}</details>`;
  const back = () =>
    state.history.length
      ? '<button type="button" class="cr-back" data-action="back">&larr; Back to my previous answer</button>'
      : "";
  const intro = (small, title, copy) =>
    `<div class="cr-eyebrow">${small}</div><h3 class="cr-h">${title}</h3>${
      copy ? `<p class="cr-copy">${copy}</p>` : ""
    }`;

  function go(step) {
    state.history.push(state.step);
    state.step = step;
    render();
  }

  /* ---------------------------------------------------------------------
   * Render
   * ------------------------------------------------------------------- */
  let root, screen;

  function renderStepper() {
    // Stages: 1 route  2 prepare info  3 review & file (external)  4 deliver  5 consultation
    const stageForMode = { route: 0, form: 1, after: 3 };
    const active = state.mode === "route" && state.step === "prepare" ? 1 : stageForMode[state.mode] ?? 0;
    root.querySelectorAll("#cr-stepper .cr-dot").forEach((dot, i) => {
      dot.dataset.active = String(i <= active);
    });
  }

  function render() {
    root.querySelectorAll('[role="tab"]').forEach((b) => {
      b.setAttribute("aria-selected", String(b.dataset.mode === state.mode));
    });
    renderStepper();

    let html = "";
    if (state.mode === "form") {
      html =
        intro(
          "HELP WITH THIS FIELD",
          "Who are you claiming against?",
          "The form calls this person or organisation the “respondent”."
        ) +
        `<label class="cr-field">Particulars of Respondent(s)<input type="text" value="Bright Home" readonly aria-label="Sample respondent field"></label>` +
        `<div class="cr-note"><strong>Use the legal name</strong><p>Check your agreement and invoice. A shop name alone may not identify the party you contracted with.</p></div>` +
        `<p>For this sample, “Bright Home” needs checking before it is copied into the form.</p>` +
        `<div class="cr-warning"><strong>To check</strong><p>The full name and an address for the other party.</p></div>` +
        `<details><summary>Where can I find this?</summary><p>Look at the agreement, invoice and correspondence. For a business respondent, check the required ACRA profile.</p>${link(
          "filing",
          "Check official document requirements"
        )}</details>` +
        `<label class="cr-check"><input type="checkbox" id="cr-reviewed" ${
          state.formReviewed ? "checked" : ""
        }><span>I checked the name against my documents.</span></label>` +
        `<p class="cr-status" id="cr-form-status">${
          state.formReviewed
            ? "Marked reviewed in this preview. No official field has been changed."
            : "The guide will not guess the name for you."
        }</p>`;
    } else if (state.mode === "after") {
      html =
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
    } else if (state.step === "start") {
      html =
        intro(
          "LET’S FIND YOUR STARTING POINT",
          "What brings you here?",
          "Choose the closest answer. You can change it later."
        ) +
        choices([
          choice("new", "I want to make a claim", "Someone has not put a problem right.", "file-plus"),
          choice("respond", "Someone has made a claim against me", "I received a notice or claim documents.", "mail"),
          choice("filed", "I have already filed a claim", "Help me with what comes next.", "list-checks"),
        ]) +
        `<details><summary>I am not sure what these mean</summary><p>A claim asks the tribunal to resolve a dispute. If someone is asking for an order against you, you are responding to their claim.</p></details>`;
    } else if (state.step === "kind") {
      html =
        intro("FIND MY ROUTE", "What is the problem about?") +
        choices(Object.entries(labels).map(([v, t]) => choice(v, t, "", kindIcon[v]))) +
        back();
    } else if (state.step === "amount") {
      html =
        intro(
          "CHECK THE AMOUNT",
          "How much money are you asking for?",
          "Choose the total you want to claim, in Singapore dollars."
        ) +
        choices([
          choice("low", "$20,000 or less"),
          choice("mid", "More than $20,000, up to $30,000"),
          choice("high", "More than $30,000"),
          choice("unknown", "I am not sure / I want work done"),
        ]) +
        info("The amount and the remedy affect the route. A claim for work needs additional checks.") +
        back();
    } else if (state.step === "consent") {
      html =
        intro(
          "ONE EXTRA CHECK",
          "Have both sides signed a Memorandum of Consent?",
          "This is a specific document, not just agreement that there is a dispute."
        ) +
        choices([
          choice("yes", "Yes, both sides have signed"),
          choice("no", "No"),
          choice("unknown", "I am not sure"),
        ]) +
        info("Consent from both sides is needed for the higher limit of $30,000.") +
        back();
    } else if (state.step === "time") {
      html =
        intro(
          "CHECK THE TIMING",
          "When did the event behind your claim happen?",
          "For example, the date a promised delivery was missed. If the relevant date is unclear, choose “I am not sure”."
        ) +
        choices([
          choice("recent", "Less than 2 years ago"),
          choice("old", "2 years ago or longer"),
          choice("unknown", "I am not sure which date counts"),
        ]) +
        info(
          "The time limit runs from the event creating the cause of action. This quick check does not calculate a filing deadline."
        ) +
        back();
    } else if (state.step === "service") {
      html =
        intro(
          "CHECK THE OTHER PARTY",
          "Can the documents be delivered to the other party in Singapore?",
          "This is different from where you bought the item or where you live."
        ) +
        choices([
          choice("yes", "Yes, I have a Singapore address"),
          choice("no", "No, they are outside Singapore"),
          choice("unknown", "I do not know their address"),
        ]) +
        info("SCT claims must be served on the respondent in Singapore.") +
        back();
    } else if (state.step === "special") {
      html =
        intro("CHECK FOR EXTRA REQUIREMENTS", "Is either side bankrupt, or is a company being wound up?") +
        choices([
          choice("no", "No, as far as I know"),
          choice("yes", "Yes"),
          choice("unknown", "I am not sure"),
        ]) +
        info(
          "Bankruptcy and company winding-up can require additional permissions. An uncertain answer should be checked."
        ) +
        back();
    } else if (state.step === "respond") {
      html =
        intro(
          "RESPONDING TO A CLAIM",
          "Start with the notice you received.",
          "You have a different set of steps from someone starting a new claim."
        ) +
        `<ol class="cr-list"><li>Find the case number and court date.</li><li>Read what the other side is claiming.</li><li>Use the official response guide to access the case and prepare your account.</li></ol>` +
        link("respond", "Open the guide for responding to a small claim") +
        `<div class="cr-note"><p>Keep the notice even if you disagree with the claim.</p></div>` +
        back();
    } else if (state.step === "other") {
      const k = state.kind;
      html =
        intro(
          "FIND MY ROUTE",
          k === "employment"
            ? "Explore the employment route."
            : k === "neighbour"
            ? "Explore help for neighbour disputes."
            : "Let’s check the details before choosing a route.",
          k === "rent"
            ? "Rental arrangements need extra checks, including the type and length of the agreement."
            : k === "services"
            ? "Check what service was agreed and whether any exclusions apply."
            : ""
        ) +
        (k === "employment"
          ? `<p>For salary or dismissal claims, check the employment guidance, including TADM mediation before an ECT claim.</p>${link(
              "employment",
              "Read the employment claim steps"
            )}`
          : k === "neighbour"
          ? `<p>For noise or nuisance, community mediation may help. Check which disputes the service handles.</p>${link(
              "neighbour",
              "Explore Community Mediation Centre help"
            )}`
          : `<div class="cr-note"><p>This preview’s detailed route check covers purchases of goods. Other categories need their own questions.</p></div>${link(
              "eligibility",
              "Check the full list and conditions"
            )}`) +
        `<details><summary>What if my problem has more than one part?</summary><p>Describe each part separately. Do not force it into a category just to continue.</p>${link(
          "help",
          "Find legal help and support"
        )}</details>` +
        back();
    } else if (state.step === "result") {
      const flags = [];
      if (state.amount === "high")
        flags.push("The amount is above the usual SCT limits. Get advice on your options before changing the amount.");
      if (state.amount === "unknown") flags.push("Confirm the amount and the remedy you want.");
      if (state.amount === "mid" && state.consent !== "yes")
        flags.push("Check the signed consent requirement for the higher limit.");
      if (state.time !== "recent") flags.push("Check the relevant date and time limit promptly.");
      if (state.service !== "yes") flags.push("Check whether and where the other party can be served in Singapore.");
      if (state.special !== "no") flags.push("Check whether extra permissions are required.");
      html =
        intro(
          "YOUR NEXT STEP",
          flags.length ? "Check these points before filing." : "SCT may be a relevant route.",
          "This is preliminary guidance. The tribunal decides whether it can hear a claim."
        ) +
        `<div class="cr-result-row"><span>What you selected</span><strong>${labels[state.kind]}</strong></div>` +
        `<div class="cr-result-row"><span>Official category to check</span><strong>Contract for the sale of goods</strong></div>` +
        (flags.length
          ? `<div class="cr-warning"><strong>${flags.length} point${
              flags.length === 1 ? "" : "s"
            } to check</strong><ul class="cr-list">${flags.map((f) => `<li>${f}</li>`).join("")}</ul></div>`
          : `<div class="cr-note"><p>No issue was identified in these broad checks. The official assessment asks more questions.</p></div>`) +
        `<a class="cr-btn cr-primary" href="${sources.cjts}" target="_blank" rel="noopener noreferrer">Open CJTS for the official assessment &#8599;</a>` +
        `<p class="cr-status">Choose the SCT pre-filing assessment. Your answers here are not transferred.</p>` +
        `<details><summary>Why this route?</summary><p>You selected a problem with something you bought. The official list includes contracts for the sale of goods, subject to its conditions.</p>${link(
          "eligibility",
          "Check eligibility and exclusions"
        )}</details>` +
        `<button type="button" class="cr-btn" data-action="prepare">See what to gather first</button>` +
        back();
    } else if (state.step === "prepare") {
      html =
        intro(
          "PREPARE YOUR INFORMATION",
          "Gather these before you start.",
          "Keep your account of what happened separate from what the documents show."
        ) +
        `<ul class="cr-list"><li>Your agreement, order or invoice.</li><li>Proof of payment and any refund.</li><li>Messages about delivery and attempts to resolve the problem.</li><li>The other party’s legal name and address.</li></ul>` +
        `<div class="cr-note"><p>You can organise your information while checking an unresolved route question.</p></div>` +
        `<button type="button" class="cr-btn cr-primary" data-action="form">See help with a form field</button>` +
        `<details><summary>Check the document requirements</summary>${link(
          "filing",
          "Open the current filing checklist"
        )}</details>` +
        back();
    }

    screen.innerHTML = html;
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
    }

    launcher.addEventListener("click", open);
    closeBtn.addEventListener("click", close);
    root.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && root.dataset.open === "true") close();
    });

    root.querySelector("#cr-reset").addEventListener("click", () => {
      state = defaultState();
      render();
    });

    root.addEventListener("click", (event) => {
      const tab = event.target.closest('[role="tab"]');
      if (tab) {
        state.mode = tab.dataset.mode;
        render();
        return;
      }
      const button = event.target.closest("button");
      if (!button || !root.contains(button)) return;
      const action = button.dataset.action;
      if (action === "back") {
        state.step = state.history.pop() || "start";
        render();
        return;
      }
      if (action === "prepare") {
        go("prepare");
        return;
      }
      if (action === "form") {
        state.mode = "form";
        render();
        return;
      }
      const value = button.dataset.choice;
      if (!value) return;
      switch (state.step) {
        case "start":
          if (value === "filed") {
            state.mode = "after";
            render();
          } else {
            go(value === "new" ? "kind" : "respond");
          }
          break;
        case "kind":
          state.kind = value;
          go(value === "goods" ? "amount" : "other");
          break;
        case "amount":
          state.amount = value;
          state.consent = "";
          go(value === "mid" ? "consent" : "time");
          break;
        case "consent":
          state.consent = value;
          go("time");
          break;
        case "time":
          state.time = value;
          go("service");
          break;
        case "service":
          state.service = value;
          go("special");
          break;
        case "special":
          state.special = value;
          go("result");
          break;
      }
    });

    root.addEventListener("change", (event) => {
      const el = event.target;
      if (el.dataset.check !== undefined) {
        state.checks[Number(el.dataset.check)] = el.checked;
        const status = root.querySelector("#cr-task-status");
        if (status) status.textContent = state.checks.filter(Boolean).length + " of 3 tasks marked done by you";
      }
      if (el.id === "cr-reviewed") {
        state.formReviewed = el.checked;
        const status = root.querySelector("#cr-form-status");
        if (status)
          status.textContent = el.checked
            ? "Marked reviewed in this preview. No official field has been changed."
            : "The guide will not guess the name for you.";
      }
    });

    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount, { once: true });
  } else {
    mount();
  }
})();
