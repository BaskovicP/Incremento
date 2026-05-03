import{L as ne,D as yt,n as fe,E as xt,B as $e,C as Et}from"./assets/extension-shared.js";(()=>{var Ie,Pe,De;const G="browser-capture-v6",We="incremento-browser-capture-root",re=window.__incrementoContentScriptState&&typeof window.__incrementoContentScriptState=="object"?window.__incrementoContentScriptState:{};if(re.version===G&&re.ready)return;window.__incrementoContentScriptState={...re,version:G,ready:!1},window.__incrementoContentScriptVersion=G;const ie="incremento_browser_capture_settings",P=50,ze=0,Ke=100;let L=yt,M=null;globalThis.__incrementoLastSelectedText=String(globalThis.__incrementoLastSelectedText||"").trim();function D(){var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();return e?(globalThis.__incrementoLastSelectedText=e,e):String(globalThis.__incrementoLastSelectedText||"").trim()}function he(e){const t=Number(e);return Number.isFinite(t)?Math.min(Ke,Math.max(ze,Number(t.toFixed(4)))):P}function Re(e){return Array.from(new Set(String(e||"").replaceAll(","," ").split(/\s+/).map(t=>t.trim()).filter(Boolean)))}function ge(e,t){const r=Array.isArray(t)?t.filter(Boolean):[],n=r[0]||"",o=i=>i===""?"":r.includes(i)?i:n;return{titleField:o(String((e==null?void 0:e.titleField)||"")),selectedTextField:o(String((e==null?void 0:e.selectedTextField)||"")),urlField:o(String((e==null?void 0:e.urlField)||"")),snapshotField:o(String((e==null?void 0:e.snapshotField)||""))}}function He(e,t){const r=Array.isArray(t==null?void 0:t.noteTypes)?t.noteTypes:[],n=Array.isArray(t==null?void 0:t.deckNames)?t.deckNames.filter(Boolean):[],o=String((e==null?void 0:e.noteTypeName)||""),i=r.find(E=>(E==null?void 0:E.name)===o)||r[0]||null,l=(i==null?void 0:i.name)||"",a=Array.isArray(i==null?void 0:i.fields)?i.fields:[],s=e!=null&&e.mappingsByNoteType&&typeof e.mappingsByNoteType=="object"?e.mappingsByNoteType:{},p=ge(s[l],a),f=String((e==null?void 0:e.deckName)||""),x=n.includes(f)?f:n[0]||"Default";return{noteTypeName:l,deckName:x,priority:he(e==null?void 0:e.priority),tagsText:String((e==null?void 0:e.tagsText)||""),fieldMappings:p,mappingsByNoteType:s}}function O(e,t,r){return{...e,noteTypeName:t,fieldMappings:{...r},mappingsByNoteType:{...(e==null?void 0:e.mappingsByNoteType)||{},[t]:{...r}}}}function Ye(e,t){var r,n,o,i;return{url:String((e==null?void 0:e.url)||"").trim(),title:String((e==null?void 0:e.title)||"").trim()||String((e==null?void 0:e.url)||"").trim()||"Untitled",selectedText:String((e==null?void 0:e.selectedText)||"").trim(),noteTypeName:String((t==null?void 0:t.noteTypeName)||"").trim(),deckName:String((t==null?void 0:t.deckName)||"").trim(),tags:Re(t==null?void 0:t.tagsText),priority:he(t==null?void 0:t.priority),fieldMappings:{titleField:String(((r=t==null?void 0:t.fieldMappings)==null?void 0:r.titleField)||"").trim(),selectedTextField:String(((n=t==null?void 0:t.fieldMappings)==null?void 0:n.selectedTextField)||"").trim(),urlField:String(((o=t==null?void 0:t.fieldMappings)==null?void 0:o.urlField)||"").trim(),snapshotField:String(((i=t==null?void 0:t.fieldMappings)==null?void 0:i.snapshotField)||"").trim()},snapshots:Array.isArray(e==null?void 0:e.snapshots)?e.snapshots.map((l,a)=>({mimeType:"image/png",filename:String((l==null?void 0:l.filename)||`browser-capture-${a+1}.png`),base64:String((l==null?void 0:l.base64)||"").trim()})).filter(l=>l.base64):[]}}function T(e){const t=document.getElementById("incremento-video-time-toast");t&&t.remove();const r=document.createElement("div");r.id="incremento-video-time-toast",r.textContent=String(e||""),Object.assign(r.style,{position:"fixed",zIndex:2147483647,top:"10px",right:"10px",maxWidth:"320px",padding:"10px 14px",background:"rgba(0, 0, 0, 0.86)",color:"#fff",fontSize:"13px",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"6px",boxShadow:"0 2px 8px rgba(0, 0, 0, 0.4)",opacity:"0",transition:"opacity 0.2s ease"}),document.documentElement.appendChild(r),requestAnimationFrame(()=>{r.style.opacity="1"}),setTimeout(()=>{r.style.opacity="0",setTimeout(()=>r.remove(),220)},2400)}async function je(){try{const e=await chrome.storage.local.get(ne);L=fe(e==null?void 0:e[ne])}catch{L=fe(null)}}function be(e){var o,i;const t=e instanceof Element?e:(e==null?void 0:e.parentElement)||null,r=(o=t==null?void 0:t.closest)==null?void 0:o.call(t,"a[href]");if(!r)return null;const n=String(r.href||((i=r.getAttribute)==null?void 0:i.call(r,"href"))||"").trim();return $e(n)?r:null}function ye(e){var r;if(!e)return null;const t=String(e.href||((r=e.getAttribute)==null?void 0:r.call(e,"href"))||"").trim();return $e(t)?{url:t,title:Et(e.textContent||"",t)}:null}function Ge(){let e=document.getElementById("incremento-tracking-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-tracking-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483646,top:"52px",right:"10px",display:"none",alignItems:"center",gap:"8px",padding:"8px 12px",background:"linear-gradient(135deg, rgba(10, 34, 64, 0.94), rgba(17, 83, 126, 0.94))",color:"#fff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",letterSpacing:"0.08em",textTransform:"uppercase",borderRadius:"999px",boxShadow:"0 4px 14px rgba(0, 0, 0, 0.28)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"none"});const t=document.createElement("span");t.textContent="●",Object.assign(t.style,{color:"#53f2a5",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(83, 242, 165, 0.85)"}),e.appendChild(t);const r=document.createElement("span");r.textContent="⚠",Object.assign(r.style,{color:"#ffd166",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(255, 209, 102, 0.55)"}),e.appendChild(r);const n=document.createElement("span");return n.id="incremento-tracking-badge-label",n.textContent="Tracking",e.appendChild(n),document.documentElement.appendChild(e),e}function F(e,t=""){const r=Ge(),n=document.getElementById("incremento-tracking-badge-label");if(!(!r||!n)){if(!e){r.style.display="none";return}n.textContent=t==="web"?"Tracking Web Card":"Tracking",r.style.display="inline-flex"}}function xe(e){const t=Math.max(0,Math.floor(Number(e)||0)),r=Math.floor(t/3600),n=Math.floor(t%3600/60),o=t%60;return r>0?`${r}:${String(n).padStart(2,"0")}:${String(o).padStart(2,"0")}`:`${n}:${String(o).padStart(2,"0")}`}function Xe(){let e=document.getElementById("incremento-browser-media-ref-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-browser-media-ref-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483645,top:"96px",right:"10px",display:"none",alignItems:"center",gap:"8px",maxWidth:"320px",padding:"9px 12px",background:"linear-gradient(135deg, rgba(28, 32, 48, 0.96), rgba(34, 62, 96, 0.96))",color:"#eef5ff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"14px",boxShadow:"0 5px 18px rgba(0, 0, 0, 0.30)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"auto"});const t=document.createElement("span");t.textContent="▶",Object.assign(t.style,{color:"#8fd3ff",fontSize:"11px",lineHeight:"1"}),e.appendChild(t);const r=document.createElement("span");r.id="incremento-browser-media-ref-badge-label",r.textContent="",Object.assign(r.style,{flex:"1 1 auto",minWidth:"0"}),e.appendChild(r);const n=document.createElement("button");return n.type="button",n.textContent="×",n.setAttribute("aria-label","Dismiss saved browser time badge"),Object.assign(n.style,{appearance:"none",border:"0",background:"transparent",color:"#a9bfdc",cursor:"pointer",fontSize:"16px",fontWeight:"700",lineHeight:"1",padding:"0 0 0 4px",margin:"0",pointerEvents:"auto"}),n.addEventListener("click",o=>{o.preventDefault(),o.stopPropagation(),Q=!0,e.style.display="none"}),e.appendChild(n),document.documentElement.appendChild(e),e}function U(e){const t=Xe(),r=document.getElementById("incremento-browser-media-ref-badge-label");if(!t||!r)return;if(!!!(e!=null&&e.hasReference)){t.style.display="none";return}if(Q)return;const o=String((e==null?void 0:e.timeText)||xe(e==null?void 0:e.seconds));r.textContent=o?`Last saved ${o}`:"Last saved",t.style.display="inline-flex"}function $(){try{return(chrome==null?void 0:chrome.runtime)||null}catch{return null}}je();try{(Pe=(Ie=chrome==null?void 0:chrome.storage)==null?void 0:Ie.onChanged)==null||Pe.addListener((e,t)=>{var r;t!=="local"||!e||!Object.prototype.hasOwnProperty.call(e,ne)||(L=fe((r=e[ne])==null?void 0:r.newValue))})}catch{}try{const e=$();(De=e==null?void 0:e.onMessage)==null||De.addListener((t,r,n)=>{var o;if(!t||!t.type)return!1;if(t.type==="SHOW_TOAST")return T(t.text||""),n==null||n({ok:!0}),!1;if(t.type==="TRIGGER_BROWSER_CAPTURE"){if(String(t.mode||"").trim().toLowerCase()==="snapshot")return V(),n==null||n({ok:!0}),!1;const l=D();return l?(q({mode:"selection",selectedText:l,snapshots:[]}).then(()=>n==null?void 0:n({ok:!0}),a=>{T((a==null?void 0:a.message)||"Failed to open browser capture."),v(),n==null||n({ok:!1,error:String((a==null?void 0:a.message)||"")})}),!0):(T("Select text on the page first."),n==null||n({ok:!1}),!1)}if(t.type==="GET_PAGE_CONTEXT")return n==null||n({ok:!0,html:((o=document.documentElement)==null?void 0:o.outerHTML)||"",selectionText:D(),title:document.title||"",url:window.location.href||""}),!1;if(t.type==="GET_CONTEXT_LINK_INFO")return n==null||n({ok:!0,url:String((M==null?void 0:M.url)||""),title:String((M==null?void 0:M.title)||"")}),!1;if(t.type==="GET_CURRENT_MEDIA_CONTEXT")return n==null||n(gt()),!1;if(t.type==="APPLY_MEDIA_RESUME"){const i=ce(t.seconds);return n==null||n({ok:i}),!1}return t.type==="UPDATE_BROWSER_MEDIA_REF_BADGE"&&(Q=!1,U(t.reference||null),n==null||n({ok:!0})),!1})}catch{}let b=null,m=null;function W(e){return new Promise((t,r)=>{const n=$();if(!(n!=null&&n.sendMessage)){r(new Error("Incremento extension runtime is unavailable."));return}n.sendMessage(e,o=>{const i=chrome.runtime.lastError;if(i){r(new Error(i.message||"Extension request failed."));return}t(o||null)})})}async function Ve(){const e=await W({type:"LOAD_BROWSER_CAPTURE_META"});if(!(e!=null&&e.ok))throw new Error(String((e==null?void 0:e.error)||"Failed to load browser capture metadata."));return e}async function qe(e){const t=await W({type:"SUBMIT_BROWSER_CAPTURE",payload:e});if(!(t!=null&&t.ok))throw new Error(String((t==null?void 0:t.error)||"Failed to submit browser capture."));return t}async function Je(){const e=await W({type:"CAPTURE_VISIBLE_TAB"});if(!(e!=null&&e.ok)||!(e!=null&&e.dataUrl))throw new Error(String((e==null?void 0:e.error)||"Failed to capture the current tab."));return e.dataUrl}async function Qe(e){let t={};try{const r=await chrome.storage.local.get(ie);t=(r==null?void 0:r[ie])||{}}catch{t={}}return He(t,e)}async function Ze(e){try{await chrome.storage.local.set({[ie]:{noteTypeName:String((e==null?void 0:e.noteTypeName)||""),deckName:String((e==null?void 0:e.deckName)||""),priority:Number((e==null?void 0:e.priority)??P),tagsText:String((e==null?void 0:e.tagsText)||""),mappingsByNoteType:(e==null?void 0:e.mappingsByNoteType)||{}}})}catch{}}function Ee(e){const t=e instanceof Element?e:(e==null?void 0:e.parentElement)||null;return t?t.closest("input, textarea, select")?!0:!!t.closest('[contenteditable=""], [contenteditable="true"]'):!1}function oe(){return!!b}function et(e){return String((e==null?void 0:e.code)||"").toLowerCase()==="keyx"}function ae(e){const t=b==null?void 0:b.shell,r=e==null?void 0:e.target;if(!(!t||!(r instanceof Node)||!t.contains(r))){if(e.key==="Escape"){e.preventDefault(),e.stopPropagation(),v();return}e.stopPropagation()}}function X(){if(b)return b;const e=document.createElement("div");e.id=We,e.style.all="initial";const t=e.attachShadow({mode:"open"});document.documentElement.appendChild(e),t.addEventListener("keydown",ae,!0),t.addEventListener("keypress",ae,!0),t.addEventListener("keyup",ae,!0);const r=document.createElement("style");r.textContent=`
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
    `,t.appendChild(r);const n=document.createElement("div");return n.className="shell",t.appendChild(n),b={host:e,shadow:t,shell:n},b}function v(){var e;(e=b==null?void 0:b.host)!=null&&e.isConnected&&b.host.remove(),b=null,m=null}function we(){const e=X();e.shell.textContent=""}function tt(e,t){const r=document.createElement("div");r.className="snapshots";for(const n of t){const o=document.createElement("div");o.className="snapshot-card";const i=document.createElement("img");i.src=n.dataUrl,i.alt=n.filename,o.appendChild(i);const l=document.createElement("div");l.className="snapshot-footer";const a=document.createElement("span");a.textContent=n.filename,l.appendChild(a);const s=document.createElement("button");s.type="button",s.textContent="Remove",s.addEventListener("click",()=>{m.snapshots=m.snapshots.filter(p=>p.id!==n.id),A()}),l.appendChild(s),o.appendChild(l),r.appendChild(o)}return r}async function A(){var Oe;const e=X(),{shell:t,shadow:r}=e,n=m;we();const o=document.createElement("div");o.className="backdrop",o.addEventListener("click",()=>v()),t.appendChild(o);const i=document.createElement("section");i.className="panel",t.appendChild(i);const l=document.createElement("p");l.className="eyebrow",l.textContent=n.mode==="snapshot"?"Browser snapshot":"Browser selection",i.appendChild(l);const a=document.createElement("h2");a.textContent="Send capture to Anki",i.appendChild(a);const s=document.createElement("p");s.className="lead",s.textContent=n.mode==="snapshot"?`${n.snapshots.length} snapshot${n.snapshots.length===1?"":"s"} ready from ${n.context.url}`:`Selected text from ${n.context.url}`,i.appendChild(s);const p=document.createElement("form");p.noValidate=!0;const f=document.createElement("div");f.className="grid",p.appendChild(f);const x=(c,u,w=!1,y="")=>{const _=document.createElement("div");_.className=`field${w?" full":""}`;const Ue=document.createElement("label");if(Ue.textContent=c,_.appendChild(Ue),_.appendChild(u),y){const me=document.createElement("p");me.className="field-note",me.textContent=y,_.appendChild(me)}return _},E=document.createElement("select");for(const c of n.meta.noteTypes){const u=document.createElement("option");u.value=c.name,u.textContent=c.name,E.appendChild(u)}E.value=n.form.noteTypeName,E.addEventListener("change",()=>{var w;const c=n.meta.noteTypes.find(y=>y.name===E.value),u=ge((w=n.form.mappingsByNoteType)==null?void 0:w[E.value],(c==null?void 0:c.fields)||[]);n.form=O(n.form,E.value,u),A()}),f.appendChild(x("Note type",E));const k=document.createElement("select");for(const c of n.meta.deckNames){const u=document.createElement("option");u.value=c,u.textContent=c,k.appendChild(u)}k.value=n.form.deckName,k.addEventListener("change",()=>{n.form.deckName=k.value}),f.appendChild(x("Deck",k));const S=document.createElement("input");S.type="text",S.value=n.form.tagsText,S.placeholder="tag-one tag-two",S.addEventListener("input",()=>{n.form.tagsText=S.value}),f.appendChild(x("Tags",S,!0));const d=document.createElement("div");d.style.display="grid",d.style.gridTemplateColumns="1fr auto",d.style.gap="10px",d.style.alignItems="center";const g=document.createElement("input");g.type="range",g.min="0",g.max="100",g.step="0.1",g.value=String(n.form.priority??P);const h=document.createElement("input");h.type="number",h.min="0",h.max="100",h.step="0.1",h.style.width="92px",h.value=String(n.form.priority??P);const N=c=>{const u=Number(c),w=Number.isFinite(u)?Math.min(100,Math.max(0,u)):P;n.form.priority=Number(w.toFixed(4)),g.value=String(n.form.priority),h.value=String(n.form.priority)};g.addEventListener("input",()=>N(g.value)),h.addEventListener("change",()=>N(h.value)),d.appendChild(g),d.appendChild(h),f.appendChild(x("Priority",d));const K=["",...((Oe=n.meta.noteTypes.find(c=>c.name===n.form.noteTypeName))==null?void 0:Oe.fields)||[]],te=(c,u)=>{const w=document.createElement("select");for(const y of K){const _=document.createElement("option");_.value=y,_.textContent=y||"Do not insert",w.appendChild(_)}return w.value=K.includes(c)?c:"",w.addEventListener("change",()=>{u(w.value)}),w},bt=!!n.context.selectedText;f.appendChild(x("Page title field",te(n.form.fieldMappings.titleField,c=>{n.form=O(n.form,n.form.noteTypeName,{...n.form.fieldMappings,titleField:c})}),!1,"The current page title is always available. First-field mappings get a unique snapshot suffix.")),f.appendChild(x("Selected text field",te(n.form.fieldMappings.selectedTextField,c=>{n.form=O(n.form,n.form.noteTypeName,{...n.form.fieldMappings,selectedTextField:c})}),!1,bt?`${n.context.selectedText.length} chars ready for insertion.`:"No text added yet.")),f.appendChild(x("Source URL field",te(n.form.fieldMappings.urlField,c=>{n.form=O(n.form,n.form.noteTypeName,{...n.form.fieldMappings,urlField:c})}),!1,"The current page URL is always available.")),f.appendChild(x("Snapshot field",te(n.form.fieldMappings.snapshotField,c=>{n.form=O(n.form,n.form.noteTypeName,{...n.form.fieldMappings,snapshotField:c})}),!0,n.snapshots.length>0?`${n.snapshots.length} snapshot${n.snapshots.length===1?"":"s"} selected.`:"No snapshot images in this capture."));const R=document.createElement("textarea");if(R.value=n.context.selectedText,R.placeholder=n.mode==="snapshot"?"Add text to store with these snapshots...":"Selected text will appear here. You can edit it before saving.",R.addEventListener("input",()=>{n.context.selectedText=R.value}),f.appendChild(x(n.mode==="snapshot"?"Text to add":"Selected text",R,!0,"This content is inserted into the selected text field if one is chosen.")),n.snapshots.length>0){const c=document.createElement("div");c.className="field full";const u=document.createElement("label");u.textContent="Snapshots",c.appendChild(u),c.appendChild(tt(r,n.snapshots)),f.appendChild(c)}const pe=document.createElement("p");pe.className=`status${n.statusKind?` ${n.statusKind}`:""}`,pe.textContent=n.statusText,p.appendChild(pe);const H=document.createElement("div");if(H.className="actions",n.snapshots.length>0){const c=document.createElement("button");c.type="button",c.className="ghost-btn",c.textContent="Capture more",c.addEventListener("click",()=>V(n.snapshots)),H.appendChild(c)}const Y=document.createElement("button");Y.type="button",Y.className="secondary-btn",Y.textContent="Cancel",Y.addEventListener("click",()=>v()),H.appendChild(Y);const j=document.createElement("button");j.type="submit",j.className="primary-btn",j.textContent=n.submitting?"Saving...":"Create note",j.disabled=!!n.submitting,H.appendChild(j),p.appendChild(H),p.addEventListener("submit",async c=>{if(c.preventDefault(),n.submitting)return;const u=Ye({...n.context,snapshots:n.snapshots.map(y=>({filename:y.filename,base64:y.base64}))},n.form),w=!!(u.fieldMappings.titleField||u.selectedText&&u.fieldMappings.selectedTextField||u.fieldMappings.urlField||u.snapshots.length>0&&u.fieldMappings.snapshotField);if(!u.noteTypeName||!u.deckName){n.statusKind="error",n.statusText="Choose a note type and deck.",A();return}if(!w){n.statusKind="error",n.statusText="Map at least one available capture part to a note field.",A();return}n.submitting=!0,n.statusKind="",n.statusText="Creating note in Anki...",A();try{const y=await qe(u);await Ze(n.form),T(`Created ${y.noteTypeName} note in ${y.deckName}.`),v()}catch(y){n.submitting=!1,n.statusKind="error",n.statusText=(y==null?void 0:y.message)||"Failed to create note.",A()}}),i.appendChild(p)}function nt(e){return new Promise((t,r)=>{const n=new Image;n.onload=()=>t(n),n.onerror=()=>r(new Error("Failed to decode screenshot.")),n.src=e})}async function rt(e,t){const r=await nt(e),n=r.width/window.innerWidth,o=r.height/window.innerHeight,i=Math.max(0,Math.round(t.x*n)),l=Math.max(0,Math.round(t.y*o)),a=Math.max(1,Math.round(t.width*n)),s=Math.max(1,Math.round(t.height*o)),p=document.createElement("canvas");return p.width=a,p.height=s,p.getContext("2d").drawImage(r,i,l,a,s,0,0,a,s),p.toDataURL("image/png")}function it(e){const t=String(e||""),r=t.indexOf(",");return r>=0?t.slice(r+1):t}function le(e){const t=Math.abs(e.width),r=Math.abs(e.height);return{x:e.width>=0?e.x:e.x-t,y:e.height>=0?e.y:e.y-r,width:t,height:r}}function Te(e=2){return new Promise(t=>{const r=Math.max(1,Number(e)||1);let n=0;const o=()=>{if(n+=1,n>=r){t();return}requestAnimationFrame(o)};requestAnimationFrame(o)})}function ot(e,t){if(!(e instanceof Element))return!1;const r=window.getComputedStyle(e),n=t==="x"?r.overflowX:r.overflowY;return/(auto|scroll|overlay)/.test(String(n||""))?t==="x"?e.scrollWidth>e.clientWidth:e.scrollHeight>e.clientHeight:!1}function ve(e,t){let r=e instanceof Element?e:null;for(;r;){if(ot(r,t))return r;r=r.parentElement}const n=document.scrollingElement;return n instanceof Element?n:document.documentElement}function at(e,t){var p;if(!e)return;const r=((p=t==null?void 0:t.style)==null?void 0:p.pointerEvents)||"";t!=null&&t.style&&(t.style.pointerEvents="none");let n=null;try{n=document.elementFromPoint(e.clientX,e.clientY)}finally{t!=null&&t.style&&(t.style.pointerEvents=r)}const o=Number(e.deltaX)||0,i=Number(e.deltaY)||0,l=o?ve(n,"x"):null,a=i?ve(n,"y"):null,s=document.scrollingElement instanceof Element?document.scrollingElement:document.documentElement;o&&(l||s).scrollBy({left:o,top:0,behavior:"auto"}),i&&(a||s).scrollBy({left:0,top:i,behavior:"auto"})}async function lt(e,t=[]){const r=X();r.shell.style.display="none";try{await Te(2);const n=await Je(),o=le(e),i=await rt(n,o);return{id:`${Date.now()}-${t.length}-${Math.random().toString(16).slice(2,8)}`,filename:`browser-capture-${t.length+1}.png`,dataUrl:i,base64:it(i)}}catch(n){throw new Error((n==null?void 0:n.message)||"Failed to capture the current tab.")}finally{b!=null&&b.shell&&(b.shell.style.display="",await Te(1))}}function V(e=[]){var S;const t=X();we(),m={mode:"snapshot",meta:(m==null?void 0:m.meta)||null,form:(m==null?void 0:m.form)||null,context:{url:window.location.href||"",title:document.title||"",selectedText:((S=m==null?void 0:m.context)==null?void 0:S.selectedText)||""},snapshots:[...e],statusKind:"",statusText:"",submitting:!1};const r=t.shell,n=document.createElement("div");n.className="capture-shell",r.appendChild(n);const o=document.createElement("div");o.className="capture-toolbar",o.innerHTML=`
      <strong>Snapshot Mode</strong>
      <span>Draw one or more rectangles on the page. The capture is limited to the current viewport.</span>
      <span class="spacer"></span>
    `,r.appendChild(o);const i=[...e];let l=null,a=null,s=!1;const p=()=>{o.innerHTML=`
        <strong>Snapshot Mode</strong>
        <span>Draw a rectangle to capture it immediately, then scroll and capture another area if needed.</span>
        <span class="spacer"></span>
      `;const d=document.createElement("span");d.textContent=s?"Capturing...":`${i.length} snapshot${i.length===1?"":"s"} ready`,o.appendChild(d);const g=document.createElement("button");g.type="button",g.className="toolbar-btn",g.textContent="Undo",g.disabled=s||i.length===0,g.addEventListener("click",()=>{i.pop(),p()}),o.appendChild(g);const h=document.createElement("button");h.type="button",h.className="toolbar-btn",h.textContent="Clear",h.disabled=s||i.length===0,h.addEventListener("click",()=>{i.splice(0,i.length),p()}),o.appendChild(h);const N=document.createElement("button");N.type="button",N.className="toolbar-btn",N.textContent="Cancel",N.addEventListener("click",()=>v()),o.appendChild(N);const I=document.createElement("button");I.type="button",I.className="toolbar-btn primary",I.textContent="Continue",I.addEventListener("click",()=>{var K;if(!s){if(!i.length){T("Draw at least one region first.");return}q({mode:"snapshot",selectedText:((K=m==null?void 0:m.context)==null?void 0:K.selectedText)||"",snapshots:[...i]})}}),o.appendChild(I)},f=(d,g)=>{a={x:d,y:g,width:0,height:0},l=document.createElement("div"),l.className="selection-rect",l.dataset.label=`Capture ${i.length+1}`,n.appendChild(l)},x=()=>{if(!l||!a)return;const d=le(a);Object.assign(l.style,{left:`${d.x}px`,top:`${d.y}px`,width:`${d.width}px`,height:`${d.height}px`})};n.addEventListener("pointerdown",d=>{s||d.button!==0||d.target!==n||(d.preventDefault(),f(d.clientX,d.clientY),x())}),n.addEventListener("pointermove",d=>{a&&(d.preventDefault(),a.width=d.clientX-a.x,a.height=d.clientY-a.y,x())});const E=d=>{a||s||(d.preventDefault(),at(d,t.host))};n.addEventListener("wheel",E,{passive:!1}),o.addEventListener("wheel",E,{passive:!1});const k=async()=>{if(!l||!a)return;const d=le(a),g=l;if(d.width>=24&&d.height>=24){s=!0,p();try{const h=await lt(d,i);i.push(h)}catch(h){T((h==null?void 0:h.message)||"Failed to capture the current tab.")}}else g.remove();g.remove(),l=null,a=null,s=!1,p()};n.addEventListener("pointerup",()=>{k()}),n.addEventListener("pointercancel",()=>{k()}),p()}async function q({mode:e,selectedText:t="",snapshots:r=[]}){const n=(m==null?void 0:m.meta)||await Ve();if(!Array.isArray(n==null?void 0:n.noteTypes)||n.noteTypes.length===0)throw new Error("No note types are available in Anki.");if(!Array.isArray(n==null?void 0:n.deckNames)||n.deckNames.length===0)throw new Error("No decks are available in Anki.");const o=(m==null?void 0:m.form)||await Qe(n);m={mode:e,meta:n,form:o,context:{url:window.location.href||"",title:document.title||"",selectedText:String(t||D()).trim()},snapshots:Array.isArray(r)?r:[],statusKind:"",statusText:"",submitting:!1},await A()}globalThis.__incrementoTriggerBrowserCapture=e=>{if(String(e||"").trim().toLowerCase()==="snapshot")return V(),{ok:!0};const r=D();return r?(q({mode:"selection",selectedText:r,snapshots:[]}).catch(n=>{T((n==null?void 0:n.message)||"Failed to open browser capture."),v()}),{ok:!0}):(T("Select text on the page first."),{ok:!1,error:"Select text on the page first."})},document.addEventListener("keydown",e=>{if(!e.altKey||!et(e)||oe()||Ee(e.target))return;if(e.metaKey){e.preventDefault(),e.stopPropagation(),V();return}if(e.ctrlKey||e.shiftKey)return;const t=D();t&&(e.preventDefault(),e.stopPropagation(),q({mode:"selection",selectedText:t,snapshots:[]}).catch(r=>{T((r==null?void 0:r.message)||"Failed to open browser capture."),v()}))},!0),document.addEventListener("contextmenu",e=>{const t=be(e.target);M=ye(t)},!0),document.addEventListener("click",e=>{if(!L.modifierClickEnabled||e.defaultPrevented||Number(e.button)!==0||oe()||Ee(e.target))return;const t=be(e.target);if(!t||!xt(e,L))return;const r=ye(t);if(!r)return;L.navigateAfterSave||e.preventDefault();const n=$();n==null||n.sendMessage({type:"SAVE_CLICKED_LINK_AS_WEBPAGE",url:r.url,title:r.title,sourcePageUrl:window.location.href||"",sourcePageTitle:document.title||""},o=>{var i;(i=chrome==null?void 0:chrome.runtime)==null||i.lastError})},!0),document.addEventListener("selectionchange",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("mouseup",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keyup",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keydown",e=>{e.key==="Escape"&&oe()&&(e.preventDefault(),e.stopPropagation(),v())},!0);function ct(e){try{const t=new URL(e),r=t.searchParams.get("v");if(r)return r;const n=t.pathname.split("/").filter(Boolean);if(t.hostname==="youtu.be"&&n[0])return n[0];if((n[0]==="shorts"||n[0]==="live"||n[0]==="embed")&&n[1])return n[1]}catch{}return""}function st(e){const t=String(e||"").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);return t?t[1]:""}function dt(){const e=window.location.href||"",t=window.location.hostname||"";return t.includes("youtube.com")||t==="youtu.be"?{provider:"youtube",videoId:ct(e)}:t.includes("vimeo.com")?{provider:"vimeo",videoId:st(e)}:{provider:"",videoId:""}}function Ce(e){try{const r=new URL(e).searchParams.get("inc_card_id")||"",n=Number(r);if(Number.isFinite(n)&&n>0)return Math.floor(n)}catch{}return 0}function ut(e){const t=String(e||"").replace(/^#/,"").trim();if(!t)return"";const n=t.indexOf("__incremento_resume__=1");return n<0?t:t.slice(0,n).replace(/[&?]+$/,"")}function pt(e){try{const t=new URL(e);t.searchParams.delete("inc_card_id"),t.searchParams.delete("inc_track_web"),t.searchParams.delete("inc_resume_sec"),t.searchParams.delete("inc_resume_media");const r=ut(t.hash);return t.hash=r?`#${r}`:"",t.toString()}catch{return String(e||"")}}function mt(e){try{const t=new URL(e),r=String(t.searchParams.get("inc_track_web")||"").trim().toLowerCase();return r==="1"||r==="true"||r==="yes"||r==="on"}catch{return!1}}function ft(){if(window.top!==window)return;const e=window.location.href||"";if(!e||!/inc_(card_id|track_web|resume_sec|resume_media)|__incremento_resume__=1/.test(e))return;const t=pt(e);if(!(!t||t===e))try{history.replaceState(history.state,document.title||"",t),ue=t}catch{}}function Se(){const e=Array.from(document.querySelectorAll("video"));return e.length===0?null:(e.sort((t,r)=>{const n=(t.videoWidth||0)*(t.videoHeight||0);return(r.videoWidth||0)*(r.videoHeight||0)-n}),e[0])}function ce(e,t=12){const r=Math.max(0,Math.floor(Number(e)||0));if(r<=0)return!1;const n=Se();if(!n)return t>0&&window.setTimeout(()=>ce(r,t-1),500),!1;try{return n.currentTime=r,T(`Resumed to ${r}s`),!0}catch{return t>0&&window.setTimeout(()=>ce(r,t-1),500),!1}}function J(){var l,a;const e=window.location.href||"",{provider:t,videoId:r}=dt(),n=Se(),o=t?e:String((n==null?void 0:n.currentSrc)||(n==null?void 0:n.src)||"").trim(),i=String(((l=n==null?void 0:n.getAttribute)==null?void 0:l.call(n,"title"))||((a=n==null?void 0:n.getAttribute)==null?void 0:a.call(n,"aria-label"))||document.title||"").trim();return{provider:t,videoId:r,video:n,mediaUrl:o,mediaTitle:i}}function ht(){const{provider:e,video:t}=J();let r=-1,n=!1;if(t&&(r=Math.max(0,Math.floor(Number(t.currentTime)||0)),n=!0),e==="youtube"&&r<=0){const o=de();o>=0&&(r=o,n=!0)}if(e==="vimeo"&&r<=0){const o=se();o>=0&&(r=o,n=!0)}return{found:n,seconds:n?Math.max(0,r):0}}function gt(){const e=window.location.href||"",{provider:t,videoId:r,mediaUrl:n,mediaTitle:o}=J(),i=ht();return{ok:!0,pageUrl:e,pageTitle:document.title||"",provider:t,videoId:r,mediaUrl:n,mediaTitle:o,hasDetectedTime:!!i.found,seconds:Math.max(0,Math.floor(Number(i.seconds)||0)),timeText:i.found?xe(i.seconds):""}}function _e(e){const t=String(e||"").trim();if(!t)return-1;const r=t.split(":").map(n=>n.trim());return r.every(n=>/^\d+$/.test(n))?r.length===2?Number(r[0])*60+Number(r[1]):r.length===3?Number(r[0])*3600+Number(r[1])*60+Number(r[2]):-1:-1}function se(){const e=Array.from(document.querySelectorAll('[data-progress-bar-timecode="true"], [class*="Timecode_module_timecode__"]'));for(const t of e){const r=String((t==null?void 0:t.textContent)||"").trim(),n=_e(r);if(n>=0)return n}return-1}function de(){const e=Array.from(document.querySelectorAll(".ytp-time-current, [class*='ytp-time-current']"));for(const t of e){const r=String((t==null?void 0:t.textContent)||"").trim(),n=_e(r);if(n>=0)return n}return-1}async function ke(){try{const e=await W({type:"GET_LINKED_CARD_CONTEXT",url:window.location.href||""});if(!(e!=null&&e.linked)||Number(e.cardId)<=0){U(null);return}const t=await W({type:"LOAD_BROWSER_MEDIA_REF"});if(!(t!=null&&t.ok)||!(t!=null&&t.hasReference)){U(null);return}U(t)}catch{U(null)}}let Ne=-1,Me=0,Ae=-1,Be=0,Q=!1,z=!0,Z=null,ue=window.location.href||"";function ee(){z=!1,Z!==null&&(clearInterval(Z),Z=null)}function Le(e){if(!z)return!1;try{const t=$();return t!=null&&t.id?(t.sendMessage(e,()=>{try{const r=t==null?void 0:t.lastError;r&&/context invalidated/i.test(String(r.message||""))&&ee()}catch{ee()}}),!0):(ee(),!1)}catch{return ee(),!1}}function Fe(){if(!z){F(!1);return}try{const e=$();if(!(e!=null&&e.id)){F(!1);return}e.sendMessage({type:"GET_TRACKING_STATUS",url:window.location.href||""},t=>{try{if(e==null?void 0:e.lastError){F(!1);return}}catch{F(!1);return}F(!!(t!=null&&t.tracked),String((t==null?void 0:t.mode)||""))})}catch{F(!1)}}function C(e=!1,t=!1){if(!z)return;const{provider:r,videoId:n,video:o}=J();if(!r)return;let i=-1;if(o&&(i=Math.max(0,Math.floor(Number(o.currentTime)||0))),r==="youtube"&&i<=0){const a=de();a>=0&&(i=a)}if(r==="vimeo"&&i<=0){const a=se();a>=0&&(i=a)}if(i<0)return;const l=Date.now();!e&&i===Ne&&l-Me<4e3||(Ne=i,Me=l,Le({type:"heartbeat",provider:r,videoId:n,cardId:Ce(window.location.href||""),flush:!!t,seconds:i,url:window.location.href||"",title:document.title||""}))}function B(e=!1,t=!1){if(!z)return;const r=window.location.href||"",{provider:n,videoId:o,video:i,mediaUrl:l,mediaTitle:a}=J();if(!i&&!n)return;let s=-1;if(i&&(s=Math.max(0,Math.floor(Number(i.currentTime)||0))),n==="youtube"&&s<=0){const f=de();f>=0&&(s=f)}if(n==="vimeo"&&s<=0){const f=se();f>=0&&(s=f)}if(s<0)return;const p=Date.now();!e&&s===Ae&&p-Be<4e3||(Ae=s,Be=p,Le({type:"web_media_heartbeat",provider:n,videoId:o,cardId:Ce(r),trackEnabled:mt(r),flush:!!t,seconds:s,url:r,mediaUrl:l,mediaTitle:a,title:document.title||""}))}Z=window.setInterval(()=>{C(!1,!1),B(!1,!1)},1e3),window.setInterval(()=>{const e=window.location.href||"";e!==ue&&(ue=e,Q=!1,Fe(),ke())},750),window.addEventListener("pagehide",()=>{C(!0,!0),B(!0,!0)},{capture:!0}),window.addEventListener("beforeunload",()=>{C(!0,!0),B(!0,!0)},{capture:!0}),document.addEventListener("visibilitychange",()=>{document.visibilityState==="hidden"&&(C(!0,!0),B(!0,!0))}),document.addEventListener("timeupdate",()=>{C(!1,!1),B(!1,!1)},!0),document.addEventListener("play",()=>{C(!0,!1),B(!0,!1)},!0),document.addEventListener("pause",()=>{C(!0,!0),B(!0,!0)},!0),document.addEventListener("ended",()=>C(!0,!0),!0),window.setTimeout(()=>C(!0,!1),1200),window.setTimeout(ft,1200),window.setTimeout(Fe,300),window.setTimeout(()=>{ke()},320),window.__incrementoContentScriptState={...window.__incrementoContentScriptState||{},version:G,ready:!0}})();
