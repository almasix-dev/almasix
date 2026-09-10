import { describe, expect, it } from "vitest";
import { normalizeEvent } from "../src/channel.js";
import { Channel } from "../src/channel.js";

describe("normalizeEvent", () => {
  it("keeps almasix system events", () => {
    expect(normalizeEvent("almasix:connection_established")).toBe(
      "almasix:connection_established",
    );
  });

  it("maps optional pusher aliases to almasix", () => {
    expect(normalizeEvent("pusher:subscription_succeeded")).toBe(
      "almasix:subscription_succeeded",
    );
  });
});

describe("Channel", () => {
  it("dispatches listen callbacks for broadcast events", () => {
    const sent: Record<string, unknown>[] = [];
    const channel = new Channel("announcements", (frame) => sent.push(frame), () => undefined);
    const seen: unknown[] = [];
    channel.listen("post.published", (data) => seen.push(data));
    channel.handle({
      event: "post.published",
      channel: "announcements",
      data: { title: "Hello" },
    });
    expect(seen).toEqual([{ title: "Hello" }]);
  });

  it("fires subscribed after subscription_succeeded", () => {
    const channel = new Channel("announcements", () => undefined, () => undefined);
    let hit = 0;
    channel.subscribed(() => {
      hit += 1;
    });
    channel.handle({ event: "almasix:subscription_succeeded", channel: "announcements", data: {} });
    expect(hit).toBe(1);
    channel.subscribed(() => {
      hit += 1;
    });
    expect(hit).toBe(2);
  });

  it("whispers client-* events", () => {
    const sent: Record<string, unknown>[] = [];
    const channel = new Channel("private-room", (frame) => sent.push(frame), () => undefined);
    channel.whisper("typing", { ok: true });
    expect(sent[0]).toEqual({
      event: "client-typing",
      channel: "private-room",
      data: { ok: true },
    });
  });
});
