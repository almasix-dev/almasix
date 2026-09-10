/**
 * almasix.conduit client — Livewire 4-shaped wire:* + Alpine $wire.
 * Goals: feel like pure JS — coalesce requests, idiomorph-lite, client wire:bind/text/show.
 *
 * Subpath hosting: never assume site-root "/conduit/...". Read window.__CONDUIT__
 * (injected by @conduitScripts) or <meta name="conduit-endpoint|conduit-base">,
 * then fall back to deriving the prefix from this script's src.
 */
(function () {
  "use strict";

  function readConfig() {
    const boot = window.__CONDUIT__ || {};
    const metaEndpoint = document.querySelector('meta[name="conduit-endpoint"]');
    const metaBase = document.querySelector('meta[name="conduit-base"]');
    let endpoint = boot.endpoint || (metaEndpoint && metaEndpoint.getAttribute("content")) || "";
    let base = boot.base || (metaBase && metaBase.getAttribute("content")) || "";
    if (!endpoint || !base) {
      const scripts = document.getElementsByTagName("script");
      for (let i = scripts.length - 1; i >= 0; i--) {
        const src = scripts[i].src || "";
        const idx = src.indexOf("/conduit/conduit.js");
        if (idx >= 0) {
          try {
            const u = new URL(src, window.location.origin);
            const path = u.pathname;
            const cut = path.indexOf("/conduit/conduit.js");
            base = base || path.slice(0, cut);
            endpoint = endpoint || path.slice(0, cut) + "/conduit/update";
          } catch (_) {}
          break;
        }
      }
    }
    return {
      base: base || "",
      endpoint: endpoint || "/conduit/update",
      upload: boot.upload || "",
      coalesceMs: boot.coalesceMs || 16,
      signed: boot.signed !== false,
    };
  }

  const CONFIG = readConfig();
  let ENDPOINT = CONFIG.endpoint;
  const COALESCE_MS = CONFIG.coalesceMs;
  const APP_BASE = CONFIG.base; // "" or "/my-app"

  function currentEndpoint() {
    return ENDPOINT || CONFIG.endpoint;
  }

  /** Prefix a root-absolute path with APP_BASE when missing (subpath safety net). */
  function withBase(path) {
    if (!path || typeof path !== "string") return path;
    if (/^([a-zA-Z][a-zA-Z0-9+.-]*:)?\/\//.test(path) || path.startsWith("#") || path.startsWith("?")) {
      return path;
    }
    if (!APP_BASE) return path;
    if (!path.startsWith("/")) return path;
    if (path === APP_BASE || path.startsWith(APP_BASE + "/")) return path;
    return APP_BASE + path;
  }

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute("content") || "";
    const input = document.querySelector('input[name="_token"]');
    return input ? input.value : "";
  }

  function parseInitial(el) {
    const raw = el.getAttribute("wire:initial-data");
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (_) {
      return null;
    }
  }

  /** Idiomorph-lite: patch attributes + children by wire:key / tag+position. */
  function morph(fromEl, toEl) {
    if (!fromEl || !toEl) return;
    if (fromEl.nodeType !== 1 || toEl.nodeType !== 1) {
      fromEl.replaceWith(toEl);
      return;
    }
    if (fromEl.tagName !== toEl.tagName) {
      fromEl.replaceWith(toEl);
      return;
    }
    if (fromEl.hasAttribute("wire:ignore") || fromEl.getAttribute("wire:ignore.self") !== null) {
      if (fromEl.hasAttribute("wire:ignore")) return;
    }
    // attrs
    const fromAttrs = fromEl.attributes;
    for (let i = fromAttrs.length - 1; i >= 0; i--) {
      const name = fromAttrs[i].name;
      if (!toEl.hasAttribute(name) && name !== "wire:id" && name !== "wire:initial-data") {
        fromEl.removeAttribute(name);
      }
    }
    for (const attr of toEl.attributes) {
      if (attr.name === "wire:initial-data") continue;
      if (fromEl.getAttribute(attr.name) !== attr.value) {
        fromEl.setAttribute(attr.name, attr.value);
      }
    }
    // keyed children
    const fromKids = Array.from(fromEl.childNodes);
    const toKids = Array.from(toEl.childNodes);
    const keyed = new Map();
    fromKids.forEach((n) => {
      if (n.nodeType === 1 && n.getAttribute && n.getAttribute("wire:key")) {
        keyed.set(n.getAttribute("wire:key"), n);
      }
    });
    let fi = 0;
    for (let ti = 0; ti < toKids.length; ti++) {
      const t = toKids[ti];
      if (t.nodeType === 3) {
        const f = fromKids[fi];
        if (f && f.nodeType === 3) {
          if (f.nodeValue !== t.nodeValue) f.nodeValue = t.nodeValue;
          fi++;
        } else {
          fromEl.insertBefore(document.createTextNode(t.nodeValue), fromKids[fi] || null);
        }
        continue;
      }
      if (t.nodeType !== 1) continue;
      const key = t.getAttribute("wire:key");
      let f = key && keyed.get(key);
      if (!f) {
        f = fromKids[fi];
        while (f && f.nodeType !== 1) {
          fi++;
          f = fromKids[fi];
        }
      }
      if (f && f.nodeType === 1 && f.tagName === t.tagName) {
        morph(f, t);
        if (f !== fromKids[fi]) {
          fromEl.insertBefore(f, fromKids[fi] || null);
        }
        fi++;
      } else {
        const clone = t.cloneNode(true);
        fromEl.insertBefore(clone, fromKids[fi] || null);
      }
    }
    while (fromEl.childNodes.length > toKids.length) {
      fromEl.removeChild(fromEl.lastChild);
    }
  }

  function morphHtml(fromEl, html) {
    if (fromEl.hasAttribute("wire:ignore")) return;
    const tpl = document.createElement("template");
    tpl.innerHTML = String(html).trim();
    const next = tpl.content.firstElementChild;
    if (!next) {
      fromEl.innerHTML = html;
      return;
    }
    if (fromEl.tagName === next.tagName) {
      morph(fromEl, next);
      // refresh snapshot attr
      const data = next.getAttribute("wire:initial-data");
      if (data) fromEl.setAttribute("wire:initial-data", data);
      bindDirectives(fromEl, fromEl.__conduitSnapshot);
      applyClientBindings(fromEl);
    } else {
      fromEl.replaceWith(next);
      bootElement(next);
    }
  }

  function morphIsland(root, name, html) {
    const target =
      root.querySelector(`[wire\\:island="${name}"]`) ||
      root.querySelector(`[wire\\:island='${name}']`);
    if (!target) {
      morphHtml(root, html);
      return;
    }
    const tpl = document.createElement("template");
    tpl.innerHTML = String(html).trim();
    const next = tpl.content.firstElementChild || tpl.content;
    if (next.nodeType === 1) morph(target, next);
    else target.innerHTML = html;
  }

  const queues = new WeakMap();

  function enqueue(el, snapshot, piece) {
    let q = queues.get(el);
    if (!q) {
      q = { updates: [], calls: [], island: null, timer: null, waiters: [] };
      queues.set(el, q);
    }
    if (piece.updates) q.updates.push(...piece.updates);
    if (piece.calls) q.calls.push(...piece.calls);
    if (piece.island) q.island = piece.island;
    return new Promise((resolve) => {
      q.waiters.push(resolve);
      if (q.timer) clearTimeout(q.timer);
      q.timer = setTimeout(() => flush(el, snapshot), COALESCE_MS);
    });
  }

  async function flush(el, snapshot) {
    const q = queues.get(el);
    if (!q) return;
    queues.delete(el);
    const payload = {
      updates: q.updates,
      calls: q.calls,
      island: q.island,
    };
    setLoading(el, true);
    const scrollY = payload.calls.some((c) => c.meta && c.meta.preserveScroll)
      ? window.scrollY
      : null;
    const result = await requestUpdate(snapshot, payload);
    setLoading(el, false);
    if (scrollY !== null) window.scrollTo(0, scrollY);
    if (result && result.serverMemo) {
      snapshot.serverMemo = result.serverMemo;
      if (result.fingerprint) snapshot.fingerprint = result.fingerprint;
      el.__conduitSnapshot = snapshot;
    }
    applyEffects(el, result, snapshot);
    q.waiters.forEach((r) => r(result));
  }

  async function requestUpdate(snapshot, { updates = [], calls = [], island = null } = {}) {
    const body = {
      fingerprint: snapshot.fingerprint,
      serverMemo: snapshot.serverMemo,
      updates,
      calls,
      island,
    };
    const res = await fetch(withBase(currentEndpoint()), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRF-TOKEN": csrfToken(),
        "X-Conduit": "true",
      },
      credentials: "same-origin",
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      console.error("[conduit] update failed", res.status);
      return null;
    }
    return res.json();
  }

  function setLoading(el, on) {
    el.toggleAttribute("data-loading", on);
    el.querySelectorAll("[wire\\:loading], [data-loading]").forEach((n) => {
      if (on) {
        n.setAttribute("data-loading", "true");
        if (n.hasAttribute("wire:loading")) n.style.display = "";
      } else {
        n.removeAttribute("data-loading");
      }
    });
    el.classList.toggle("conduit-dirty", on);
  }

  function applyClientBindings(el) {
    const snap = el.__conduitSnapshot;
    if (!snap || !snap.serverMemo) return;
    const data = snap.serverMemo.data || {};
    const errors = snap.serverMemo.errors || {};
    el.__wireErrors = errors;

    el.querySelectorAll("[wire\\:text]").forEach((node) => {
      const key = node.getAttribute("wire:text");
      if (key in data) node.textContent = data[key] == null ? "" : String(data[key]);
    });
    el.querySelectorAll("[wire\\:show]").forEach((node) => {
      const key = node.getAttribute("wire:show");
      const show = !!data[key];
      node.style.display = show ? "" : "none";
    });
    el.querySelectorAll("[wire\\:bind\\:class], [wire\\:bind\\:disabled], [wire\\:bind\\:href], [wire\\:bind\\:value]").forEach(
      () => {}
    );
    Array.from(el.querySelectorAll("*")).forEach((node) => {
      Array.from(node.attributes || []).forEach((attr) => {
        if (!attr.name.startsWith("wire:bind:")) return;
        const prop = attr.name.slice("wire:bind:".length);
        const expr = attr.value;
        let val;
        try {
          val = Function("data", "$wire", "return (" + expr + ")")(data, el.__wire);
        } catch (_) {
          val = data[expr];
        }
        if (prop === "class") {
          if (typeof val === "string") node.className = val;
          else if (val && typeof val === "object") {
            Object.entries(val).forEach(([c, on]) => node.classList.toggle(c, !!on));
          }
        } else if (prop === "style" && val && typeof val === "object") {
          Object.assign(node.style, val);
        } else if (typeof val === "boolean") {
          if (val) node.setAttribute(prop, "");
          else node.removeAttribute(prop);
        } else if (val != null) {
          node.setAttribute(prop, String(val));
        }
      });
    });
  }

  function applyEffects(el, result, snapshot) {
    if (!result) return;
    if (result.error) {
      console.error("[conduit]", result.error);
      return;
    }
    const effects = result.effects || {};
    if (effects.data && snapshot) {
      snapshot.serverMemo.data = effects.data;
      if (effects.errors) snapshot.serverMemo.errors = effects.errors;
    }
    if (effects.queryString) {
      const url = new URL(window.location.href);
      Object.entries(effects.queryString).forEach(([k, v]) => {
        if (v === null || v === undefined || v === "") url.searchParams.delete(k);
        else url.searchParams.set(k, String(v));
      });
      window.history.replaceState({}, "", url);
    }
    if (effects.endpoint) {
      ENDPOINT = effects.endpoint;
      CONFIG.endpoint = effects.endpoint;
      const meta = document.querySelector('meta[name="conduit-endpoint"]');
      if (meta) meta.setAttribute("content", effects.endpoint);
      if (window.__CONDUIT__) window.__CONDUIT__.endpoint = effects.endpoint;
    }
    (effects.dispatches || []).forEach((d) => {
      if (d.event === "__js" && d.params && d.params.expr) {
        try {
          Function("$wire", d.params.expr)(el.__wire);
        } catch (e) {
          console.error("[conduit] $js", e);
        }
        return;
      }
      window.dispatchEvent(new CustomEvent(d.event, { detail: d.params || {} }));
    });
    applyClientBindings(el);
    if (effects.islands) {
      Object.entries(effects.islands).forEach(([name, html]) => morphIsland(el, name, html));
      return;
    }
    if (effects.island && effects.html) {
      morphIsland(el, effects.island, effects.html);
      return;
    }
    if (effects.html) morphHtml(el, effects.html);
  }

  function wireProxy(el, snapshot) {
    return new Proxy(
      {},
      {
        get(_t, prop) {
          if (prop === "$refresh") {
            return () =>
              enqueue(el, snapshot, { calls: [{ method: "$refresh", params: [] }] });
          }
          if (prop === "$set") {
            return (name, value) => {
              snapshot.serverMemo.data[name] = value;
              applyClientBindings(el);
              return enqueue(el, snapshot, { updates: [[name, value]] });
            };
          }
          if (prop === "$toggle") {
            return (name) =>
              enqueue(el, snapshot, { calls: [{ method: "$toggle", params: [name] }] });
          }
          if (prop === "$dispatch") {
            return (event, params) =>
              window.dispatchEvent(new CustomEvent(event, { detail: params || {} }));
          }
          if (prop === "$errors") return el.__wireErrors || {};
          if (prop === "$island") {
            return (name, opts) => {
              const method = (opts && opts.method) || "$refresh";
              return enqueue(el, snapshot, {
                island: name,
                calls: [{ method, params: (opts && opts.params) || [], island: name }],
              });
            };
          }
          if (prop === "$entangle") {
            return (name) => ({
              get value() {
                return snapshot.serverMemo.data[name];
              },
              set value(v) {
                snapshot.serverMemo.data[name] = v;
                applyClientBindings(el);
                enqueue(el, snapshot, { updates: [[name, v]] });
              },
            });
          }
          if (typeof prop === "string" && prop in (snapshot.serverMemo.data || {})) {
            return snapshot.serverMemo.data[prop];
          }
          return (...params) => {
            const meta = {};
            return enqueue(el, snapshot, {
              calls: [{ method: String(prop), params, meta }],
            });
          };
        },
        set(_t, prop, value) {
          snapshot.serverMemo.data[prop] = value;
          applyClientBindings(el);
          enqueue(el, snapshot, { updates: [[String(prop), value]] });
          return true;
        },
      }
    );
  }

  function parseClick(methodAttr) {
    // "increment" | "add(1)" | "save.renderless" handled via separate attrs
    const m = String(methodAttr).match(/^([a-zA-Z_][\w]*)\s*(?:\((.*)\))?$/);
    if (!m) return { method: methodAttr, params: [] };
    const params = [];
    if (m[2]) {
      try {
        params.push(...Function("return [" + m[2] + "]")());
      } catch (_) {}
    }
    return { method: m[1], params };
  }

  function bindDirectives(el, snapshot) {
    el.querySelectorAll("[wire\\:click]").forEach((btn) => {
      if (btn.__conduitBound) return;
      btn.__conduitBound = true;
      btn.addEventListener("click", (e) => {
        if (btn.hasAttribute("wire:confirm")) {
          const msg = btn.getAttribute("wire:confirm") || "Are you sure?";
          if (!window.confirm(msg)) {
            e.preventDefault();
            return;
          }
        }
        e.preventDefault();
        const raw = btn.getAttribute("wire:click");
        const { method, params } = parseClick(raw);
        const meta = {};
        if (btn.hasAttribute("wire:click.renderless") || /\.renderless/.test(raw || ""))
          meta.renderless = true;
        if (btn.hasAttribute("wire:click.preserve-scroll")) meta.preserveScroll = true;
        const island = btn.getAttribute("wire:island");
        const call = { method: method.replace(/\.renderless$/, ""), params, meta };
        if (island) call.island = island;
        enqueue(el, snapshot, { calls: [call], island });
      });
    });

    el.querySelectorAll("[wire\\:submit]").forEach((form) => {
      if (form.__conduitBound) return;
      form.__conduitBound = true;
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        const method = form.getAttribute("wire:submit") || "submit";
        enqueue(el, snapshot, { calls: [{ method, params: [] }] });
      });
    });

    const modelSel =
      "[wire\\:model], [wire\\:model\\.live], [wire\\:model\\.blur], [wire\\:model\\.change], [wire\\:model\\.deep], [wire\\:model\\.live\\.blur]";
    el.querySelectorAll(modelSel).forEach((input) => {
      if (input.__conduitBound) return;
      input.__conduitBound = true;
      let name =
        input.getAttribute("wire:model") ||
        input.getAttribute("wire:model.live") ||
        input.getAttribute("wire:model.blur") ||
        input.getAttribute("wire:model.change") ||
        input.getAttribute("wire:model.deep") ||
        input.getAttribute("wire:model.live.blur");
      if (!name) return;
      const live =
        input.hasAttribute("wire:model.live") || input.hasAttribute("wire:model.live.blur");
      const blurOnly =
        input.hasAttribute("wire:model.blur") || input.hasAttribute("wire:model.live.blur");
      const debounceMs = (() => {
        for (const a of input.attributes) {
          const m = a.name.match(/^wire:model\.debounce\.(\d+)ms$/);
          if (m) return parseInt(m[1], 10);
        }
        return live ? 0 : 0;
      })();
      let t = null;
      const read = () =>
        input.type === "checkbox" ? !!input.checked : input.type === "file" ? input.files : input.value;
      const push = () => {
        const value = read();
        snapshot.serverMemo.data[name] = value;
        applyClientBindings(el);
        enqueue(el, snapshot, { updates: [[name, value]] });
      };
      const onInput = () => {
        snapshot.serverMemo.data[name] = read();
        applyClientBindings(el);
        if (!live && blurOnly) return;
        if (debounceMs) {
          clearTimeout(t);
          t = setTimeout(push, debounceMs);
        } else if (live) push();
      };
      input.addEventListener("input", onInput);
      if (blurOnly) input.addEventListener("blur", push);
      else if (!live) input.addEventListener("change", push);
    });

    el.querySelectorAll("[wire\\:poll]").forEach((node) => {
      if (node.__conduitPoll) return;
      const raw = node.getAttribute("wire:poll") || "5s";
      let ms = 5000;
      const m = String(raw).match(/^(\d+)(ms|s)?$/);
      if (m) ms = parseInt(m[1], 10) * (m[2] === "ms" ? 1 : 1000);
      const island = node.getAttribute("wire:island");
      node.__conduitPoll = setInterval(() => {
        enqueue(el, snapshot, {
          calls: [{ method: "$refresh", params: [], island }],
          island,
        });
      }, ms);
    });

    el.querySelectorAll("[wire\\:intersect]").forEach((node) => {
      if (node.__conduitIo) return;
      const method = node.getAttribute("wire:intersect") || "$refresh";
      const once = node.hasAttribute("wire:intersect.once");
      const opts = { threshold: 0.01 };
      if (node.hasAttribute("wire:intersect.half")) opts.threshold = 0.5;
      if (node.hasAttribute("wire:intersect.full")) opts.threshold = 0.99;
      node.__conduitIo = new IntersectionObserver((entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        const { method: m, params } = parseClick(method);
        enqueue(el, snapshot, { calls: [{ method: m, params }] });
        if (once) node.__conduitIo.disconnect();
      }, opts);
      node.__conduitIo.observe(node);
    });

    el.querySelectorAll("[wire\\:init]").forEach((node) => {
      if (node.__conduitInit) return;
      node.__conduitInit = true;
      const method = node.getAttribute("wire:init");
      if (method) {
        const { method: m, params } = parseClick(method);
        enqueue(el, snapshot, { calls: [{ method: m, params }] });
      }
    });

    el.querySelectorAll("[wire\\:ref]").forEach((node) => {
      const ref = node.getAttribute("wire:ref");
      if (!ref) return;
      el.__conduitRefs = el.__conduitRefs || {};
      el.__conduitRefs[ref] = node;
    });

    // wire:sort basic HTML5 DnD
    el.querySelectorAll("[wire\\:sort]").forEach((list) => {
      if (list.__conduitSort) return;
      list.__conduitSort = true;
      const method = list.getAttribute("wire:sort") || "sort";
      list.querySelectorAll("[wire\\:sort\\:item]").forEach((item) => {
        item.draggable = true;
        item.addEventListener("dragstart", () => {
          list.__drag = item;
        });
        item.addEventListener("dragover", (e) => e.preventDefault());
        item.addEventListener("drop", (e) => {
          e.preventDefault();
          if (!list.__drag || list.__drag === item) return;
          list.insertBefore(list.__drag, item);
          const order = Array.from(list.querySelectorAll("[wire\\:sort\\:item]")).map(
            (n, i) => n.getAttribute("wire:sort:item") || String(i)
          );
          enqueue(el, snapshot, { calls: [{ method, params: [order] }] });
        });
      });
    });
  }

  function bootElement(el) {
    if (!el || el.__conduitBooted) return;
    const snap = parseInitial(el);
    if (!snap) {
      const lazy = el.getAttribute("wire:lazy") === "true";
      const defer = el.getAttribute("wire:defer") === "true";
      if (lazy || defer) {
        const load = () => {
          const name = el.getAttribute("wire:name");
          const id = el.getAttribute("wire:id");
          const empty = {
            fingerprint: { id, name, path: location.pathname, method: "GET" },
            serverMemo: { data: {}, checksum: "", errors: {} },
          };
          enqueue(el, empty, { calls: [{ method: "$load", params: [] }] }).then(() => {
            /* morph replaces el */
          });
        };
        if (defer) {
          requestAnimationFrame(load);
        } else {
          const io = new IntersectionObserver((entries) => {
            if (entries.some((e) => e.isIntersecting)) {
              io.disconnect();
              load();
            }
          });
          io.observe(el);
        }
      }
      return;
    }
    el.__conduitBooted = true;
    el.__conduitSnapshot = snap;
    el.__wire = wireProxy(el, snap);
    bindDirectives(el, snap);
    applyClientBindings(el);
  }

  function bootAll(root) {
    (root || document).querySelectorAll("[wire\\:id], [data-conduit]").forEach(bootElement);
  }

  // wire:offline — show elements when navigator is offline
  function syncOffline() {
    const offline = !navigator.onLine;
    document.documentElement.toggleAttribute("data-conduit-offline", offline);
    document.querySelectorAll("[wire\\:offline]").forEach((n) => {
      n.style.display = offline ? "" : "none";
    });
    document.querySelectorAll("[wire\\:online]").forEach((n) => {
      n.style.display = offline ? "none" : "";
    });
  }
  window.addEventListener("online", syncOffline);
  window.addEventListener("offline", syncOffline);

  function entangle(el, snapshot, name) {
    return {
      get value() {
        return snapshot.serverMemo.data[name];
      },
      set value(v) {
        snapshot.serverMemo.data[name] = v;
        applyClientBindings(el);
        enqueue(el, snapshot, { updates: [[name, v]] });
      },
    };
  }

  document.addEventListener("alpine:init", () => {
    if (!window.Alpine) return;
    window.Alpine.magic("wire", (el) => {
      const root = el.closest("[wire\\:id]");
      return root && root.__wire ? root.__wire : {};
    });
    window.Alpine.magic("errors", (el) => {
      const root = el.closest("[wire\\:id]");
      return (root && root.__wireErrors) || {};
    });
  });

  // wire:navigate: intercept same-origin links (subpath-aware + View Transitions)
  document.addEventListener("click", (e) => {
    const a = e.target.closest && e.target.closest("[wire\\:navigate]");
    if (!a || a.target === "_blank") return;
    const href = a.getAttribute("href");
    if (!href || href.startsWith("#") || href.startsWith("mailto:")) return;
    e.preventDefault();
    const target = withBase(href);
    const go = () => {
      fetch(target, { headers: { "X-Conduit-Navigate": "true", Accept: "text/html" } })
        .then((r) => r.text())
        .then((html) => {
          const doc = new DOMParser().parseFromString(html, "text/html");
          const nextMain = doc.querySelector("[data-conduit-navigate]") || doc.body;
          const curMain = document.querySelector("[data-conduit-navigate]") || document.body;
          if (curMain && nextMain && curMain !== document.body) {
            curMain.innerHTML = nextMain.innerHTML;
          } else {
            document.body.innerHTML = doc.body.innerHTML;
          }
          document.title = doc.title;
          history.pushState({}, "", target);
          bootAll(document);
          syncOffline();
        });
    };
    if (document.startViewTransition) document.startViewTransition(go);
    else go();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      syncOffline();
      bootAll();
    });
  } else {
    syncOffline();
    bootAll();
  }

  window.Conduit = {
    boot: bootAll,
    csrfToken,
    enqueue,
    withBase,
    config: CONFIG,
    get endpoint() {
      return currentEndpoint();
    },
  };
})();
