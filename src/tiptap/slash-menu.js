import { Extension } from "@tiptap/core";
import Suggestion from "@tiptap/suggestion";

const ITEMS = [
  { label: "Heading 2",  command: (e) => e.chain().focus().toggleHeading({ level: 2 }).run() },
  { label: "Heading 3",  command: (e) => e.chain().focus().toggleHeading({ level: 3 }).run() },
  { label: "Quote",      command: (e) => e.chain().focus().toggleBlockquote().run() },
  { label: "Code block", command: (e) => e.chain().focus().toggleCodeBlock().run() },
  { label: "Divider",    command: (e) => e.chain().focus().setHorizontalRule().run() },
];

function createPopup() {
  const el = document.createElement("div");
  el.className = "slash-menu";
  el.setAttribute("role", "listbox");
  document.body.appendChild(el);
  return el;
}

function renderItems(el, items, selected, onPick) {
  el.innerHTML = "";
  items.forEach((item, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = item.label;
    btn.className = "slash-menu__item" + (idx === selected ? " is-selected" : "");
    btn.addEventListener("mousedown", (e) => { e.preventDefault(); onPick(item); });
    el.appendChild(btn);
  });
}

function positionPopup(el, clientRect) {
  const rect = clientRect();
  if (!rect) { el.style.display = "none"; return; }
  el.style.display = "block";
  el.style.position = "absolute";
  el.style.top  = `${rect.bottom + window.scrollY + 4}px`;
  el.style.left = `${rect.left + window.scrollX}px`;
}

export const SlashMenu = Extension.create({
  name: "slashMenu",
  addOptions() {
    return {
      suggestion: {
        char: "/",
        startOfLine: false,
        command: ({ editor, range, props }) => {
          editor.chain().focus().deleteRange(range).run();
          props.command(editor);
        },
        items: ({ query }) =>
          ITEMS.filter((i) => i.label.toLowerCase().includes(query.toLowerCase())).slice(0, 6),
        render: () => {
          let popup, items = [], selected = 0, clientRect = null, commandPick;
          return {
            onStart: (props) => {
              popup = createPopup();
              items = props.items;
              selected = 0;
              clientRect = props.clientRect;
              commandPick = props.command;
              renderItems(popup, items, selected, commandPick);
              positionPopup(popup, clientRect);
            },
            onUpdate: (props) => {
              items = props.items;
              selected = 0;
              clientRect = props.clientRect;
              commandPick = props.command;
              renderItems(popup, items, selected, commandPick);
              positionPopup(popup, clientRect);
            },
            onKeyDown: ({ event }) => {
              if (event.key === "ArrowDown") {
                selected = (selected + 1) % items.length;
                renderItems(popup, items, selected, commandPick);
                return true;
              }
              if (event.key === "ArrowUp") {
                selected = (selected - 1 + items.length) % items.length;
                renderItems(popup, items, selected, commandPick);
                return true;
              }
              if (event.key === "Enter") {
                if (items[selected]) commandPick(items[selected]);
                return true;
              }
              if (event.key === "Escape") {
                popup.remove();
                return true;
              }
              return false;
            },
            onExit: () => {
              popup?.remove();
            },
          };
        },
      },
    };
  },
  addProseMirrorPlugins() {
    return [Suggestion({ editor: this.editor, ...this.options.suggestion })];
  },
});
