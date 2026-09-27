import { describe, it, expect, beforeEach } from "vitest";
import { stubBrowser } from "./helpers";
import { WorldView } from "../lib/world";
import type { World } from "../types";

// jsdom has no PointerEvent constructor and no layout engine (getBoundingClientRect is always
// 0x0 unless stubbed), which is exactly why this bug shipped: the previous test suite never
// exercised an actual pointerdown. This one does, with a stubbed layout so the projection math
// (canvas centre = node at x=0,y=0) is checkable without a real browser.
describe("clicking a point on the World canvas", () => {
  beforeEach(() => stubBrowser());

  function makeWorld(): { world: WorldView; canvas: HTMLCanvasElement } {
    document.body.innerHTML = `<div style="width:800px;height:600px"><canvas id="c"></canvas></div>`;
    const canvas = document.querySelector("canvas")!;
    const rect = { left: 0, top: 0, width: 800, height: 600, right: 800, bottom: 600, x: 0, y: 0, toJSON() {} };
    canvas.getBoundingClientRect = () => rect as DOMRect;
    canvas.parentElement!.getBoundingClientRect = () => rect as DOMRect;
    return { world: new WorldView(canvas), canvas };
  }

  it("picks the node under the pointer (WorldView listens for pointerdown; jsdom dispatches it as a MouseEvent)", () => {
    const { world, canvas } = makeWorld();
    const wdata: World = { date: "2026-09-22", nodes: [{ id: 1, n: "a/b", x: 0, y: 0, e: 500, a: 10, f: 0, p: 0, r: 0 }], edges: [], encoding: {} };
    world.setWorld(wdata);
    let picked: number | null = null;
    world.onPick = (n) => { picked = n.id; };
    canvas.dispatchEvent(new MouseEvent("pointerdown", { clientX: 400, clientY: 300, bubbles: true }));
    expect(picked).toBe(1);
  });

  it("does NOT pick when the pointer is far from every node", () => {
    const { world, canvas } = makeWorld();
    world.setWorld({ date: "d", nodes: [{ id: 1, n: "a/b", x: 0, y: 0, e: 500, a: 10, f: 0, p: 0, r: 0 }], edges: [], encoding: {} });
    let picked: number | null = null;
    world.onPick = (n) => { picked = n.id; };
    canvas.dispatchEvent(new MouseEvent("pointerdown", { clientX: 10, clientY: 10, bubbles: true }));
    expect(picked).toBeNull();
  });
});
