/** Safe DOM building. Repository names, event types and every other string from the data are
 *  attacker-influenced (anyone can name a repo anything GitHub allows). They are ONLY ever inserted
 *  as text nodes. There is no innerHTML anywhere in this codebase. */
export type Child = Node | string | number | null | undefined | false | Child[];
type Attr = string | number | boolean | undefined | ((e: Event) => void);

function add(el: Element, kids: Child[]) {
  for (const k of kids) {
    if (k === null || k === undefined || k === false) continue;
    if (Array.isArray(k)) { add(el, k); continue; }
    el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
}
export function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, Attr> = {}, ...kids: Child[]): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === false) continue;
    if (typeof v === "function") el.addEventListener(k.replace(/^on/, ""), v);
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  add(el, kids);
  return el;
}
/** Replace an element's children, tolerating optional (null/false) children and nested arrays. */
export function fill(el: Element, ...kids: Child[]): void { el.replaceChildren(); add(el, kids); }
export function s<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number> = {}, ...kids: Child[]): SVGElementTagNameMap[K] {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  add(el, kids);
  return el;
}
export const $ = <T extends Element = HTMLElement>(sel: string, root: ParentNode = document): T => {
  const el = root.querySelector<T>(sel);
  if (!el) throw new Error(`missing element ${sel}`);
  return el;
};
