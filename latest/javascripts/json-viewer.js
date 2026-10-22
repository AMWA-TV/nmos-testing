(() => {
  "use strict";

  function decodeSource(encoded) {
    const binary = window.atob(encoded);
    const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  }

  function addToken(container, text, className) {
    if (!text) return;
    const token = document.createElement("span");
    token.className = className;
    token.textContent = text;
    container.appendChild(token);
  }

  function renderCode(line) {
    const code = document.createElement("span");
    code.className = "source-editor-code";
    const pattern = /("(?:[^"\\]|\\.)*")|(-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)|(\b(?:true|false|null)\b)|([{}\[\],:])/g;
    let position = 0;
    let match;

    while ((match = pattern.exec(line)) !== null) {
      addToken(code, line.slice(position, match.index), "");
      const tokenClass = match[1]
        ? "source-token-string"
        : match[2]
          ? "source-token-number"
          : match[3]
            ? "source-token-boolean"
            : "source-token-punctuation";
      addToken(code, match[0], tokenClass);
      position = pattern.lastIndex;
    }
    addToken(code, line.slice(position), "");
    return code;
  }

  function indentation(line) {
    const whitespace = line.match(/^[ \t]*/)[0];
    return whitespace.replace(/\t/g, "  ").length;
  }

  function foldEnd(lines, start) {
    if (lines[start].trim() === "") return null;
    const currentIndent = indentation(lines[start]);
    let next = start + 1;
    while (next < lines.length && lines[next].trim() === "") next += 1;
    if (next >= lines.length || indentation(lines[next]) <= currentIndent) return null;

    let end = next;
    while (end < lines.length) {
      if (lines[end].trim() !== "" && indentation(lines[end]) <= currentIndent) break;
      end += 1;
    }
    return end;
  }

  function createLine(lines, number, end) {
    const row = document.createElement("div");
    row.className = "source-editor-line";
    row.dataset.line = String(number);

    const gutter = document.createElement("span");
    gutter.className = "source-editor-gutter";
    if (end !== null) {
      const toggle = document.createElement("button");
      toggle.className = "source-editor-fold-toggle";
      toggle.type = "button";
      toggle.textContent = "⌄";
      toggle.setAttribute("aria-label", "Collapse lines");
      toggle.setAttribute("aria-expanded", "true");
      toggle.dataset.foldEnd = String(end);
      gutter.appendChild(toggle);
    } else {
      const spacer = document.createElement("span");
      spacer.className = "source-editor-fold-spacer";
      gutter.appendChild(spacer);
    }

    const lineNumber = document.createElement("span");
    lineNumber.className = "source-editor-line-number";
    lineNumber.textContent = String(number);
    gutter.appendChild(lineNumber);
    row.append(gutter, renderCode(lines[number - 1]));
    return row;
  }

  function setFoldState(editor, row, collapsed) {
    const toggle = row.querySelector(".source-editor-fold-toggle");
    if (!toggle) return;
    row.toggleAttribute("data-collapsed", collapsed);
    toggle.textContent = collapsed ? "›" : "⌄";
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.setAttribute("aria-label", collapsed ? "Expand lines" : "Collapse lines");

    const start = Number(row.dataset.line);
    const end = Number(toggle.dataset.foldEnd);
    editor.querySelectorAll(".source-editor-line").forEach(child => {
      const number = Number(child.dataset.line);
      if (number > start && number <= end) child.hidden = collapsed;
    });
  }

  function initializeViewer(viewer) {
    const editor = viewer.querySelector(".source-editor");
    const source = decodeSource(viewer.dataset.source);
    const lines = source.replace(/\r/g, "").split("\n");
    const foldEnds = lines.map((line, index) => foldEnd(lines, index));
    const rows = lines.map((line, index) => createLine(lines, index + 1, foldEnds[index]));
    rows.forEach(row => editor.appendChild(row));

    editor.querySelectorAll(".source-editor-fold-toggle").forEach(toggle => {
      toggle.addEventListener("click", () => {
        const row = toggle.closest(".source-editor-line");
        setFoldState(editor, row, !row.hasAttribute("data-collapsed"));
      });
    });

    viewer.querySelector('[data-source-action="expand"]').addEventListener("click", () => {
      editor.querySelectorAll(".source-editor-line").forEach(row => setFoldState(editor, row, false));
    });
    viewer.querySelector('[data-source-action="collapse"]').addEventListener("click", () => {
      editor.querySelectorAll(".source-editor-line").forEach(row => setFoldState(editor, row, row.querySelector(".source-editor-fold-toggle") !== null));
    });

    const rawView = viewer.querySelector(".source-viewer-raw");
    rawView.querySelector("code").textContent = source;
    const foldingView = viewer.querySelector(".source-viewer-folding");
    viewer.querySelector("[data-source-mode]").addEventListener("change", event => {
      const folding = event.target.value === "folding";
      foldingView.hidden = !folding;
      rawView.hidden = folding;
    });
  }

  function initializeViewers() {
    document.querySelectorAll(".json-viewer").forEach(viewer => {
      if (viewer.dataset.initialized === "true") return;
      try {
        initializeViewer(viewer);
        viewer.dataset.initialized = "true";
      } catch (error) {
        const message = document.createElement("p");
        message.textContent = "Unable to render this JSON source file.";
        viewer.appendChild(message);
        console.error("Unable to initialize JSON source viewer", error);
      }
    });
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(initializeViewers);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeViewers);
  } else {
    initializeViewers();
  }
})();
