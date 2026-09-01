import{L as re,D as St,n as ge,Q as Ct,R as je,S as _t,T as oe,F as Ge,H as Ve,I as kt,J as qe,N as Nt,U as At}from"./assets/extension-shared.js";(()=>{var Re,Ke,He;const V="browser-capture-v7",Je="incremento-browser-capture-root",ie=window.__incrementoContentScriptState&&typeof window.__incrementoContentScriptState=="object"?window.__incrementoContentScriptState:{};if(ie.version===V&&ie.ready)return;window.__incrementoContentScriptState={...ie,version:V,ready:!1},window.__incrementoContentScriptVersion=V;const ae="incremento_browser_capture_settings",W=50,Qe=0,Ze=100;let P=St,M=null;globalThis.__incrementoLastSelectedText=String(globalThis.__incrementoLastSelectedText||"").trim();function D(){var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();return e?(globalThis.__incrementoLastSelectedText=e,e):String(globalThis.__incrementoLastSelectedText||"").trim()}function be(e){const t=Number(e);return Number.isFinite(t)?Math.min(Ze,Math.max(Qe,Number(t.toFixed(4)))):W}function et(e){return Array.from(new Set(String(e||"").replaceAll(","," ").split(/\s+/).map(t=>t.trim()).filter(Boolean)))}function ye(e,t){const r=Array.isArray(t)?t.filter(Boolean):[],n=r[0]||"",i=o=>o===""?"":r.includes(o)?o:n;return{titleField:i(String((e==null?void 0:e.titleField)||"")),selectedTextField:i(String((e==null?void 0:e.selectedTextField)||"")),urlField:i(String((e==null?void 0:e.urlField)||"")),snapshotField:i(String((e==null?void 0:e.snapshotField)||""))}}function tt(e,t){const r=Array.isArray(t==null?void 0:t.noteTypes)?t.noteTypes:[],n=Array.isArray(t==null?void 0:t.deckNames)?t.deckNames.filter(Boolean):[],i=String((e==null?void 0:e.noteTypeName)||""),o=r.find(w=>(w==null?void 0:w.name)===i)||r[0]||null,a=(o==null?void 0:o.name)||"",l=Array.isArray(o==null?void 0:o.fields)?o.fields:[],c=e!=null&&e.mappingsByNoteType&&typeof e.mappingsByNoteType=="object"?e.mappingsByNoteType:{},p=ye(c[a],l),m=String((e==null?void 0:e.deckName)||""),T=n.includes(m)?m:n[0]||"Default";return{noteTypeName:a,deckName:T,priority:be(e==null?void 0:e.priority),tagsText:String((e==null?void 0:e.tagsText)||""),fieldMappings:p,mappingsByNoteType:c}}function z(e,t,r){return{...e,noteTypeName:t,fieldMappings:{...r},mappingsByNoteType:{...(e==null?void 0:e.mappingsByNoteType)||{},[t]:{...r}}}}function xe(e,t){var r,n,i,o;return{url:String((e==null?void 0:e.url)||"").trim(),title:String((e==null?void 0:e.title)||"").trim()||String((e==null?void 0:e.url)||"").trim()||"Untitled",selectedText:String((e==null?void 0:e.selectedText)||"").trim(),noteTypeName:String((t==null?void 0:t.noteTypeName)||"").trim(),deckName:String((t==null?void 0:t.deckName)||"").trim(),tags:et(t==null?void 0:t.tagsText),priority:be(t==null?void 0:t.priority),fieldMappings:{titleField:String(((r=t==null?void 0:t.fieldMappings)==null?void 0:r.titleField)||"").trim(),selectedTextField:String(((n=t==null?void 0:t.fieldMappings)==null?void 0:n.selectedTextField)||"").trim(),urlField:String(((i=t==null?void 0:t.fieldMappings)==null?void 0:i.urlField)||"").trim(),snapshotField:String(((o=t==null?void 0:t.fieldMappings)==null?void 0:o.snapshotField)||"").trim()},snapshots:Array.isArray(e==null?void 0:e.snapshots)?e.snapshots.map((a,l)=>({mimeType:"image/png",filename:String((a==null?void 0:a.filename)||`browser-capture-${l+1}.png`),base64:String((a==null?void 0:a.base64)||"").trim()})).filter(a=>a.base64):[]}}function E(e){const t=document.getElementById("incremento-video-time-toast");t&&t.remove();const r=document.createElement("div");r.id="incremento-video-time-toast",r.textContent=String(e||""),Object.assign(r.style,{position:"fixed",zIndex:2147483647,top:"10px",right:"10px",maxWidth:"320px",padding:"10px 14px",background:"rgba(0, 0, 0, 0.86)",color:"#fff",fontSize:"13px",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"6px",boxShadow:"0 2px 8px rgba(0, 0, 0, 0.4)",opacity:"0",transition:"opacity 0.2s ease"}),document.documentElement.appendChild(r),requestAnimationFrame(()=>{r.style.opacity="1"}),setTimeout(()=>{r.style.opacity="0",setTimeout(()=>r.remove(),220)},2400)}async function nt(){try{const e=await chrome.storage.local.get(re);P=ge(e==null?void 0:e[re])}catch{P=ge(null)}}function Ee(e){var i,o;const t=e instanceof Element?e:(e==null?void 0:e.parentElement)||null,r=(i=t==null?void 0:t.closest)==null?void 0:i.call(t,"a[href]");if(!r)return null;const n=String(r.href||((o=r.getAttribute)==null?void 0:o.call(r,"href"))||"").trim();return Ve(n)?r:null}function we(e){var r;if(!e)return null;const t=String(e.href||((r=e.getAttribute)==null?void 0:r.call(e,"href"))||"").trim();return Ve(t)?{url:t,title:kt(e.textContent||"",t)}:null}function rt(){let e=document.getElementById("incremento-tracking-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-tracking-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483646,top:"52px",right:"10px",display:"none",alignItems:"center",gap:"8px",padding:"8px 12px",background:"linear-gradient(135deg, rgba(10, 34, 64, 0.94), rgba(17, 83, 126, 0.94))",color:"#fff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",letterSpacing:"0.08em",textTransform:"uppercase",borderRadius:"999px",boxShadow:"0 4px 14px rgba(0, 0, 0, 0.28)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"none"});const t=document.createElement("span");t.textContent="●",Object.assign(t.style,{color:"#53f2a5",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(83, 242, 165, 0.85)"}),e.appendChild(t);const r=document.createElement("span");r.textContent="⚠",Object.assign(r.style,{color:"#ffd166",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(255, 209, 102, 0.55)"}),e.appendChild(r);const n=document.createElement("span");return n.id="incremento-tracking-badge-label",n.textContent="Tracking",e.appendChild(n),document.documentElement.appendChild(e),e}function O(e,t=""){const r=rt(),n=document.getElementById("incremento-tracking-badge-label");if(!(!r||!n)){if(!e){r.style.display="none";return}n.textContent=t==="web"?"Tracking Web Card":"Tracking",r.style.display="inline-flex"}}function Te(e){const t=Math.max(0,Math.floor(Number(e)||0)),r=Math.floor(t/3600),n=Math.floor(t%3600/60),i=t%60;return r>0?`${r}:${String(n).padStart(2,"0")}:${String(i).padStart(2,"0")}`:`${n}:${String(i).padStart(2,"0")}`}function ot(){let e=document.getElementById("incremento-browser-media-ref-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-browser-media-ref-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483645,top:"96px",right:"10px",display:"none",alignItems:"center",gap:"8px",maxWidth:"320px",padding:"9px 12px",background:"linear-gradient(135deg, rgba(28, 32, 48, 0.96), rgba(34, 62, 96, 0.96))",color:"#eef5ff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"14px",boxShadow:"0 5px 18px rgba(0, 0, 0, 0.30)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"auto"});const t=document.createElement("span");t.textContent="▶",Object.assign(t.style,{color:"#8fd3ff",fontSize:"11px",lineHeight:"1"}),e.appendChild(t);const r=document.createElement("span");r.id="incremento-browser-media-ref-badge-label",r.textContent="",Object.assign(r.style,{flex:"1 1 auto",minWidth:"0"}),e.appendChild(r);const n=document.createElement("button");return n.type="button",n.textContent="×",n.setAttribute("aria-label","Dismiss saved browser time badge"),Object.assign(n.style,{appearance:"none",border:"0",background:"transparent",color:"#a9bfdc",cursor:"pointer",fontSize:"16px",fontWeight:"700",lineHeight:"1",padding:"0 0 0 4px",margin:"0",pointerEvents:"auto"}),n.addEventListener("click",i=>{i.preventDefault(),i.stopPropagation(),ee=!0,e.style.display="none"}),e.appendChild(n),document.documentElement.appendChild(e),e}function R(e){const t=ot(),r=document.getElementById("incremento-browser-media-ref-badge-label");if(!t||!r)return;if(!!!(e!=null&&e.hasReference)){t.style.display="none";return}if(ee)return;const i=String((e==null?void 0:e.timeText)||Te(e==null?void 0:e.seconds));r.textContent=i?`Last saved ${i}`:"Last saved",t.style.display="inline-flex"}function K(){try{return(chrome==null?void 0:chrome.runtime)||null}catch{return null}}nt();try{(Ke=(Re=chrome==null?void 0:chrome.storage)==null?void 0:Re.onChanged)==null||Ke.addListener((e,t)=>{var r;t!=="local"||!e||!Object.prototype.hasOwnProperty.call(e,re)||(P=ge((r=e[re])==null?void 0:r.newValue))})}catch{}try{const e=K();(He=e==null?void 0:e.onMessage)==null||He.addListener((t,r,n)=>{var i;if(!t||!t.type)return!1;if(t.type==="SHOW_TOAST")return E(t.text||""),n==null||n({ok:!0}),!1;if(t.type==="TRIGGER_BROWSER_CAPTURE"){if(String(t.mode||"").trim().toLowerCase()==="snapshot")return J(),n==null||n({ok:!0}),!1;const a=D();return a?(Q({mode:"selection",selectedText:a,snapshots:[]}).then(()=>n==null?void 0:n({ok:!0}),l=>{E((l==null?void 0:l.message)||"Failed to open browser capture."),S(),n==null||n({ok:!1,error:String((l==null?void 0:l.message)||"")})}),!0):(E("Select text on the page first."),n==null||n({ok:!1}),!1)}if(t.type==="GET_PAGE_CONTEXT"){const o={html:((i=document.documentElement)==null?void 0:i.outerHTML)||"",selectionText:D(),title:document.title||"",url:window.location.href||""},a=Ct(o);return a.ok?(n==null||n({ok:!0,...o}),!1):(n==null||n(a),!1)}if(t.type==="GET_CONTEXT_LINK_INFO")return n==null||n({ok:!0,url:String((M==null?void 0:M.url)||""),title:String((M==null?void 0:M.title)||"")}),!1;if(t.type==="GET_CURRENT_MEDIA_CONTEXT")return n==null||n(vt()),!1;if(t.type==="APPLY_MEDIA_RESUME"){const o=de(t.seconds);return n==null||n({ok:o}),!1}return t.type==="UPDATE_BROWSER_MEDIA_REF_BADGE"&&(ee=!1,R(t.reference||null),n==null||n({ok:!0})),!1})}catch{}let g=null,u=null;function H(e){return new Promise((t,r)=>{const n=K();if(!(n!=null&&n.sendMessage)){r(new Error("Incremento extension runtime is unavailable."));return}n.sendMessage(e,i=>{const o=chrome.runtime.lastError;if(o){r(new Error(o.message||"Extension request failed."));return}t(i||null)})})}async function ve(){const e=await H({type:"LOAD_BROWSER_CAPTURE_META"});if(!(e!=null&&e.ok))throw new Error(String((e==null?void 0:e.error)||"Failed to load browser capture metadata."));return e}async function Se(e){const t=await H({type:"SUBMIT_BROWSER_CAPTURE",payload:e});if(!(t!=null&&t.ok))throw new Error(String((t==null?void 0:t.error)||"Failed to submit browser capture."));return t}async function it(){const e=await H({type:"CAPTURE_VISIBLE_TAB"});if(!(e!=null&&e.ok)||!(e!=null&&e.dataUrl))throw new Error(String((e==null?void 0:e.error)||"Failed to capture the current tab."));return e.dataUrl}async function Ce(e){let t={};try{const r=await chrome.storage.local.get(ae);t=(r==null?void 0:r[ae])||{}}catch{t={}}return tt(t,e)}async function _e(e){try{await chrome.storage.local.set({[ae]:{noteTypeName:String((e==null?void 0:e.noteTypeName)||""),deckName:String((e==null?void 0:e.deckName)||""),priority:Number((e==null?void 0:e.priority)??W),tagsText:String((e==null?void 0:e.tagsText)||""),mappingsByNoteType:(e==null?void 0:e.mappingsByNoteType)||{}}})}catch{}}async function ke(e="",t=[]){const r=(u==null?void 0:u.meta)||await ve();if(!Array.isArray(r==null?void 0:r.noteTypes)||r.noteTypes.length===0)throw new Error("No note types are available in Anki.");if(!Array.isArray(r==null?void 0:r.deckNames)||r.deckNames.length===0)throw new Error("No decks are available in Anki.");const n=(u==null?void 0:u.form)||await Ce(r);return u={mode:"snapshot",meta:r,form:n,context:{url:window.location.href||"",title:document.title||"",selectedText:je("snapshot",e,D())},snapshots:Array.isArray(t)?t:[],statusKind:"",statusText:"",submitting:!1},u}async function at(e="",t=[]){const r=await ke(e,t),n=xe({...r.context,snapshots:r.snapshots.map(a=>({filename:a.filename,base64:a.base64}))},r.form),i=Ge(n);if(!i.ok)throw new Error(`${i.error} Open Continue once to choose the destination fields for snapshot capture.`);const o=await Se(n);return await _e(r.form),o}function Ne(e){const t=e instanceof Element?e:(e==null?void 0:e.parentElement)||null;return t?t.closest("input, textarea, select")?!0:!!t.closest('[contenteditable=""], [contenteditable="true"]'):!1}function le(){return!!g}function lt(e){return String((e==null?void 0:e.code)||"").toLowerCase()==="keyx"}function ce(e){const t=g==null?void 0:g.shell,r=e==null?void 0:e.target;if(!(!t||!(r instanceof Node)||!t.contains(r))){if(e.key==="Escape"){e.preventDefault(),e.stopPropagation(),S();return}e.stopPropagation()}}function q(){if(g)return g;const e=document.createElement("div");e.id=Je,e.style.all="initial";const t=e.attachShadow({mode:"open"});document.documentElement.appendChild(e),t.addEventListener("keydown",ce,!0),t.addEventListener("keypress",ce,!0),t.addEventListener("keyup",ce,!0);const r=document.createElement("style");r.textContent=`
      :host { all: initial; }
      *, *::before, *::after { box-sizing: border-box; }
      .shell {
        position: fixed;
        inset: 0;
        z-index: 2147483645;
        font-family: "Avenir Next", "Segoe UI", sans-serif;
        color: #1f2328;
      }
      .backdrop {
        position: absolute;
        inset: 0;
        background: rgba(12, 18, 26, 0.42);
      }
      .panel {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        width: min(760px, calc(100vw - 32px));
        max-height: calc(100vh - 32px);
        overflow: auto;
        border-radius: 24px;
        border: 1px solid rgba(90, 74, 47, 0.18);
        background:
          radial-gradient(circle at top left, rgba(255, 219, 161, 0.7), transparent 42%),
          linear-gradient(170deg, rgba(255, 251, 244, 0.98), rgba(245, 236, 223, 0.97));
        box-shadow: 0 28px 80px rgba(22, 23, 25, 0.32);
        padding: 22px;
      }
      .capture-shell {
        position: absolute;
        inset: 0;
        cursor: crosshair;
      }
      .capture-toolbar {
        position: absolute;
        top: 14px;
        left: 50%;
        transform: translateX(-50%);
        display: flex;
        align-items: center;
        gap: 10px;
        min-width: min(860px, calc(100vw - 24px));
        max-width: calc(100vw - 24px);
        padding: 12px 14px;
        border-radius: 18px;
        background: rgba(17, 25, 34, 0.92);
        color: #fff;
        box-shadow: 0 16px 34px rgba(0, 0, 0, 0.3);
      }
      .capture-toolbar strong {
        font-size: 13px;
        letter-spacing: 0.05em;
        text-transform: uppercase;
      }
      .capture-toolbar span {
        font-size: 13px;
        opacity: 0.82;
      }
      .capture-toolbar .spacer {
        flex: 1;
      }
      .toolbar-btn,
      .primary-btn,
      .secondary-btn,
      .ghost-btn {
        border: 0;
        border-radius: 13px;
        padding: 10px 14px;
        font: inherit;
        cursor: pointer;
      }
      .toolbar-btn {
        background: rgba(255, 255, 255, 0.12);
        color: #fff;
      }
      .toolbar-btn.primary {
        background: linear-gradient(135deg, #b86a17, #e0932f);
      }
      .eyebrow {
        margin: 0 0 6px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #8f5a1e;
      }
      h2 {
        margin: 0 0 12px;
        font-size: 24px;
        line-height: 1.08;
      }
      .lead, .status, .field-note {
        margin: 0;
        font-size: 13px;
        line-height: 1.45;
        color: #5c5b57;
      }
      .status.error { color: #ab2f2f; }
      .status.success { color: #216c3f; }
      .grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
        margin-top: 16px;
      }
      .field {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .field.full { grid-column: 1 / -1; }
      .field label {
        font-size: 12px;
        font-weight: 700;
        color: #433720;
      }
      .field input,
      .field textarea,
      .field select {
        width: 100%;
        border: 1px solid rgba(82, 68, 45, 0.18);
        border-radius: 13px;
        background: rgba(255, 255, 255, 0.9);
        padding: 11px 12px;
        font: inherit;
        color: inherit;
      }
      .field textarea {
        min-height: 110px;
        resize: vertical;
      }
      .field input[type="range"] {
        padding: 0;
      }
      .field input:focus,
      .field textarea:focus,
      .field select:focus {
        outline: 2px solid rgba(184, 106, 23, 0.2);
        border-color: rgba(184, 106, 23, 0.38);
      }
      .snapshots {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 10px;
      }
      .snapshot-card {
        overflow: hidden;
        border: 1px solid rgba(82, 68, 45, 0.14);
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.72);
      }
      .snapshot-card img {
        display: block;
        width: 100%;
        height: 108px;
        object-fit: cover;
        background: #e8dfd2;
      }
      .snapshot-footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        padding: 8px 10px 10px;
      }
      .snapshot-footer span {
        font-size: 12px;
        color: #4d4b46;
      }
      .snapshot-footer button {
        border: 0;
        border-radius: 10px;
        padding: 6px 8px;
        background: rgba(171, 47, 47, 0.1);
        color: #8f2222;
        font: inherit;
        cursor: pointer;
      }
      .actions {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 10px;
        margin-top: 18px;
      }
      .primary-btn {
        background: linear-gradient(135deg, #9e5d12 0%, #d88219 100%);
        color: #fffdf8;
        font-weight: 700;
      }
      .secondary-btn {
        background: rgba(88, 73, 44, 0.09);
        color: #473a24;
        font-weight: 600;
      }
      .ghost-btn {
        background: rgba(88, 73, 44, 0.08);
        color: #473a24;
      }
      .selection-rect {
        position: absolute;
        border: 2px solid rgba(255, 171, 64, 0.96);
        background: rgba(255, 193, 101, 0.2);
        box-shadow: 0 0 0 1px rgba(20, 20, 20, 0.24), 0 12px 32px rgba(0, 0, 0, 0.16);
      }
      .selection-rect::after {
        content: attr(data-label);
        position: absolute;
        top: -26px;
        left: 0;
        padding: 4px 8px;
        border-radius: 999px;
        background: rgba(17, 25, 34, 0.9);
        color: #fff;
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }
      @media (max-width: 720px) {
        .grid {
          grid-template-columns: 1fr;
        }
        .panel {
          width: calc(100vw - 16px);
          padding: 18px;
        }
        .capture-toolbar {
          flex-wrap: wrap;
          justify-content: center;
        }
        .capture-toolbar .spacer {
          display: none;
        }
      }
    `,t.appendChild(r);const n=document.createElement("div");return n.className="shell",t.appendChild(n),g={host:e,shadow:t,shell:n},g}function S(){var e;(e=g==null?void 0:g.host)!=null&&e.isConnected&&g.host.remove(),g=null,u=null}function Ae(){const e=q();e.shell.textContent=""}function ct(e,t){const r=document.createElement("div");r.className="snapshots";for(const n of t){const i=document.createElement("div");i.className="snapshot-card";const o=document.createElement("img");o.src=n.dataUrl,o.alt=n.filename,i.appendChild(o);const a=document.createElement("div");a.className="snapshot-footer";const l=document.createElement("span");l.textContent=n.filename,a.appendChild(l);const c=document.createElement("button");c.type="button",c.textContent="Remove",c.addEventListener("click",()=>{u.snapshots=u.snapshots.filter(p=>p.id!==n.id),U()}),a.appendChild(c),i.appendChild(a),r.appendChild(i)}return r}async function U(){var Ye;const e=q(),{shell:t,shadow:r}=e,n=u;Ae();const i=document.createElement("div");i.className="backdrop",i.addEventListener("click",()=>S()),t.appendChild(i);const o=document.createElement("section");o.className="panel",t.appendChild(o);const a=document.createElement("p");a.className="eyebrow",a.textContent=n.mode==="snapshot"?"Browser snapshot":"Browser selection",o.appendChild(a);const l=document.createElement("h2");l.textContent="Send capture to Anki",o.appendChild(l);const c=document.createElement("p");c.className="lead",c.textContent=n.mode==="snapshot"?`${n.snapshots.length} snapshot${n.snapshots.length===1?"":"s"} ready from ${n.context.url}`:`Selected text from ${n.context.url}`,o.appendChild(c);const p=document.createElement("form");p.noValidate=!0;const m=document.createElement("div");m.className="grid",p.appendChild(m);const T=(s,h,x=!1,b="")=>{const B=document.createElement("div");B.className=`field${x?" full":""}`;const Xe=document.createElement("label");if(Xe.textContent=s,B.appendChild(Xe),B.appendChild(h),b){const he=document.createElement("p");he.className="field-note",he.textContent=b,B.appendChild(he)}return B},w=document.createElement("select");for(const s of n.meta.noteTypes){const h=document.createElement("option");h.value=s.name,h.textContent=s.name,w.appendChild(h)}w.value=n.form.noteTypeName,w.addEventListener("change",()=>{var x;const s=n.meta.noteTypes.find(b=>b.name===w.value),h=ye((x=n.form.mappingsByNoteType)==null?void 0:x[w.value],(s==null?void 0:s.fields)||[]);n.form=z(n.form,w.value,h),U()}),m.appendChild(T("Note type",w));const L=document.createElement("select");for(const s of n.meta.deckNames){const h=document.createElement("option");h.value=s,h.textContent=s,L.appendChild(h)}L.value=n.form.deckName,L.addEventListener("change",()=>{n.form.deckName=L.value}),m.appendChild(T("Deck",L));const N=document.createElement("input");N.type="text",N.value=n.form.tagsText,N.placeholder="tag-one tag-two",N.addEventListener("input",()=>{n.form.tagsText=N.value}),m.appendChild(T("Tags",N,!0));const C=document.createElement("div");C.style.display="grid",C.style.gridTemplateColumns="1fr auto",C.style.gap="10px",C.style.alignItems="center";const d=document.createElement("input");d.type="range",d.min="0",d.max="100",d.step="0.1",d.value=String(n.form.priority??W);const f=document.createElement("input");f.type="number",f.min="0",f.max="100",f.step="0.1",f.style.width="92px",f.value=String(n.form.priority??W);const y=s=>{const h=Number(s),x=Number.isFinite(h)?Math.min(100,Math.max(0,h)):W;n.form.priority=Number(x.toFixed(4)),d.value=String(n.form.priority),f.value=String(n.form.priority)};d.addEventListener("input",()=>y(d.value)),f.addEventListener("change",()=>y(f.value)),C.appendChild(d),C.appendChild(f),m.appendChild(T("Priority",C));const A=["",...((Ye=n.meta.noteTypes.find(s=>s.name===n.form.noteTypeName))==null?void 0:Ye.fields)||[]],_=(s,h)=>{const x=document.createElement("select");for(const b of A){const B=document.createElement("option");B.value=b,B.textContent=b||"Do not insert",x.appendChild(B)}return x.value=A.includes(s)?s:"",x.addEventListener("change",()=>{h(x.value)}),x},F=!!n.context.selectedText;m.appendChild(T("Page title field",_(n.form.fieldMappings.titleField,s=>{n.form=z(n.form,n.form.noteTypeName,{...n.form.fieldMappings,titleField:s})}),!1,"The current page title is always available. First-field mappings get a unique snapshot suffix.")),m.appendChild(T("Selected text field",_(n.form.fieldMappings.selectedTextField,s=>{n.form=z(n.form,n.form.noteTypeName,{...n.form.fieldMappings,selectedTextField:s})}),!1,F?`${n.context.selectedText.length} chars ready for insertion.`:"No text added yet.")),m.appendChild(T("Source URL field",_(n.form.fieldMappings.urlField,s=>{n.form=z(n.form,n.form.noteTypeName,{...n.form.fieldMappings,urlField:s})}),!1,"The current page URL is always available.")),m.appendChild(T("Snapshot field",_(n.form.fieldMappings.snapshotField,s=>{n.form=z(n.form,n.form.noteTypeName,{...n.form.fieldMappings,snapshotField:s})}),!0,n.snapshots.length>0?`${n.snapshots.length} snapshot${n.snapshots.length===1?"":"s"} selected.`:"No snapshot images in this capture."));const v=document.createElement("textarea");if(v.value=n.context.selectedText,v.placeholder=n.mode==="snapshot"?"Add text to store with these snapshots...":"Selected text will appear here. You can edit it before saving.",v.addEventListener("input",()=>{n.context.selectedText=v.value}),m.appendChild(T(n.mode==="snapshot"?"Text to add":"Selected text",v,!0,"This content is inserted into the selected text field if one is chosen.")),n.snapshots.length>0){const s=document.createElement("div");s.className="field full";const h=document.createElement("label");h.textContent="Snapshots",s.appendChild(h),s.appendChild(ct(r,n.snapshots)),m.appendChild(s)}const fe=document.createElement("p");fe.className=`status${n.statusKind?` ${n.statusKind}`:""}`,fe.textContent=n.statusText,p.appendChild(fe);const X=document.createElement("div");if(X.className="actions",n.snapshots.length>0){const s=document.createElement("button");s.type="button",s.className="ghost-btn",s.textContent="Capture more",s.addEventListener("click",()=>J(n.snapshots)),X.appendChild(s)}const j=document.createElement("button");j.type="button",j.className="secondary-btn",j.textContent="Cancel",j.addEventListener("click",()=>S()),X.appendChild(j);const G=document.createElement("button");G.type="submit",G.className="primary-btn",G.textContent=n.submitting?"Saving...":"Create note",G.disabled=!!n.submitting,X.appendChild(G),p.appendChild(X),p.addEventListener("submit",async s=>{if(s.preventDefault(),n.submitting)return;const h=xe({...n.context,snapshots:n.snapshots.map(b=>({filename:b.filename,base64:b.base64}))},n.form),x=Ge(h);if(!x.ok){n.statusKind="error",n.statusText=x.error,U();return}n.submitting=!0,n.statusKind="",n.statusText="Creating note in Anki...",U();try{const b=await Se(h);await _e(n.form),E(`Created ${b.noteTypeName} note in ${b.deckName}.`),S()}catch(b){n.submitting=!1,n.statusKind="error",n.statusText=(b==null?void 0:b.message)||"Failed to create note.",U()}}),o.appendChild(p)}function st(e){return new Promise((t,r)=>{const n=new Image;n.onload=()=>t(n),n.onerror=()=>r(new Error("Failed to decode screenshot.")),n.src=e})}async function dt(e,t){const r=await st(e),n=r.width/window.innerWidth,i=r.height/window.innerHeight,o=Math.max(0,Math.round(t.x*n)),a=Math.max(0,Math.round(t.y*i)),l=Math.max(1,Math.round(t.width*n)),c=Math.max(1,Math.round(t.height*i)),p=document.createElement("canvas");return p.width=l,p.height=c,p.getContext("2d").drawImage(r,o,a,l,c,0,0,l,c),p.toDataURL("image/png")}function ut(e){const t=String(e||""),r=t.indexOf(",");return r>=0?t.slice(r+1):t}function se(e){const t=Math.abs(e.width),r=Math.abs(e.height);return{x:e.width>=0?e.x:e.x-t,y:e.height>=0?e.y:e.y-r,width:t,height:r}}function Be(e=2){return new Promise(t=>{const r=Math.max(1,Number(e)||1);let n=0;const i=()=>{if(n+=1,n>=r){t();return}requestAnimationFrame(i)};requestAnimationFrame(i)})}function pt(e,t){if(!(e instanceof Element))return!1;const r=window.getComputedStyle(e),n=t==="x"?r.overflowX:r.overflowY;return/(auto|scroll|overlay)/.test(String(n||""))?t==="x"?e.scrollWidth>e.clientWidth:e.scrollHeight>e.clientHeight:!1}function Le(e,t){let r=e instanceof Element?e:null;for(;r;){if(pt(r,t))return r;r=r.parentElement}const n=document.scrollingElement;return n instanceof Element?n:document.documentElement}function mt(e,t){var p;if(!e)return;const r=((p=t==null?void 0:t.style)==null?void 0:p.pointerEvents)||"";t!=null&&t.style&&(t.style.pointerEvents="none");let n=null;try{n=document.elementFromPoint(e.clientX,e.clientY)}finally{t!=null&&t.style&&(t.style.pointerEvents=r)}const i=Number(e.deltaX)||0,o=Number(e.deltaY)||0,a=i?Le(n,"x"):null,l=o?Le(n,"y"):null,c=document.scrollingElement instanceof Element?document.scrollingElement:document.documentElement;i&&(a||c).scrollBy({left:i,top:0,behavior:"auto"}),o&&(l||c).scrollBy({left:0,top:o,behavior:"auto"})}async function ft(e,t=[]){if(t.length>=oe)throw new Error(`Too many snapshots. Maximum is ${oe}.`);const r=q();r.shell.style.display="none";try{await Be(2);const n=await it(),i=qe(n,{maxBytes:Nt});if(!i.ok)throw new Error(i.error);const o=se(e),a=await dt(n,o),l=qe(a,{maxBytes:At});if(!l.ok)throw new Error(l.error);return{id:`${Date.now()}-${t.length}-${Math.random().toString(16).slice(2,8)}`,filename:`browser-capture-${t.length+1}.png`,dataUrl:a,base64:ut(a)}}catch(n){throw new Error((n==null?void 0:n.message)||"Failed to capture the current tab.")}finally{g!=null&&g.shell&&(g.shell.style.display="",await Be(1))}}function J(e=[]){var C;const t=q();Ae();const r=e.length>0&&((C=u==null?void 0:u.context)==null?void 0:C.selectedText)||"";u={mode:"snapshot",meta:(u==null?void 0:u.meta)||null,form:(u==null?void 0:u.form)||null,context:{url:window.location.href||"",title:document.title||"",selectedText:r},snapshots:[...e],statusKind:"",statusText:"",submitting:!1};const n=t.shell,i=document.createElement("div");i.className="capture-shell",n.appendChild(i);const o=document.createElement("div");o.className="capture-toolbar",o.innerHTML=`
      <strong>Snapshot Mode</strong>
      <span>Draw one or more rectangles on the page. The capture is limited to the current viewport.</span>
      <span class="spacer"></span>
    `,n.appendChild(o);const a=[...e];let l=null,c=null,p=!1;const m=()=>{o.innerHTML=`
        <strong>Snapshot Mode</strong>
        <span>Draw a rectangle to capture it immediately, then scroll and capture another area if needed.</span>
        <span class="spacer"></span>
      `;const d=document.createElement("span");d.textContent=p?"Capturing...":`${a.length} snapshot${a.length===1?"":"s"} ready`,o.appendChild(d);const f=document.createElement("button");f.type="button",f.className="toolbar-btn",f.textContent="Undo",f.disabled=p||a.length===0,f.addEventListener("click",()=>{a.pop(),m()}),o.appendChild(f);const y=document.createElement("button");y.type="button",y.className="toolbar-btn",y.textContent="Clear",y.disabled=p||a.length===0,y.addEventListener("click",()=>{a.splice(0,a.length),m()}),o.appendChild(y);const $=document.createElement("button");$.type="button",$.className="toolbar-btn",$.textContent="Cancel",$.addEventListener("click",()=>S()),o.appendChild($);const A=document.createElement("button");A.type="button",A.className="toolbar-btn",A.textContent="Extract now",A.disabled=p||a.length===0,A.addEventListener("click",async()=>{var F;if(!p){if(!a.length){E("Draw at least one region first.");return}p=!0,m();try{const v=await at(((F=u==null?void 0:u.context)==null?void 0:F.selectedText)||"",[...a]);E(`Created ${v.noteTypeName} note in ${v.deckName}.`),S()}catch(v){p=!1,m(),E((v==null?void 0:v.message)||"Failed to create note.")}}}),o.appendChild(A);const _=document.createElement("button");_.type="button",_.className="toolbar-btn primary",_.textContent="Continue",_.addEventListener("click",()=>{var F;if(!p){if(!a.length){E("Draw at least one region first.");return}Q({mode:"snapshot",selectedText:((F=u==null?void 0:u.context)==null?void 0:F.selectedText)||"",snapshots:[...a]})}}),o.appendChild(_)},T=(d,f)=>{if(a.length>=oe){E(`Too many snapshots. Maximum is ${oe}.`);return}c={x:d,y:f,width:0,height:0},l=document.createElement("div"),l.className="selection-rect",l.dataset.label=`Capture ${a.length+1}`,i.appendChild(l)},w=()=>{if(!l||!c)return;const d=se(c);Object.assign(l.style,{left:`${d.x}px`,top:`${d.y}px`,width:`${d.width}px`,height:`${d.height}px`})};i.addEventListener("pointerdown",d=>{p||d.button!==0||d.target!==i||(d.preventDefault(),T(d.clientX,d.clientY),w())}),i.addEventListener("pointermove",d=>{c&&(d.preventDefault(),c.width=d.clientX-c.x,c.height=d.clientY-c.y,w())});const L=d=>{c||p||(d.preventDefault(),mt(d,t.host))};i.addEventListener("wheel",L,{passive:!1}),o.addEventListener("wheel",L,{passive:!1});const N=async()=>{if(!l||!c)return;const d=se(c),f=l;if(d.width>=24&&d.height>=24){p=!0,m();try{const y=await ft(d,a);a.push(y)}catch(y){E((y==null?void 0:y.message)||"Failed to capture the current tab.")}}else f.remove();f.remove(),l=null,c=null,p=!1,m()};i.addEventListener("pointerup",()=>{N()}),i.addEventListener("pointercancel",()=>{N()}),m()}async function Q({mode:e,selectedText:t="",snapshots:r=[]}){if(e==="snapshot")await ke(t,r);else{const n=(u==null?void 0:u.meta)||await ve();if(!Array.isArray(n==null?void 0:n.noteTypes)||n.noteTypes.length===0)throw new Error("No note types are available in Anki.");if(!Array.isArray(n==null?void 0:n.deckNames)||n.deckNames.length===0)throw new Error("No decks are available in Anki.");const i=(u==null?void 0:u.form)||await Ce(n);u={mode:e,meta:n,form:i,context:{url:window.location.href||"",title:document.title||"",selectedText:je(e,t,D())},snapshots:Array.isArray(r)?r:[],statusKind:"",statusText:"",submitting:!1}}await U()}globalThis.__incrementoTriggerBrowserCapture=e=>{if(String(e||"").trim().toLowerCase()==="snapshot")return J(),{ok:!0};const r=D();return r?(Q({mode:"selection",selectedText:r,snapshots:[]}).catch(n=>{E((n==null?void 0:n.message)||"Failed to open browser capture."),S()}),{ok:!0}):(E("Select text on the page first."),{ok:!1,error:"Select text on the page first."})},document.addEventListener("keydown",e=>{if(!e.altKey||!lt(e)||le()||Ne(e.target))return;if(e.metaKey){e.preventDefault(),e.stopPropagation(),J();return}if(e.ctrlKey||e.shiftKey)return;const t=D();t&&(e.preventDefault(),e.stopPropagation(),Q({mode:"selection",selectedText:t,snapshots:[]}).catch(r=>{E((r==null?void 0:r.message)||"Failed to open browser capture."),S()}))},!0),document.addEventListener("contextmenu",e=>{const t=Ee(e.target);M=we(t)},!0),document.addEventListener("click",e=>{if(!P.modifierClickEnabled||e.defaultPrevented||Number(e.button)!==0||le()||Ne(e.target))return;const t=Ee(e.target);if(!t||!_t(e,P))return;const r=we(t);if(!r)return;P.navigateAfterSave||e.preventDefault();const n=K();n==null||n.sendMessage({type:"SAVE_CLICKED_LINK_AS_WEBPAGE",url:r.url,title:r.title,sourcePageUrl:window.location.href||"",sourcePageTitle:document.title||""},i=>{var o;(o=chrome==null?void 0:chrome.runtime)==null||o.lastError})},!0),document.addEventListener("selectionchange",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("mouseup",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keyup",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keydown",e=>{e.key==="Escape"&&le()&&(e.preventDefault(),e.stopPropagation(),S())},!0);function ht(e){try{const t=new URL(e),r=t.searchParams.get("v");if(r)return r;const n=t.pathname.split("/").filter(Boolean);if(t.hostname==="youtu.be"&&n[0])return n[0];if((n[0]==="shorts"||n[0]==="live"||n[0]==="embed")&&n[1])return n[1]}catch{}return""}function gt(e){const t=String(e||"").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);return t?t[1]:""}function bt(){const e=window.location.href||"",t=window.location.hostname||"";return t.includes("youtube.com")||t==="youtu.be"?{provider:"youtube",videoId:ht(e)}:t.includes("vimeo.com")?{provider:"vimeo",videoId:gt(e)}:{provider:"",videoId:""}}function Me(e){try{const r=new URL(e).searchParams.get("inc_card_id")||"",n=Number(r);if(Number.isFinite(n)&&n>0)return Math.floor(n)}catch{}return 0}function yt(e){const t=String(e||"").replace(/^#/,"").trim();if(!t)return"";const n=t.indexOf("__incremento_resume__=1");return n<0?t:t.slice(0,n).replace(/[&?]+$/,"")}function xt(e){try{const t=new URL(e);t.searchParams.delete("inc_card_id"),t.searchParams.delete("inc_track_web"),t.searchParams.delete("inc_resume_sec"),t.searchParams.delete("inc_resume_media");const r=yt(t.hash);return t.hash=r?`#${r}`:"",t.toString()}catch{return String(e||"")}}function Et(e){try{const t=new URL(e),r=String(t.searchParams.get("inc_track_web")||"").trim().toLowerCase();return r==="1"||r==="true"||r==="yes"||r==="on"}catch{return!1}}function wt(){if(window.top!==window)return;const e=window.location.href||"";if(!e||!/inc_(card_id|track_web|resume_sec|resume_media)|__incremento_resume__=1/.test(e))return;const t=xt(e);if(!(!t||t===e))try{history.replaceState(history.state,document.title||"",t),me=t}catch{}}function Ie(){const e=Array.from(document.querySelectorAll("video"));return e.length===0?null:(e.sort((t,r)=>{const n=(t.videoWidth||0)*(t.videoHeight||0);return(r.videoWidth||0)*(r.videoHeight||0)-n}),e[0])}function de(e,t=12){const r=Math.max(0,Math.floor(Number(e)||0));if(r<=0)return!1;const n=Ie();if(!n)return t>0&&window.setTimeout(()=>de(r,t-1),500),!1;try{return n.currentTime=r,E(`Resumed to ${r}s`),!0}catch{return t>0&&window.setTimeout(()=>de(r,t-1),500),!1}}function Z(){var a,l;const e=window.location.href||"",{provider:t,videoId:r}=bt(),n=Ie(),i=t?e:String((n==null?void 0:n.currentSrc)||(n==null?void 0:n.src)||"").trim(),o=String(((a=n==null?void 0:n.getAttribute)==null?void 0:a.call(n,"title"))||((l=n==null?void 0:n.getAttribute)==null?void 0:l.call(n,"aria-label"))||document.title||"").trim();return{provider:t,videoId:r,video:n,mediaUrl:i,mediaTitle:o}}function Tt(){const{provider:e,video:t}=Z();let r=-1,n=!1;if(t&&(r=Math.max(0,Math.floor(Number(t.currentTime)||0)),n=!0),e==="youtube"&&r<=0){const i=pe();i>=0&&(r=i,n=!0)}if(e==="vimeo"&&r<=0){const i=ue();i>=0&&(r=i,n=!0)}return{found:n,seconds:n?Math.max(0,r):0}}function vt(){const e=window.location.href||"",{provider:t,videoId:r,mediaUrl:n,mediaTitle:i}=Z(),o=Tt();return{ok:!0,pageUrl:e,pageTitle:document.title||"",provider:t,videoId:r,mediaUrl:n,mediaTitle:i,hasDetectedTime:!!o.found,seconds:Math.max(0,Math.floor(Number(o.seconds)||0)),timeText:o.found?Te(o.seconds):""}}function Fe(e){const t=String(e||"").trim();if(!t)return-1;const r=t.split(":").map(n=>n.trim());return r.every(n=>/^\d+$/.test(n))?r.length===2?Number(r[0])*60+Number(r[1]):r.length===3?Number(r[0])*3600+Number(r[1])*60+Number(r[2]):-1:-1}function ue(){const e=Array.from(document.querySelectorAll('[data-progress-bar-timecode="true"], [class*="Timecode_module_timecode__"]'));for(const t of e){const r=String((t==null?void 0:t.textContent)||"").trim(),n=Fe(r);if(n>=0)return n}return-1}function pe(){const e=Array.from(document.querySelectorAll(".ytp-time-current, [class*='ytp-time-current']"));for(const t of e){const r=String((t==null?void 0:t.textContent)||"").trim(),n=Fe(r);if(n>=0)return n}return-1}async function Pe(){try{const e=await H({type:"GET_LINKED_CARD_CONTEXT",url:window.location.href||""});if(!(e!=null&&e.linked)||Number(e.cardId)<=0){R(null);return}const t=await H({type:"LOAD_BROWSER_MEDIA_REF"});if(!(t!=null&&t.ok)||!(t!=null&&t.hasReference)){R(null);return}R(t)}catch{R(null)}}let De=-1,Oe=0,Ue=-1,$e=0,ee=!1,Y=!0,te=null,me=window.location.href||"";function ne(){Y=!1,te!==null&&(clearInterval(te),te=null)}function We(e){if(!Y)return!1;try{const t=K();return t!=null&&t.id?(t.sendMessage(e,()=>{try{const r=t==null?void 0:t.lastError;r&&/context invalidated/i.test(String(r.message||""))&&ne()}catch{ne()}}),!0):(ne(),!1)}catch{return ne(),!1}}function ze(){if(!Y){O(!1);return}try{const e=K();if(!(e!=null&&e.id)){O(!1);return}e.sendMessage({type:"GET_TRACKING_STATUS",url:window.location.href||""},t=>{try{if(e==null?void 0:e.lastError){O(!1);return}}catch{O(!1);return}O(!!(t!=null&&t.tracked),String((t==null?void 0:t.mode)||""))})}catch{O(!1)}}function k(e=!1,t=!1){if(!Y)return;const{provider:r,videoId:n,video:i}=Z();if(!r)return;let o=-1;if(i&&(o=Math.max(0,Math.floor(Number(i.currentTime)||0))),r==="youtube"&&o<=0){const l=pe();l>=0&&(o=l)}if(r==="vimeo"&&o<=0){const l=ue();l>=0&&(o=l)}if(o<0)return;const a=Date.now();!e&&o===De&&a-Oe<4e3||(De=o,Oe=a,We({type:"heartbeat",provider:r,videoId:n,cardId:Me(window.location.href||""),flush:!!t,seconds:o,url:window.location.href||"",title:document.title||""}))}function I(e=!1,t=!1){if(!Y)return;const r=window.location.href||"",{provider:n,videoId:i,video:o,mediaUrl:a,mediaTitle:l}=Z();if(!o&&!n)return;let c=-1;if(o&&(c=Math.max(0,Math.floor(Number(o.currentTime)||0))),n==="youtube"&&c<=0){const m=pe();m>=0&&(c=m)}if(n==="vimeo"&&c<=0){const m=ue();m>=0&&(c=m)}if(c<0)return;const p=Date.now();!e&&c===Ue&&p-$e<4e3||(Ue=c,$e=p,We({type:"web_media_heartbeat",provider:n,videoId:i,cardId:Me(r),trackEnabled:Et(r),flush:!!t,seconds:c,url:r,mediaUrl:a,mediaTitle:l,title:document.title||""}))}te=window.setInterval(()=>{k(!1,!1),I(!1,!1)},1e3),window.setInterval(()=>{const e=window.location.href||"";e!==me&&(me=e,ee=!1,ze(),Pe())},750),window.addEventListener("pagehide",()=>{k(!0,!0),I(!0,!0)},{capture:!0}),window.addEventListener("beforeunload",()=>{k(!0,!0),I(!0,!0)},{capture:!0}),document.addEventListener("visibilitychange",()=>{document.visibilityState==="hidden"&&(k(!0,!0),I(!0,!0))}),document.addEventListener("timeupdate",()=>{k(!1,!1),I(!1,!1)},!0),document.addEventListener("play",()=>{k(!0,!1),I(!0,!1)},!0),document.addEventListener("pause",()=>{k(!0,!0),I(!0,!0)},!0),document.addEventListener("ended",()=>k(!0,!0),!0),window.setTimeout(()=>k(!0,!1),1200),window.setTimeout(wt,1200),window.setTimeout(ze,300),window.setTimeout(()=>{Pe()},320),window.__incrementoContentScriptState={...window.__incrementoContentScriptState||{},version:V,ready:!0}})();
