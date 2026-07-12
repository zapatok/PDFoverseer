// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { focusIsInInput } from "./keyboard-focus";

describe("focusIsInInput", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("is true when an <input> has focus", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    expect(focusIsInInput()).toBe(true);
  });

  it("is true when a <textarea> has focus", () => {
    const textarea = document.createElement("textarea");
    document.body.appendChild(textarea);
    textarea.focus();
    expect(focusIsInInput()).toBe(true);
  });

  it("is true when a <select> has focus", () => {
    // Regression (Track D §4 review): ReorgHud hosts <select> controls;
    // Escape while one has focus is the close-dropdown gesture and must NOT
    // reach the viewer's shortcuts (it silently wiped the marked range).
    const select = document.createElement("select");
    document.body.appendChild(select);
    select.focus();
    expect(focusIsInInput()).toBe(true);
  });

  it("is true when a contentEditable element has focus", () => {
    // jsdom sets the `contenteditable` attribute but never implements the
    // isContentEditable IDL getter (jsdom/jsdom#1670) — set the attribute
    // directly, which is also how React renders the contentEditable prop.
    const div = document.createElement("div");
    div.setAttribute("contenteditable", "true");
    div.tabIndex = 0;
    document.body.appendChild(div);
    div.focus();
    expect(focusIsInInput()).toBe(true);
  });

  it("is false when focus is on the body", () => {
    document.body.focus();
    expect(focusIsInInput()).toBe(false);
  });

  it("is false when focus is on a <button>", () => {
    const button = document.createElement("button");
    document.body.appendChild(button);
    button.focus();
    expect(focusIsInInput()).toBe(false);
  });

  it("is false when passed null", () => {
    expect(focusIsInInput(null)).toBe(false);
  });
});
