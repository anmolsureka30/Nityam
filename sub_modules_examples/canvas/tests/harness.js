/* Drives REAL pointer events against REAL layout, then writes results into the
   page so a screenshot can show them. This exercises the whole path:
   annotate.js -> stroke -> gesture -> resolve.js -> packet. */
window.addEventListener('load', function () { setTimeout(run, 900); });

function pageOf(n){ return document.querySelector('.nb-page[data-page="'+n+'"]'); }
function overlayOf(n){ return pageOf(n).querySelector('.nb-overlay'); }

function drag(n, pts) {
  var ov = overlayOf(n);
  function ev(type, x, y) {
    ov.dispatchEvent(new PointerEvent(type, {clientX:x, clientY:y, pointerId:7, bubbles:true, cancelable:true}));
  }
  ev('pointerdown', pts[0][0], pts[0][1]);
  for (var i=1;i<pts.length;i++) ev('pointermove', pts[i][0], pts[i][1]);
  ev('pointerup', pts[pts.length-1][0], pts[pts.length-1][1]);
}

/* viewport-coordinate ring around an element, padded */
function ringAround(sel, pad, steps) {
  var r = document.querySelector(sel).getBoundingClientRect();
  var cx=r.left+r.width/2, cy=r.top+r.height/2;
  var rx=r.width/2+pad, ry=r.height/2+pad, pts=[];
  steps = steps||22;
  for (var i=0;i<=steps;i++){ var t=i/steps*Math.PI*2; pts.push([cx+rx*Math.cos(t), cy+ry*Math.sin(t)]); }
  return pts;
}
function swipeAcross(sel) {
  var r = document.querySelector(sel).getBoundingClientRect();
  var y = r.top + r.height/2, pts=[];
  for (var x=r.left-4; x<=r.right+4; x+=6) pts.push([x,y]);
  return pts;
}

var results = [];
function record(label, expectFn) {
  var p = window.nb.lastPacket();
  var verdict = expectFn(p);
  results.push({label:label, ok:verdict.ok, note:verdict.note, packet:p});
}

function run() {
  // ── 1. marker swipe over an equation term ────────────────────────────
  window.nb.goToPage(1);
  setTimeout(function(){
    nb.setTool('marker');
    drag(1, swipeAcross('[data-anchor="t_frac"]'));
    record('marker over (u sinθ)²/2g', function(p){
      var hit = p.resolved.some(function(r){return r.anchor==='t_frac';});
      return {ok: hit && p.confidence>0.5,
              note:'resolved=['+p.resolved.map(function(r){return r.anchor+'@'+r.coverage;}).join(', ')+
                   '] nearby=['+p.nearby.map(function(r){return r.anchor+'@'+r.coverage;}).join(', ')+
                   '] conf='+p.confidence};
    });

    // ── 2. tight circle around the uy vector in the SVG ────────────────
    nb.setTool('circle');
    drag(1, ringAround('[data-anchor="a_vec_uy"]', 6));
    record('circle around the u_y vector', function(p){
      var hit = p.resolved.some(function(r){return r.anchor==='a_vec_uy';});
      return {ok: hit, note:'resolved=['+p.resolved.map(function(r){return r.anchor+'@'+r.coverage;}).join(', ')+
             '] nearby=['+p.nearby.map(function(r){return r.anchor;}).join(', ')+']'};
    });

    // ── 3. circle in the empty margin ─────────────────────────────────
    var pg = pageOf(1).getBoundingClientRect();
    drag(1, (function(){var pts=[],cx=pg.right-34,cy=pg.top+120;
      for(var i=0;i<=20;i++){var t=i/20*Math.PI*2;pts.push([cx+16*Math.cos(t),cy+16*Math.sin(t)]);}return pts;})());
    record('circle in the empty margin', function(p){
      return {ok: p.resolved.length===0 && p.bbox!==null && p.gesture==='circle',
              note:'resolved='+p.resolved.length+' nearby='+p.nearby.length+' bbox ok='+(p.bbox!==null)};
    });

    // ── 4. circle the apex region of the raster image (tier 3 crop) ────
    nb.goToPage(2);
    setTimeout(function(){
      var img = pageOf(2).querySelector('.blk-img').getBoundingClientRect();
      var cx = img.left + 0.545*img.width, cy = img.top + 0.29*img.height;
      var pts=[]; for(var i=0;i<=22;i++){var t=i/22*Math.PI*2;
        pts.push([cx+0.075*img.width*Math.cos(t), cy+0.15*img.height*Math.sin(t)]);}
      nb.setTool('circle');
      drag(2, pts);
      record('circle the apex inside the image', function(p){
        var hit = p.resolved.some(function(r){return r.anchor==='r_apex';});
        return {ok: hit && !!p.crop,
                note:'resolved=['+p.resolved.map(function(r){return r.anchor;}).join(', ')+
                     '] crop='+(p.crop?Math.round(p.crop.length/1024)+'KB':'null')+' tier='+p.tier};
      });

      // ── 5. pointAt from the tutor stub ──────────────────────────────
      var okPoint = nb.pointAt('t_frac');
      var lit = !!document.querySelector('.tutor-point');
      results.push({label:'nb.pointAt("t_frac")', ok: okPoint && lit,
                    note:'returned '+okPoint+', element highlighted='+lit, packet:null});

      // ── 6. artifact coexistence, inside its shadow root ─────────────
      var holder = pageOf(3) && pageOf(3).querySelector('.blk-artifact');
      var shadow = holder && holder.shadowRoot;
      var sliders = shadow ? shadow.querySelectorAll('input[type=range]').length : 0;
      var styled  = shadow ? !!shadow.querySelector('style') : false;
      results.push({label:'embedded artifact mounted (shadow-encapsulated)',
                    ok: !!shadow && sliders>=2 && styled,
                    note:'shadowRoot='+!!shadow+', '+sliders+' sliders, own stylesheet='+styled, packet:null});

      // ── 7. persistence ──────────────────────────────────────────────
      var saved = JSON.parse(localStorage.getItem('nityam.canvas.'+DOC.notebook_id)||'{}');
      results.push({label:'strokes persisted to localStorage', ok:(saved.strokes||[]).length>=4,
                    note:(saved.strokes||[]).length+' strokes saved', packet:null});

      report();
    }, 700);
  }, 500);
}

function report() {
  var fails = results.filter(function(r){return !r.ok;}).length;
  var box = document.createElement('div');
  box.style.cssText='position:fixed;inset:0;background:#0f1216;color:#e8edf2;z-index:9999;'+
    'font:13px ui-monospace,Menlo,monospace;padding:26px 30px;overflow:auto;line-height:1.75';
  box.innerHTML = '<div style="font-size:16px;font-weight:700;margin-bottom:18px">'+
    'BROWSER GESTURE TEST — '+(fails?('FAIL ('+fails+')'):'PASS')+'</div>' +
    results.map(function(r){
      return '<div style="margin-bottom:11px">'+
        '<span style="color:'+(r.ok?'#4ade80':'#f87171')+';font-weight:700">'+(r.ok?'PASS':'FAIL')+'</span>  '+
        r.label+'<div style="color:#8b95a7;padding-left:56px">'+r.note+'</div></div>';
    }).join('');
  document.body.appendChild(box);
  console.log('GESTURE_TEST_RESULT ' + (fails?'FAIL':'PASS'));
}
