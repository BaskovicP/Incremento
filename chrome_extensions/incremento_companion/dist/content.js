import{L as ne,D as yt,n as fe,E as xt,F as Et,B as $e,C as wt}from"./assets/extension-shared.js";(()=>{var Ie,Pe,De;const X="browser-capture-v6",We="incremento-browser-capture-root",re=window.__incrementoContentScriptState&&typeof window.__incrementoContentScriptState=="object"?window.__incrementoContentScriptState:{};if(re.version===X&&re.ready)return;window.__incrementoContentScriptState={...re,version:X,ready:!1},window.__incrementoContentScriptVersion=X;const oe="incremento_browser_capture_settings",O=50,ze=0,Ke=100;let I=yt,M=null;globalThis.__incrementoLastSelectedText=String(globalThis.__incrementoLastSelectedText||"").trim();function U(){var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();return e?(globalThis.__incrementoLastSelectedText=e,e):String(globalThis.__incrementoLastSelectedText||"").trim()}function he(e){const t=Number(e);return Number.isFinite(t)?Math.min(Ke,Math.max(ze,Number(t.toFixed(4)))):O}function Re(e){return Array.from(new Set(String(e||"").replaceAll(","," ").split(/\s+/).map(t=>t.trim()).filter(Boolean)))}function ge(e,t){const r=Array.isArray(t)?t.filter(Boolean):[],n=r[0]||"",i=o=>o===""?"":r.includes(o)?o:n;return{titleField:i(String((e==null?void 0:e.titleField)||"")),selectedTextField:i(String((e==null?void 0:e.selectedTextField)||"")),urlField:i(String((e==null?void 0:e.urlField)||"")),snapshotField:i(String((e==null?void 0:e.snapshotField)||""))}}function He(e,t){const r=Array.isArray(t==null?void 0:t.noteTypes)?t.noteTypes:[],n=Array.isArray(t==null?void 0:t.deckNames)?t.deckNames.filter(Boolean):[],i=String((e==null?void 0:e.noteTypeName)||""),o=r.find(x=>(x==null?void 0:x.name)===i)||r[0]||null,a=(o==null?void 0:o.name)||"",l=Array.isArray(o==null?void 0:o.fields)?o.fields:[],c=e!=null&&e.mappingsByNoteType&&typeof e.mappingsByNoteType=="object"?e.mappingsByNoteType:{},u=ge(c[a],l),m=String((e==null?void 0:e.deckName)||""),w=n.includes(m)?m:n[0]||"Default";return{noteTypeName:a,deckName:w,priority:he(e==null?void 0:e.priority),tagsText:String((e==null?void 0:e.tagsText)||""),fieldMappings:u,mappingsByNoteType:c}}function $(e,t,r){return{...e,noteTypeName:t,fieldMappings:{...r},mappingsByNoteType:{...(e==null?void 0:e.mappingsByNoteType)||{},[t]:{...r}}}}function Ye(e,t){var r,n,i,o;return{url:String((e==null?void 0:e.url)||"").trim(),title:String((e==null?void 0:e.title)||"").trim()||String((e==null?void 0:e.url)||"").trim()||"Untitled",selectedText:String((e==null?void 0:e.selectedText)||"").trim(),noteTypeName:String((t==null?void 0:t.noteTypeName)||"").trim(),deckName:String((t==null?void 0:t.deckName)||"").trim(),tags:Re(t==null?void 0:t.tagsText),priority:he(t==null?void 0:t.priority),fieldMappings:{titleField:String(((r=t==null?void 0:t.fieldMappings)==null?void 0:r.titleField)||"").trim(),selectedTextField:String(((n=t==null?void 0:t.fieldMappings)==null?void 0:n.selectedTextField)||"").trim(),urlField:String(((i=t==null?void 0:t.fieldMappings)==null?void 0:i.urlField)||"").trim(),snapshotField:String(((o=t==null?void 0:t.fieldMappings)==null?void 0:o.snapshotField)||"").trim()},snapshots:Array.isArray(e==null?void 0:e.snapshots)?e.snapshots.map((a,l)=>({mimeType:"image/png",filename:String((a==null?void 0:a.filename)||`browser-capture-${l+1}.png`),base64:String((a==null?void 0:a.base64)||"").trim()})).filter(a=>a.base64):[]}}function T(e){const t=document.getElementById("incremento-video-time-toast");t&&t.remove();const r=document.createElement("div");r.id="incremento-video-time-toast",r.textContent=String(e||""),Object.assign(r.style,{position:"fixed",zIndex:2147483647,top:"10px",right:"10px",maxWidth:"320px",padding:"10px 14px",background:"rgba(0, 0, 0, 0.86)",color:"#fff",fontSize:"13px",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"6px",boxShadow:"0 2px 8px rgba(0, 0, 0, 0.4)",opacity:"0",transition:"opacity 0.2s ease"}),document.documentElement.appendChild(r),requestAnimationFrame(()=>{r.style.opacity="1"}),setTimeout(()=>{r.style.opacity="0",setTimeout(()=>r.remove(),220)},2400)}async function je(){try{const e=await chrome.storage.local.get(ne);I=fe(e==null?void 0:e[ne])}catch{I=fe(null)}}function be(e){var i,o;const t=e instanceof Element?e:(e==null?void 0:e.parentElement)||null,r=(i=t==null?void 0:t.closest)==null?void 0:i.call(t,"a[href]");if(!r)return null;const n=String(r.href||((o=r.getAttribute)==null?void 0:o.call(r,"href"))||"").trim();return $e(n)?r:null}function ye(e){var r;if(!e)return null;const t=String(e.href||((r=e.getAttribute)==null?void 0:r.call(e,"href"))||"").trim();return $e(t)?{url:t,title:wt(e.textContent||"",t)}:null}function Ge(){let e=document.getElementById("incremento-tracking-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-tracking-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483646,top:"52px",right:"10px",display:"none",alignItems:"center",gap:"8px",padding:"8px 12px",background:"linear-gradient(135deg, rgba(10, 34, 64, 0.94), rgba(17, 83, 126, 0.94))",color:"#fff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",letterSpacing:"0.08em",textTransform:"uppercase",borderRadius:"999px",boxShadow:"0 4px 14px rgba(0, 0, 0, 0.28)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"none"});const t=document.createElement("span");t.textContent="●",Object.assign(t.style,{color:"#53f2a5",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(83, 242, 165, 0.85)"}),e.appendChild(t);const r=document.createElement("span");r.textContent="⚠",Object.assign(r.style,{color:"#ffd166",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(255, 209, 102, 0.55)"}),e.appendChild(r);const n=document.createElement("span");return n.id="incremento-tracking-badge-label",n.textContent="Tracking",e.appendChild(n),document.documentElement.appendChild(e),e}function P(e,t=""){const r=Ge(),n=document.getElementById("incremento-tracking-badge-label");if(!(!r||!n)){if(!e){r.style.display="none";return}n.textContent=t==="web"?"Tracking Web Card":"Tracking",r.style.display="inline-flex"}}function xe(e){const t=Math.max(0,Math.floor(Number(e)||0)),r=Math.floor(t/3600),n=Math.floor(t%3600/60),i=t%60;return r>0?`${r}:${String(n).padStart(2,"0")}:${String(i).padStart(2,"0")}`:`${n}:${String(i).padStart(2,"0")}`}function Xe(){let e=document.getElementById("incremento-browser-media-ref-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-browser-media-ref-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483645,top:"96px",right:"10px",display:"none",alignItems:"center",gap:"8px",maxWidth:"320px",padding:"9px 12px",background:"linear-gradient(135deg, rgba(28, 32, 48, 0.96), rgba(34, 62, 96, 0.96))",color:"#eef5ff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"14px",boxShadow:"0 5px 18px rgba(0, 0, 0, 0.30)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"auto"});const t=document.createElement("span");t.textContent="▶",Object.assign(t.style,{color:"#8fd3ff",fontSize:"11px",lineHeight:"1"}),e.appendChild(t);const r=document.createElement("span");r.id="incremento-browser-media-ref-badge-label",r.textContent="",Object.assign(r.style,{flex:"1 1 auto",minWidth:"0"}),e.appendChild(r);const n=document.createElement("button");return n.type="button",n.textContent="×",n.setAttribute("aria-label","Dismiss saved browser time badge"),Object.assign(n.style,{appearance:"none",border:"0",background:"transparent",color:"#a9bfdc",cursor:"pointer",fontSize:"16px",fontWeight:"700",lineHeight:"1",padding:"0 0 0 4px",margin:"0",pointerEvents:"auto"}),n.addEventListener("click",i=>{i.preventDefault(),i.stopPropagation(),Z=!0,e.style.display="none"}),e.appendChild(n),document.documentElement.appendChild(e),e}function W(e){const t=Xe(),r=document.getElementById("incremento-browser-media-ref-badge-label");if(!t||!r)return;if(!!!(e!=null&&e.hasReference)){t.style.display="none";return}if(Z)return;const i=String((e==null?void 0:e.timeText)||xe(e==null?void 0:e.seconds));r.textContent=i?`Last saved ${i}`:"Last saved",t.style.display="inline-flex"}function z(){try{return(chrome==null?void 0:chrome.runtime)||null}catch{return null}}je();try{(Pe=(Ie=chrome==null?void 0:chrome.storage)==null?void 0:Ie.onChanged)==null||Pe.addListener((e,t)=>{var r;t!=="local"||!e||!Object.prototype.hasOwnProperty.call(e,ne)||(I=fe((r=e[ne])==null?void 0:r.newValue))})}catch{}try{const e=z();(De=e==null?void 0:e.onMessage)==null||De.addListener((t,r,n)=>{var i;if(!t||!t.type)return!1;if(t.type==="SHOW_TOAST")return T(t.text||""),n==null||n({ok:!0}),!1;if(t.type==="TRIGGER_BROWSER_CAPTURE"){if(String(t.mode||"").trim().toLowerCase()==="snapshot")return q(),n==null||n({ok:!0}),!1;const a=U();return a?(J({mode:"selection",selectedText:a,snapshots:[]}).then(()=>n==null?void 0:n({ok:!0}),l=>{T((l==null?void 0:l.message)||"Failed to open browser capture."),C(),n==null||n({ok:!1,error:String((l==null?void 0:l.message)||"")})}),!0):(T("Select text on the page first."),n==null||n({ok:!1}),!1)}if(t.type==="GET_PAGE_CONTEXT")return n==null||n({ok:!0,html:((i=document.documentElement)==null?void 0:i.outerHTML)||"",selectionText:U(),title:document.title||"",url:window.location.href||""}),!1;if(t.type==="GET_CONTEXT_LINK_INFO")return n==null||n({ok:!0,url:String((M==null?void 0:M.url)||""),title:String((M==null?void 0:M.title)||"")}),!1;if(t.type==="GET_CURRENT_MEDIA_CONTEXT")return n==null||n(gt()),!1;if(t.type==="APPLY_MEDIA_RESUME"){const o=ce(t.seconds);return n==null||n({ok:o}),!1}return t.type==="UPDATE_BROWSER_MEDIA_REF_BADGE"&&(Z=!1,W(t.reference||null),n==null||n({ok:!0})),!1})}catch{}let g=null,f=null;function K(e){return new Promise((t,r)=>{const n=z();if(!(n!=null&&n.sendMessage)){r(new Error("Incremento extension runtime is unavailable."));return}n.sendMessage(e,i=>{const o=chrome.runtime.lastError;if(o){r(new Error(o.message||"Extension request failed."));return}t(i||null)})})}async function Ve(){const e=await K({type:"LOAD_BROWSER_CAPTURE_META"});if(!(e!=null&&e.ok))throw new Error(String((e==null?void 0:e.error)||"Failed to load browser capture metadata."));return e}async function qe(e){const t=await K({type:"SUBMIT_BROWSER_CAPTURE",payload:e});if(!(t!=null&&t.ok))throw new Error(String((t==null?void 0:t.error)||"Failed to submit browser capture."));return t}async function Je(){const e=await K({type:"CAPTURE_VISIBLE_TAB"});if(!(e!=null&&e.ok)||!(e!=null&&e.dataUrl))throw new Error(String((e==null?void 0:e.error)||"Failed to capture the current tab."));return e.dataUrl}async function Qe(e){let t={};try{const r=await chrome.storage.local.get(oe);t=(r==null?void 0:r[oe])||{}}catch{t={}}return He(t,e)}async function Ze(e){try{await chrome.storage.local.set({[oe]:{noteTypeName:String((e==null?void 0:e.noteTypeName)||""),deckName:String((e==null?void 0:e.deckName)||""),priority:Number((e==null?void 0:e.priority)??O),tagsText:String((e==null?void 0:e.tagsText)||""),mappingsByNoteType:(e==null?void 0:e.mappingsByNoteType)||{}}})}catch{}}function Ee(e){const t=e instanceof Element?e:(e==null?void 0:e.parentElement)||null;return t?t.closest("input, textarea, select")?!0:!!t.closest('[contenteditable=""], [contenteditable="true"]'):!1}function ie(){return!!g}function et(e){return String((e==null?void 0:e.code)||"").toLowerCase()==="keyx"}function ae(e){const t=g==null?void 0:g.shell,r=e==null?void 0:e.target;if(!(!t||!(r instanceof Node)||!t.contains(r))){if(e.key==="Escape"){e.preventDefault(),e.stopPropagation(),C();return}e.stopPropagation()}}function V(){if(g)return g;const e=document.createElement("div");e.id=We,e.style.all="initial";const t=e.attachShadow({mode:"open"});document.documentElement.appendChild(e),t.addEventListener("keydown",ae,!0),t.addEventListener("keypress",ae,!0),t.addEventListener("keyup",ae,!0);const r=document.createElement("style");r.textContent=`
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
    `,t.appendChild(r);const n=document.createElement("div");return n.className="shell",t.appendChild(n),g={host:e,shadow:t,shell:n},g}function C(){var e;(e=g==null?void 0:g.host)!=null&&e.isConnected&&g.host.remove(),g=null,f=null}function we(){const e=V();e.shell.textContent=""}function tt(e,t){const r=document.createElement("div");r.className="snapshots";for(const n of t){const i=document.createElement("div");i.className="snapshot-card";const o=document.createElement("img");o.src=n.dataUrl,o.alt=n.filename,i.appendChild(o);const a=document.createElement("div");a.className="snapshot-footer";const l=document.createElement("span");l.textContent=n.filename,a.appendChild(l);const c=document.createElement("button");c.type="button",c.textContent="Remove",c.addEventListener("click",()=>{f.snapshots=f.snapshots.filter(u=>u.id!==n.id),A()}),a.appendChild(c),i.appendChild(a),r.appendChild(i)}return r}async function A(){var Oe;const e=V(),{shell:t,shadow:r}=e,n=f;we();const i=document.createElement("div");i.className="backdrop",i.addEventListener("click",()=>C()),t.appendChild(i);const o=document.createElement("section");o.className="panel",t.appendChild(o);const a=document.createElement("p");a.className="eyebrow",a.textContent=n.mode==="snapshot"?"Browser snapshot":"Browser selection",o.appendChild(a);const l=document.createElement("h2");l.textContent="Send capture to Anki",o.appendChild(l);const c=document.createElement("p");c.className="lead",c.textContent=n.mode==="snapshot"?`${n.snapshots.length} snapshot${n.snapshots.length===1?"":"s"} ready from ${n.context.url}`:`Selected text from ${n.context.url}`,o.appendChild(c);const u=document.createElement("form");u.noValidate=!0;const m=document.createElement("div");m.className="grid",u.appendChild(m);const w=(s,p,E=!1,b="")=>{const k=document.createElement("div");k.className=`field${E?" full":""}`;const Ue=document.createElement("label");if(Ue.textContent=s,k.appendChild(Ue),k.appendChild(p),b){const me=document.createElement("p");me.className="field-note",me.textContent=b,k.appendChild(me)}return k},x=document.createElement("select");for(const s of n.meta.noteTypes){const p=document.createElement("option");p.value=s.name,p.textContent=s.name,x.appendChild(p)}x.value=n.form.noteTypeName,x.addEventListener("change",()=>{var E;const s=n.meta.noteTypes.find(b=>b.name===x.value),p=ge((E=n.form.mappingsByNoteType)==null?void 0:E[x.value],(s==null?void 0:s.fields)||[]);n.form=$(n.form,x.value,p),A()}),m.appendChild(w("Note type",x));const N=document.createElement("select");for(const s of n.meta.deckNames){const p=document.createElement("option");p.value=s,p.textContent=s,N.appendChild(p)}N.value=n.form.deckName,N.addEventListener("change",()=>{n.form.deckName=N.value}),m.appendChild(w("Deck",N));const _=document.createElement("input");_.type="text",_.value=n.form.tagsText,_.placeholder="tag-one tag-two",_.addEventListener("input",()=>{n.form.tagsText=_.value}),m.appendChild(w("Tags",_,!0));const v=document.createElement("div");v.style.display="grid",v.style.gridTemplateColumns="1fr auto",v.style.gap="10px",v.style.alignItems="center";const d=document.createElement("input");d.type="range",d.min="0",d.max="100",d.step="0.1",d.value=String(n.form.priority??O);const h=document.createElement("input");h.type="number",h.min="0",h.max="100",h.step="0.1",h.style.width="92px",h.value=String(n.form.priority??O);const y=s=>{const p=Number(s),E=Number.isFinite(p)?Math.min(100,Math.max(0,p)):O;n.form.priority=Number(E.toFixed(4)),d.value=String(n.form.priority),h.value=String(n.form.priority)};d.addEventListener("input",()=>y(d.value)),h.addEventListener("change",()=>y(h.value)),v.appendChild(d),v.appendChild(h),m.appendChild(w("Priority",v));const B=["",...((Oe=n.meta.noteTypes.find(s=>s.name===n.form.noteTypeName))==null?void 0:Oe.fields)||[]],F=(s,p)=>{const E=document.createElement("select");for(const b of B){const k=document.createElement("option");k.value=b,k.textContent=b||"Do not insert",E.appendChild(k)}return E.value=B.includes(s)?s:"",E.addEventListener("change",()=>{p(E.value)}),E},bt=!!n.context.selectedText;m.appendChild(w("Page title field",F(n.form.fieldMappings.titleField,s=>{n.form=$(n.form,n.form.noteTypeName,{...n.form.fieldMappings,titleField:s})}),!1,"The current page title is always available. First-field mappings get a unique snapshot suffix.")),m.appendChild(w("Selected text field",F(n.form.fieldMappings.selectedTextField,s=>{n.form=$(n.form,n.form.noteTypeName,{...n.form.fieldMappings,selectedTextField:s})}),!1,bt?`${n.context.selectedText.length} chars ready for insertion.`:"No text added yet.")),m.appendChild(w("Source URL field",F(n.form.fieldMappings.urlField,s=>{n.form=$(n.form,n.form.noteTypeName,{...n.form.fieldMappings,urlField:s})}),!1,"The current page URL is always available.")),m.appendChild(w("Snapshot field",F(n.form.fieldMappings.snapshotField,s=>{n.form=$(n.form,n.form.noteTypeName,{...n.form.fieldMappings,snapshotField:s})}),!0,n.snapshots.length>0?`${n.snapshots.length} snapshot${n.snapshots.length===1?"":"s"} selected.`:"No snapshot images in this capture."));const H=document.createElement("textarea");if(H.value=n.context.selectedText,H.placeholder=n.mode==="snapshot"?"Add text to store with these snapshots...":"Selected text will appear here. You can edit it before saving.",H.addEventListener("input",()=>{n.context.selectedText=H.value}),m.appendChild(w(n.mode==="snapshot"?"Text to add":"Selected text",H,!0,"This content is inserted into the selected text field if one is chosen.")),n.snapshots.length>0){const s=document.createElement("div");s.className="field full";const p=document.createElement("label");p.textContent="Snapshots",s.appendChild(p),s.appendChild(tt(r,n.snapshots)),m.appendChild(s)}const pe=document.createElement("p");pe.className=`status${n.statusKind?` ${n.statusKind}`:""}`,pe.textContent=n.statusText,u.appendChild(pe);const Y=document.createElement("div");if(Y.className="actions",n.snapshots.length>0){const s=document.createElement("button");s.type="button",s.className="ghost-btn",s.textContent="Capture more",s.addEventListener("click",()=>q(n.snapshots)),Y.appendChild(s)}const j=document.createElement("button");j.type="button",j.className="secondary-btn",j.textContent="Cancel",j.addEventListener("click",()=>C()),Y.appendChild(j);const G=document.createElement("button");G.type="submit",G.className="primary-btn",G.textContent=n.submitting?"Saving...":"Create note",G.disabled=!!n.submitting,Y.appendChild(G),u.appendChild(Y),u.addEventListener("submit",async s=>{if(s.preventDefault(),n.submitting)return;const p=Ye({...n.context,snapshots:n.snapshots.map(b=>({filename:b.filename,base64:b.base64}))},n.form),E=!!(p.fieldMappings.titleField||p.selectedText&&p.fieldMappings.selectedTextField||p.fieldMappings.urlField||p.snapshots.length>0&&p.fieldMappings.snapshotField);if(!p.noteTypeName||!p.deckName){n.statusKind="error",n.statusText="Choose a note type and deck.",A();return}if(!E){n.statusKind="error",n.statusText="Map at least one available capture part to a note field.",A();return}n.submitting=!0,n.statusKind="",n.statusText="Creating note in Anki...",A();try{const b=await qe(p);await Ze(n.form),T(`Created ${b.noteTypeName} note in ${b.deckName}.`),C()}catch(b){n.submitting=!1,n.statusKind="error",n.statusText=(b==null?void 0:b.message)||"Failed to create note.",A()}}),o.appendChild(u)}function nt(e){return new Promise((t,r)=>{const n=new Image;n.onload=()=>t(n),n.onerror=()=>r(new Error("Failed to decode screenshot.")),n.src=e})}async function rt(e,t){const r=await nt(e),n=r.width/window.innerWidth,i=r.height/window.innerHeight,o=Math.max(0,Math.round(t.x*n)),a=Math.max(0,Math.round(t.y*i)),l=Math.max(1,Math.round(t.width*n)),c=Math.max(1,Math.round(t.height*i)),u=document.createElement("canvas");return u.width=l,u.height=c,u.getContext("2d").drawImage(r,o,a,l,c,0,0,l,c),u.toDataURL("image/png")}function ot(e){const t=String(e||""),r=t.indexOf(",");return r>=0?t.slice(r+1):t}function le(e){const t=Math.abs(e.width),r=Math.abs(e.height);return{x:e.width>=0?e.x:e.x-t,y:e.height>=0?e.y:e.y-r,width:t,height:r}}function Te(e=2){return new Promise(t=>{const r=Math.max(1,Number(e)||1);let n=0;const i=()=>{if(n+=1,n>=r){t();return}requestAnimationFrame(i)};requestAnimationFrame(i)})}function it(e,t){if(!(e instanceof Element))return!1;const r=window.getComputedStyle(e),n=t==="x"?r.overflowX:r.overflowY;return/(auto|scroll|overlay)/.test(String(n||""))?t==="x"?e.scrollWidth>e.clientWidth:e.scrollHeight>e.clientHeight:!1}function ve(e,t){let r=e instanceof Element?e:null;for(;r;){if(it(r,t))return r;r=r.parentElement}const n=document.scrollingElement;return n instanceof Element?n:document.documentElement}function at(e,t){var u;if(!e)return;const r=((u=t==null?void 0:t.style)==null?void 0:u.pointerEvents)||"";t!=null&&t.style&&(t.style.pointerEvents="none");let n=null;try{n=document.elementFromPoint(e.clientX,e.clientY)}finally{t!=null&&t.style&&(t.style.pointerEvents=r)}const i=Number(e.deltaX)||0,o=Number(e.deltaY)||0,a=i?ve(n,"x"):null,l=o?ve(n,"y"):null,c=document.scrollingElement instanceof Element?document.scrollingElement:document.documentElement;i&&(a||c).scrollBy({left:i,top:0,behavior:"auto"}),o&&(l||c).scrollBy({left:0,top:o,behavior:"auto"})}async function lt(e,t=[]){const r=V();r.shell.style.display="none";try{await Te(2);const n=await Je(),i=le(e),o=await rt(n,i);return{id:`${Date.now()}-${t.length}-${Math.random().toString(16).slice(2,8)}`,filename:`browser-capture-${t.length+1}.png`,dataUrl:o,base64:ot(o)}}catch(n){throw new Error((n==null?void 0:n.message)||"Failed to capture the current tab.")}finally{g!=null&&g.shell&&(g.shell.style.display="",await Te(1))}}function q(e=[]){var v;const t=V();we();const r=e.length>0&&((v=f==null?void 0:f.context)==null?void 0:v.selectedText)||"";f={mode:"snapshot",meta:(f==null?void 0:f.meta)||null,form:(f==null?void 0:f.form)||null,context:{url:window.location.href||"",title:document.title||"",selectedText:r},snapshots:[...e],statusKind:"",statusText:"",submitting:!1};const n=t.shell,i=document.createElement("div");i.className="capture-shell",n.appendChild(i);const o=document.createElement("div");o.className="capture-toolbar",o.innerHTML=`
      <strong>Snapshot Mode</strong>
      <span>Draw one or more rectangles on the page. The capture is limited to the current viewport.</span>
      <span class="spacer"></span>
    `,n.appendChild(o);const a=[...e];let l=null,c=null,u=!1;const m=()=>{o.innerHTML=`
        <strong>Snapshot Mode</strong>
        <span>Draw a rectangle to capture it immediately, then scroll and capture another area if needed.</span>
        <span class="spacer"></span>
      `;const d=document.createElement("span");d.textContent=u?"Capturing...":`${a.length} snapshot${a.length===1?"":"s"} ready`,o.appendChild(d);const h=document.createElement("button");h.type="button",h.className="toolbar-btn",h.textContent="Undo",h.disabled=u||a.length===0,h.addEventListener("click",()=>{a.pop(),m()}),o.appendChild(h);const y=document.createElement("button");y.type="button",y.className="toolbar-btn",y.textContent="Clear",y.disabled=u||a.length===0,y.addEventListener("click",()=>{a.splice(0,a.length),m()}),o.appendChild(y);const D=document.createElement("button");D.type="button",D.className="toolbar-btn",D.textContent="Cancel",D.addEventListener("click",()=>C()),o.appendChild(D);const B=document.createElement("button");B.type="button",B.className="toolbar-btn primary",B.textContent="Continue",B.addEventListener("click",()=>{var F;if(!u){if(!a.length){T("Draw at least one region first.");return}J({mode:"snapshot",selectedText:((F=f==null?void 0:f.context)==null?void 0:F.selectedText)||"",snapshots:[...a]})}}),o.appendChild(B)},w=(d,h)=>{c={x:d,y:h,width:0,height:0},l=document.createElement("div"),l.className="selection-rect",l.dataset.label=`Capture ${a.length+1}`,i.appendChild(l)},x=()=>{if(!l||!c)return;const d=le(c);Object.assign(l.style,{left:`${d.x}px`,top:`${d.y}px`,width:`${d.width}px`,height:`${d.height}px`})};i.addEventListener("pointerdown",d=>{u||d.button!==0||d.target!==i||(d.preventDefault(),w(d.clientX,d.clientY),x())}),i.addEventListener("pointermove",d=>{c&&(d.preventDefault(),c.width=d.clientX-c.x,c.height=d.clientY-c.y,x())});const N=d=>{c||u||(d.preventDefault(),at(d,t.host))};i.addEventListener("wheel",N,{passive:!1}),o.addEventListener("wheel",N,{passive:!1});const _=async()=>{if(!l||!c)return;const d=le(c),h=l;if(d.width>=24&&d.height>=24){u=!0,m();try{const y=await lt(d,a);a.push(y)}catch(y){T((y==null?void 0:y.message)||"Failed to capture the current tab.")}}else h.remove();h.remove(),l=null,c=null,u=!1,m()};i.addEventListener("pointerup",()=>{_()}),i.addEventListener("pointercancel",()=>{_()}),m()}async function J({mode:e,selectedText:t="",snapshots:r=[]}){const n=(f==null?void 0:f.meta)||await Ve();if(!Array.isArray(n==null?void 0:n.noteTypes)||n.noteTypes.length===0)throw new Error("No note types are available in Anki.");if(!Array.isArray(n==null?void 0:n.deckNames)||n.deckNames.length===0)throw new Error("No decks are available in Anki.");const i=(f==null?void 0:f.form)||await Qe(n);f={mode:e,meta:n,form:i,context:{url:window.location.href||"",title:document.title||"",selectedText:xt(e,t,U())},snapshots:Array.isArray(r)?r:[],statusKind:"",statusText:"",submitting:!1},await A()}globalThis.__incrementoTriggerBrowserCapture=e=>{if(String(e||"").trim().toLowerCase()==="snapshot")return q(),{ok:!0};const r=U();return r?(J({mode:"selection",selectedText:r,snapshots:[]}).catch(n=>{T((n==null?void 0:n.message)||"Failed to open browser capture."),C()}),{ok:!0}):(T("Select text on the page first."),{ok:!1,error:"Select text on the page first."})},document.addEventListener("keydown",e=>{if(!e.altKey||!et(e)||ie()||Ee(e.target))return;if(e.metaKey){e.preventDefault(),e.stopPropagation(),q();return}if(e.ctrlKey||e.shiftKey)return;const t=U();t&&(e.preventDefault(),e.stopPropagation(),J({mode:"selection",selectedText:t,snapshots:[]}).catch(r=>{T((r==null?void 0:r.message)||"Failed to open browser capture."),C()}))},!0),document.addEventListener("contextmenu",e=>{const t=be(e.target);M=ye(t)},!0),document.addEventListener("click",e=>{if(!I.modifierClickEnabled||e.defaultPrevented||Number(e.button)!==0||ie()||Ee(e.target))return;const t=be(e.target);if(!t||!Et(e,I))return;const r=ye(t);if(!r)return;I.navigateAfterSave||e.preventDefault();const n=z();n==null||n.sendMessage({type:"SAVE_CLICKED_LINK_AS_WEBPAGE",url:r.url,title:r.title,sourcePageUrl:window.location.href||"",sourcePageTitle:document.title||""},i=>{var o;(o=chrome==null?void 0:chrome.runtime)==null||o.lastError})},!0),document.addEventListener("selectionchange",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("mouseup",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keyup",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keydown",e=>{e.key==="Escape"&&ie()&&(e.preventDefault(),e.stopPropagation(),C())},!0);function ct(e){try{const t=new URL(e),r=t.searchParams.get("v");if(r)return r;const n=t.pathname.split("/").filter(Boolean);if(t.hostname==="youtu.be"&&n[0])return n[0];if((n[0]==="shorts"||n[0]==="live"||n[0]==="embed")&&n[1])return n[1]}catch{}return""}function st(e){const t=String(e||"").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);return t?t[1]:""}function dt(){const e=window.location.href||"",t=window.location.hostname||"";return t.includes("youtube.com")||t==="youtu.be"?{provider:"youtube",videoId:ct(e)}:t.includes("vimeo.com")?{provider:"vimeo",videoId:st(e)}:{provider:"",videoId:""}}function Ce(e){try{const r=new URL(e).searchParams.get("inc_card_id")||"",n=Number(r);if(Number.isFinite(n)&&n>0)return Math.floor(n)}catch{}return 0}function ut(e){const t=String(e||"").replace(/^#/,"").trim();if(!t)return"";const n=t.indexOf("__incremento_resume__=1");return n<0?t:t.slice(0,n).replace(/[&?]+$/,"")}function pt(e){try{const t=new URL(e);t.searchParams.delete("inc_card_id"),t.searchParams.delete("inc_track_web"),t.searchParams.delete("inc_resume_sec"),t.searchParams.delete("inc_resume_media");const r=ut(t.hash);return t.hash=r?`#${r}`:"",t.toString()}catch{return String(e||"")}}function mt(e){try{const t=new URL(e),r=String(t.searchParams.get("inc_track_web")||"").trim().toLowerCase();return r==="1"||r==="true"||r==="yes"||r==="on"}catch{return!1}}function ft(){if(window.top!==window)return;const e=window.location.href||"";if(!e||!/inc_(card_id|track_web|resume_sec|resume_media)|__incremento_resume__=1/.test(e))return;const t=pt(e);if(!(!t||t===e))try{history.replaceState(history.state,document.title||"",t),ue=t}catch{}}function Se(){const e=Array.from(document.querySelectorAll("video"));return e.length===0?null:(e.sort((t,r)=>{const n=(t.videoWidth||0)*(t.videoHeight||0);return(r.videoWidth||0)*(r.videoHeight||0)-n}),e[0])}function ce(e,t=12){const r=Math.max(0,Math.floor(Number(e)||0));if(r<=0)return!1;const n=Se();if(!n)return t>0&&window.setTimeout(()=>ce(r,t-1),500),!1;try{return n.currentTime=r,T(`Resumed to ${r}s`),!0}catch{return t>0&&window.setTimeout(()=>ce(r,t-1),500),!1}}function Q(){var a,l;const e=window.location.href||"",{provider:t,videoId:r}=dt(),n=Se(),i=t?e:String((n==null?void 0:n.currentSrc)||(n==null?void 0:n.src)||"").trim(),o=String(((a=n==null?void 0:n.getAttribute)==null?void 0:a.call(n,"title"))||((l=n==null?void 0:n.getAttribute)==null?void 0:l.call(n,"aria-label"))||document.title||"").trim();return{provider:t,videoId:r,video:n,mediaUrl:i,mediaTitle:o}}function ht(){const{provider:e,video:t}=Q();let r=-1,n=!1;if(t&&(r=Math.max(0,Math.floor(Number(t.currentTime)||0)),n=!0),e==="youtube"&&r<=0){const i=de();i>=0&&(r=i,n=!0)}if(e==="vimeo"&&r<=0){const i=se();i>=0&&(r=i,n=!0)}return{found:n,seconds:n?Math.max(0,r):0}}function gt(){const e=window.location.href||"",{provider:t,videoId:r,mediaUrl:n,mediaTitle:i}=Q(),o=ht();return{ok:!0,pageUrl:e,pageTitle:document.title||"",provider:t,videoId:r,mediaUrl:n,mediaTitle:i,hasDetectedTime:!!o.found,seconds:Math.max(0,Math.floor(Number(o.seconds)||0)),timeText:o.found?xe(o.seconds):""}}function _e(e){const t=String(e||"").trim();if(!t)return-1;const r=t.split(":").map(n=>n.trim());return r.every(n=>/^\d+$/.test(n))?r.length===2?Number(r[0])*60+Number(r[1]):r.length===3?Number(r[0])*3600+Number(r[1])*60+Number(r[2]):-1:-1}function se(){const e=Array.from(document.querySelectorAll('[data-progress-bar-timecode="true"], [class*="Timecode_module_timecode__"]'));for(const t of e){const r=String((t==null?void 0:t.textContent)||"").trim(),n=_e(r);if(n>=0)return n}return-1}function de(){const e=Array.from(document.querySelectorAll(".ytp-time-current, [class*='ytp-time-current']"));for(const t of e){const r=String((t==null?void 0:t.textContent)||"").trim(),n=_e(r);if(n>=0)return n}return-1}async function ke(){try{const e=await K({type:"GET_LINKED_CARD_CONTEXT",url:window.location.href||""});if(!(e!=null&&e.linked)||Number(e.cardId)<=0){W(null);return}const t=await K({type:"LOAD_BROWSER_MEDIA_REF"});if(!(t!=null&&t.ok)||!(t!=null&&t.hasReference)){W(null);return}W(t)}catch{W(null)}}let Ne=-1,Be=0,Me=-1,Ae=0,Z=!1,R=!0,ee=null,ue=window.location.href||"";function te(){R=!1,ee!==null&&(clearInterval(ee),ee=null)}function Le(e){if(!R)return!1;try{const t=z();return t!=null&&t.id?(t.sendMessage(e,()=>{try{const r=t==null?void 0:t.lastError;r&&/context invalidated/i.test(String(r.message||""))&&te()}catch{te()}}),!0):(te(),!1)}catch{return te(),!1}}function Fe(){if(!R){P(!1);return}try{const e=z();if(!(e!=null&&e.id)){P(!1);return}e.sendMessage({type:"GET_TRACKING_STATUS",url:window.location.href||""},t=>{try{if(e==null?void 0:e.lastError){P(!1);return}}catch{P(!1);return}P(!!(t!=null&&t.tracked),String((t==null?void 0:t.mode)||""))})}catch{P(!1)}}function S(e=!1,t=!1){if(!R)return;const{provider:r,videoId:n,video:i}=Q();if(!r)return;let o=-1;if(i&&(o=Math.max(0,Math.floor(Number(i.currentTime)||0))),r==="youtube"&&o<=0){const l=de();l>=0&&(o=l)}if(r==="vimeo"&&o<=0){const l=se();l>=0&&(o=l)}if(o<0)return;const a=Date.now();!e&&o===Ne&&a-Be<4e3||(Ne=o,Be=a,Le({type:"heartbeat",provider:r,videoId:n,cardId:Ce(window.location.href||""),flush:!!t,seconds:o,url:window.location.href||"",title:document.title||""}))}function L(e=!1,t=!1){if(!R)return;const r=window.location.href||"",{provider:n,videoId:i,video:o,mediaUrl:a,mediaTitle:l}=Q();if(!o&&!n)return;let c=-1;if(o&&(c=Math.max(0,Math.floor(Number(o.currentTime)||0))),n==="youtube"&&c<=0){const m=de();m>=0&&(c=m)}if(n==="vimeo"&&c<=0){const m=se();m>=0&&(c=m)}if(c<0)return;const u=Date.now();!e&&c===Me&&u-Ae<4e3||(Me=c,Ae=u,Le({type:"web_media_heartbeat",provider:n,videoId:i,cardId:Ce(r),trackEnabled:mt(r),flush:!!t,seconds:c,url:r,mediaUrl:a,mediaTitle:l,title:document.title||""}))}ee=window.setInterval(()=>{S(!1,!1),L(!1,!1)},1e3),window.setInterval(()=>{const e=window.location.href||"";e!==ue&&(ue=e,Z=!1,Fe(),ke())},750),window.addEventListener("pagehide",()=>{S(!0,!0),L(!0,!0)},{capture:!0}),window.addEventListener("beforeunload",()=>{S(!0,!0),L(!0,!0)},{capture:!0}),document.addEventListener("visibilitychange",()=>{document.visibilityState==="hidden"&&(S(!0,!0),L(!0,!0))}),document.addEventListener("timeupdate",()=>{S(!1,!1),L(!1,!1)},!0),document.addEventListener("play",()=>{S(!0,!1),L(!0,!1)},!0),document.addEventListener("pause",()=>{S(!0,!0),L(!0,!0)},!0),document.addEventListener("ended",()=>S(!0,!0),!0),window.setTimeout(()=>S(!0,!1),1200),window.setTimeout(ft,1200),window.setTimeout(Fe,300),window.setTimeout(()=>{ke()},320),window.__incrementoContentScriptState={...window.__incrementoContentScriptState||{},version:X,ready:!0}})();
