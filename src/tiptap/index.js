import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import Link from "@tiptap/extension-link";
import BubbleMenu from "@tiptap/extension-bubble-menu";
import { SlashMenu } from "./slash-menu.js";
import { smartPasteHandler } from "./paste.js";

function bindBubbleClicks(bubbleEl, editor) {
  bubbleEl.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-cmd]");
    if (!btn) return;
    e.preventDefault();
    const [cmd, arg] = btn.dataset.cmd.split(":");
    const chain = editor.chain().focus();
    if (cmd === "setLink") {
      const url = window.prompt("Link URL");
      if (!url) return;
      chain.setLink({ href: url }).run();
      return;
    }
    if (arg) chain[cmd]({ level: Number(arg) }).run();
    else chain[cmd]().run();
  });
}

function mountEditor(shell) {
  const textarea = shell.querySelector("[data-tiptap-input]");
  const mount    = shell.querySelector("[data-editor]");
  const bubble   = shell.querySelector("[data-bubble]");

  const editor = new Editor({
    element: mount,
    extensions: [
      StarterKit.configure({ heading: { levels: [2, 3] } }),
      Underline,
      Link.configure({ openOnClick: false, autolink: true, HTMLAttributes: { rel: "noopener noreferrer" } }),
      BubbleMenu.configure({ element: bubble }),
      SlashMenu,
    ],
    content: textarea.value,
    editorProps: {
      attributes: { class: "prose prose-lg max-w-none focus:outline-none" },
      handlePaste: (view, event) =>
        smartPasteHandler(
          {
            state: view.state,
            pasteHTML: (html) => editor.commands.insertContent(html),
          },
          event,
        ),
    },
    onUpdate: ({ editor }) => {
      textarea.value = editor.getHTML();
    },
  });

  bindBubbleClicks(bubble, editor);

  // Sync once before form submit in case input event was throttled.
  const form = textarea.closest("form");
  if (form) {
    form.addEventListener("submit", () => { textarea.value = editor.getHTML(); });
  }

  return editor;
}

function init() {
  document.querySelectorAll(".tiptap-shell").forEach(mountEditor);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
