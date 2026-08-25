/* Headless DOM test. Requires node, no browser.
 *   node tests/dom.js
 * Stubs just enough document/canvas to mount the artifact for real, then drives
 * it like a student: drag the angle slider, watch the probes fire, let the
 * assessment gate open, answer it, switch theme, and check nothing was lost. */
const fs=require('fs'), vm=require('vm'), path=require('path');
const B=process.argv[2] || path.join(__dirname, "..");

// --- minimal DOM + canvas stub ------------------------------------------
function mkNode(tag){
  const n={tagName:tag, className:'', _text:'', children:[], style:{}, dataset:{},
    classList:null,
    appendChild(c){this.children.push(c); c.parentNode=this; return c},
    insertBefore(c,r){this.children.unshift(c); return c},
    removeChild(c){this.children=this.children.filter(x=>x!==c)},
    remove(){ if(this.parentNode) this.parentNode.removeChild(this) },
    setAttribute(k,v){ this['attr_'+k]=v }, getAttribute(k){ return this['attr_'+k] },
    offsetWidth:0, focus(){}, contains(){return false},
    querySelectorAll(sel){ const want=sel.replace(/^[.#]/,''); const out=[];
      const walk=n=>{ for(const c of n.children){ if((c.className||'').split(' ').includes(want)) out.push(c); walk(c);} };
      walk(this); return out },
    querySelector(sel){ const want=sel.replace(/^[.#]/,'');
      const walk=n=>{ for(const c of n.children){
        if((c.className||'').split(' ').includes(want)||c.id===want) return c;
        const r=walk(c); if(r) return r; } return null };
      return walk(this) },
    get firstChild(){ return this.children[0]||null },
    get textContent(){return this._text}, set textContent(v){this._text=String(v)},
    get innerHTML(){return this._html||''},
  set innerHTML(v){ this._html=v; this.children=[];
    if(v && v.indexOf('<span')>=0){ const sp=mkNode('span'); this.children.push(sp); sp.parentNode=this; } },
  get lastChild(){ return this.children[this.children.length-1]||null },
  };
  // real classList semantics: backed by className
  n.classList={ add(c){ const s=new Set((n.className||'').split(' ').filter(Boolean)); s.add(c); n.className=[...s].join(' ') },
                remove(c){ const s=new Set((n.className||'').split(' ').filter(Boolean)); s.delete(c); n.className=[...s].join(' ') },
                contains(c){ return (n.className||'').split(' ').includes(c) } };
  if(tag==='canvas'){ n.clientWidth=760; n.clientHeight=390; n.width=0; n.height=0;
    const grad={addColorStop(){}};
    n.getContext=()=>new Proxy({}, {get:(t,k)=>{
      if(k==='canvas') return n;
      if(k==='measureText') return ()=>({width:10});
      if(k==='createLinearGradient'||k==='createRadialGradient') return ()=>grad;
      return ()=>{};
    }, set:()=>true}); }
  return n;
}
const document={ createElement:mkNode, createTextNode:t=>({textContent:t, children:[]}) };
const rafQ=[];
const sandbox={window:{addEventListener(){},removeEventListener(){},devicePixelRatio:2,
  requestAnimationFrame(f){rafQ.push(f);return rafQ.length},cancelAnimationFrame(){}},
  document, console, Date, Math, JSON, setTimeout:(f)=>{f();return 1}, clearTimeout(){},
  requestAnimationFrame(f){rafQ.push(f);return rafQ.length}, cancelAnimationFrame(){},
  getComputedStyle:()=>({getPropertyValue:()=>'#2a78d6'}),
  Object, Array, String, Number, parseFloat};
sandbox.window.document=document;
sandbox.getComputedStyle=sandbox.getComputedStyle||(()=>({getPropertyValue:()=>'#2a78d6'}));
document.documentElement=mkNode('html');
vm.createContext(sandbox);
for(const f of ['kernel.js','evaluate.js','probes.js','render.js','mount.js'])
  vm.runInContext(fs.readFileSync(path.join(B,'runtime',f),'utf8'), sandbox, {filename:f});

const NS=sandbox.window.Nityam;
const {loadIR, drivePlan, expectedOnceEvents}=require('./lib.js');
const ir=loadIR(B);
const themes=JSON.parse(fs.readFileSync(path.join(B,'examples','themes.json'),'utf8'));
delete themes._comment;
const parity=JSON.parse(fs.readFileSync(path.join(B,'out','parity.json'),'utf8'));

const root=mkNode('div');
const evidence=[];
const h=NS.mountArtifact(ir, root, {themes, theme:'cricket', parity,
  onEvidence:e=>evidence.push(e), onParity:w=>console.log('  onParity callback fired, worst='+w)});
console.log('  mount OK  — DOM nodes built:', root.children.length);

// drive it exactly like a student would, whichever control this lesson is about
function findInputs(n, out=[]){ for(const c of n.children){ if(c.tagName==='input'&&c.type==='range') out.push(c); findInputs(c,out);} return out; }
const inputs=findInputs(root);
console.log('  sliders rendered:', inputs.length);
const plan=drivePlan(ir);
const sliderIdx=ir.controls.filter(c=>c.widget==='slider').findIndex(c=>c.id===plan.controlId);
const target=inputs[sliderIdx];
console.log('  driving:', plan.name, '->', plan.values.join(', '));
for(const v of plan.values){ target.value=v; target.oninput(); }
console.log('  evidence events after drag:', evidence.map(e=>e.event).join(', '));

// assessment should now be visible and answerable
function findButtons(n,out=[]){ for(const c of n.children){ if(c.tagName==='button') out.push(c); findButtons(c,out);} return out; }
const btns=findButtons(root).filter(b=>b.dataset && b.dataset.v!==undefined);
console.log('  assessment options rendered:', btns.map(b=>b.textContent).join(' '));
const q=ir.assessment[0];
if(btns.length){ btns.find(b=>parseFloat(b.dataset.v)===q.expected).onclick();
  console.log('  after answering 45°:', evidence[evidence.length-1].event,
              JSON.stringify(evidence[evidence.length-1].payload)); }

// theme switch must not lose state
h && console.log('  state before theme switch:', JSON.stringify(h.getState()));
const sel=(function find(n){ for(const c of n.children){ if(c.tagName==='select') return c; const r=find(c); if(r) return r;} return null})(root);
if(sel){ sel.value='spiderman'; sel.onchange(); console.log('  theme switched, state kept:', JSON.stringify(h.getState())); }

// after the theme switch the evidence stream and the answered checkpoint must survive
function countEvidenceRows(n,c=0){ for(const k of n.children){ if((k.className||'').split(' ').includes('ev')) c++; c=countEvidenceRows(k,c);} return c }
const rowsAfter=countEvidenceRows(root);
const btnsAfter=findButtons(root).filter(b=>b.dataset && b.dataset.v!==undefined);
const okMark=btnsAfter.some(b=>(b.className||'').split(' ').includes('ok'));
console.log('  after theme switch: evidence rows='+rowsAfter+'  (expected '+evidence.length+'), checkpoint restored='+okMark);

const ok = rowsAfter===evidence.length && okMark &&
           expectedOnceEvents(ir).every(w=>evidence.some(e=>e.event===w)) &&
           evidence.some(e=>e.event==='assessment.answered') && btns.length===q.options.length;
console.log('\n  DOM TEST: '+(ok?'PASS':'FAIL'));
process.exit(ok?0:1);
