/* Drives the built app in headless Chrome over the DevTools protocol.
 *
 * No Puppeteer, no test runner — the same approach the adk and canvas
 * sub-modules use. It exists mainly to guard the grounding path, where a real
 * bug already hid: a horizontal marker drag has zero height, so scoring an
 * anchor by vertical overlap silently rejected every highlight and told the
 * student "not sure what you marked". That is the worst class of failure here,
 * because the student pointed at something and was ignored.
 *
 *   npm run build && node tests/ui.mjs
 */
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = process.env.NITYAM_SHOTS ?? tmpdir();
import { createServer } from "node:net";
const freePort = () => new Promise((r) => { const s = createServer(); s.unref(); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => r(port)); }); });
const APP = await freePort(), CDP = await freePort();
const sleep = ms => new Promise(r => setTimeout(r, ms));
const srv = spawn("npx", ["vite", "preview", "--port", String(APP), "--strictPort", "--host", "127.0.0.1"], { cwd: ROOT, stdio: "ignore" });
const profile = mkdtempSync(resolve(tmpdir(), "nity-v-"));
const CHROME = process.env.CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const chrome = spawn(CHROME,
  ["--headless=new", `--remote-debugging-port=${CDP}`, `--user-data-dir=${profile}`, "--no-first-run",
   "--disable-gpu", "--hide-scrollbars", "--window-size=1440,1000", "about:blank"], { stdio: "ignore" });
process.on("exit", () => { chrome.kill("SIGKILL"); srv.kill("SIGKILL"); });
for (let i=0;i<200;i++){try{if((await fetch(`http://127.0.0.1:${APP}/`)).ok)break;}catch{}await sleep(120);}
let url;for(let i=0;i<90;i++){try{const l=await (await fetch(`http://127.0.0.1:${CDP}/json/list`)).json();const p=l.find(t=>t.type==="page");if(p?.webSocketDebuggerUrl){url=p.webSocketDebuggerUrl;break;}}catch{}await sleep(150);}
let id=1;const pend=new Map();const ws=new WebSocket(url);
await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
ws.onmessage=({data})=>{const p=JSON.parse(data);const w=pend.get(p.id);if(w){pend.delete(p.id);p.error?w.reject(new Error(p.error.message)):w.resolve(p.result);}};
const send=(m,p={})=>new Promise((res,rej)=>{const i=id++;pend.set(i,{resolve:res,reject:rej});ws.send(JSON.stringify({id:i,method:m,params:p}));});
const ev=async e=>{const r=await send("Runtime.evaluate",{expression:`(()=>{${e}})()`,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description);return r.result.value;};
await send("Page.enable");await send("Runtime.enable");
const errs=[];ws.addEventListener("message",({data})=>{const p=JSON.parse(data);if(p.method==="Runtime.exceptionThrown")errs.push(p.params.exceptionDetails.text);});

let failed = 0;
const check=(n,ok,extra="")=>{ if(!ok) failed++; console.log(`${ok?"  ok  ":"  FAIL"} ${n}${extra?" — "+extra:""}`); };

await send("Page.navigate",{url:`http://127.0.0.1:${APP}/session`});
await sleep(1600);

const anchors = await ev("return [...document.querySelectorAll('[data-anchor]')].map(e=>({id:e.dataset.anchor,text:e.textContent}));");
check("anchors rendered", anchors.length === 3, JSON.stringify(anchors));

const svgH = await ev("const r=document.querySelector('svg')?.getBoundingClientRect(); return r? Math.round(r.height):0;");
check("simulation height is sane", svgH > 80 && svgH <= 210, `${svgH}px`);

const ghostLabels = await ev("return [...document.querySelectorAll('svg text')].map(t=>t.textContent);");
check("coincident ghosts share one label", ghostLabels.some(t=>t.includes("·")), JSON.stringify(ghostLabels));

// pick the marker, then drag across the equation
await ev("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Marker')).click(); return 1;");
await sleep(250);
const box = await ev("const m=[...document.querySelectorAll('[data-anchor]')].find(e=>e.textContent.includes('sin')); const r=m.getBoundingClientRect(); return {x:Math.round(r.left),y:Math.round(r.top+r.height/2),w:Math.round(r.width)};");
const drag = async (type,x,y) => send("Input.dispatchMouseEvent",{type,x,y,button:"left",buttons:1,pointerType:"mouse",clickCount:1});
await drag("mousePressed", box.x-6, box.y);
for (let i=0;i<=10;i++) await drag("mouseMoved", box.x-6 + (box.w+12)*i/10, box.y);
await drag("mouseReleased", box.x+box.w+6, box.y);
await sleep(500);

const marked = await ev("return document.body.innerText.includes('YOU MARKED ON THE PAGE') || document.body.innerText.includes('You marked on the page');");
check("marking the page produces a context panel", marked);
const summary = await ev("const el=[...document.querySelectorAll('*')].find(e=>e.children.length===0&&/^You marked \u201c/.test(e.textContent.trim())); return el?el.textContent.trim():null;");
check("the packet names what was marked", !!summary && /sin/.test(summary), summary ?? "none");
const conf = await ev("const t=document.body.innerText.match(/Confidence (\\d+)%/); return t?Number(t[1]):null;");
check("confidence is reported", conf !== null && conf > 30, `${conf}%`);

await ev("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Ask about this'))?.click(); return 1;");
await sleep(600);
const replied = await ev("const b=document.querySelector('[role=status]'); return b? b.innerText : '';");
check("the tutor answers about that exact term", /whole story|2θ = 90/.test(replied), replied.slice(0,90).replace(/\n/g,' '));

/* She can talk over the notebook, so her bubble has to be dismissable — and
   dismissing it must not lose the words, only fold them into the cloud. */
const said = replied;
await ev("document.querySelector('[aria-label=\"Minimise her words\"]').click(); return 1;");
await sleep(350);
const folded = await ev(`
  const cloud = document.querySelector('[aria-expanded="false"]');
  const bubble = [...document.querySelectorAll('[role=status]')].find(e => e.innerText.length > 40);
  const av = document.querySelector('canvas').getBoundingClientRect();
  if (!cloud) return { cloud: false };
  const r = cloud.getBoundingClientRect();
  return { cloud: true, bubbleGone: !bubble, w: Math.round(r.width), h: Math.round(r.height),
           aboveHer: r.bottom <= av.top + 40, visible: r.width > 0 && r.bottom < window.innerHeight };
`);
check("the bubble minimises to a cloud", folded.cloud && folded.bubbleGone,
      folded.cloud ? `cloud is ${folded.w}x${folded.h}` : "no cloud");
check("the cloud stays over her head", !!folded.aboveHer && !!folded.visible);

await ev("document.querySelector('[aria-expanded=\"false\"]').click(); return 1;");
await sleep(350);
const restored = await ev("const b=[...document.querySelectorAll('[role=status]')].find(e=>e.innerText.length>40); return b? b.innerText : '';");
check("clicking the cloud brings the same words back",
      restored.replace(/\s+/g,' ').includes(said.replace(/\s+/g,' ').slice(-40)),
      restored.slice(0,60).replace(/\n/g,' '));

// The rig draws on a canvas it clears each frame, so "is she there" means
// "are there non-transparent pixels", not "does the element exist".
const painted = await ev(`
  const c = document.querySelector('.nty-avatar canvas') || document.querySelector('canvas');
  if (!c) return { found: false };
  const g = c.getContext('2d');
  const d = g.getImageData(0, 0, c.width, c.height).data;
  let opaque = 0;
  for (let i = 3; i < d.length; i += 4) if (d[i] > 8) opaque++;
  return { found: true, w: c.width, h: c.height, coverage: opaque / (d.length / 4) };
`);
check("the avatar canvas is mounted", painted.found, painted.found ? `${painted.w}x${painted.h}` : "no canvas");
check("the avatar is actually drawn", painted.found && painted.coverage > 0.05,
      painted.found ? `${Math.round(painted.coverage * 100)}% of pixels painted` : "");
check("its background is transparent", painted.found && painted.coverage < 0.9,
      painted.found ? `${Math.round((1 - painted.coverage) * 100)}% clear` : "");

/* "It will talk" is the requirement, so test the mouth, not the element.
   Sample the lower third of the face across a second and check the pixels
   change — a frozen rig and a talking one look identical in a single frame. */
const sampleMouth = `
  const c = document.querySelector('canvas');
  const g = c.getContext('2d');
  const d = g.getImageData(Math.round(c.width * 0.32), Math.round(c.height * 0.42),
                           Math.round(c.width * 0.36), Math.round(c.height * 0.22)).data;
  let sum = 0;
  for (let i = 0; i < d.length; i += 4) sum += d[i] + d[i + 1] + d[i + 2];
  return sum;
`;
const frames = [];
for (let i = 0; i < 8; i++) { frames.push(await ev(sampleMouth)); await sleep(110); }
const distinct = new Set(frames).size;
check("the avatar animates while speaking", distinct >= 3,
      `${distinct} distinct frames out of ${frames.length}`);

// The canvas must have the page to itself.
const widths = await ev(`
  const sheet = document.querySelector('article');
  return { sheet: sheet ? Math.round(sheet.getBoundingClientRect().width) : 0, page: window.innerWidth };
`);
/* She stands in front of the page, so content CAN sit behind her. What must
   be true is that the student can always scroll it out from under her. */
const clearance = await ev(`
  const sc = document.querySelector('[class*="scroll"]');
  if (!sc) return { ok: false };
  // scroll-behavior is smooth, so assigning scrollTop animates; force it.
  sc.scrollTo({ top: sc.scrollHeight, behavior: 'instant' });
  return new Promise(r => setTimeout(() => {
    // The annotation overlay is absolutely positioned across the whole scroll
    // height, so it must not count as content.
    const blocks = [...sc.children].filter(el => getComputedStyle(el).position !== 'absolute');
    const lowest = Math.max(...blocks.map(b => b.getBoundingClientRect().bottom));
    const av = document.querySelector('canvas').getBoundingClientRect();
    r({ ok: true, lowest: Math.round(lowest), avatarTop: Math.round(av.top),
        scrolled: Math.round(sc.scrollTop),
        range: Math.round(sc.scrollHeight - sc.clientHeight) });
  }, 250));
`);
check("content can be scrolled clear of the avatar",
      clearance.ok && clearance.lowest < clearance.avatarTop,
      `scrolled ${clearance.scrolled}px; last line ends at ${clearance.lowest}px, she starts at ${clearance.avatarTop}px`);
check("there is scroll range to do it with", clearance.range > 200, `${clearance.range}px of scroll`);

check("the canvas spans the full width", widths.sheet / widths.page > 0.9,
      `${widths.sheet}px of ${widths.page}px`);

const shot = await send("Page.captureScreenshot",{format:"png",captureBeyondViewport:true});
writeFileSync(`${OUT}/fe_session2.png`, Buffer.from(shot.data,"base64"));

await send("Page.navigate",{url:`http://127.0.0.1:${APP}/`});
await sleep(1200);
const shot2 = await send("Page.captureScreenshot",{format:"png",captureBeyondViewport:true});
writeFileSync(`${OUT}/fe_home2.png`, Buffer.from(shot2.data,"base64"));

check("no uncaught page errors", errs.length === 0, errs.join(" | "));
console.log(failed ? `\n${failed} failed` : "\nall passed");
process.exit(failed ? 1 : 0);
