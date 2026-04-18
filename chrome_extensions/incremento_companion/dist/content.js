(()=>{var _e;const le="browser-capture-v4";if(window.__incrementoContentScriptVersion===le)return;window.__incrementoContentScriptVersion=le;const Z="incremento_browser_capture_settings",I=50,Me=0,Be=100;globalThis.__incrementoLastSelectedText=String(globalThis.__incrementoLastSelectedText||"").trim();function L(){var n;const e=String(((n=window.getSelection)==null?void 0:n.call(window).toString())||"").trim();return e?(globalThis.__incrementoLastSelectedText=e,e):String(globalThis.__incrementoLastSelectedText||"").trim()}function ce(e){const n=Number(e);return Number.isFinite(n)?Math.min(Be,Math.max(Me,Number(n.toFixed(4)))):I}function Fe(e){return Array.from(new Set(String(e||"").replaceAll(","," ").split(/\s+/).map(n=>n.trim()).filter(Boolean)))}function se(e,n){const r=Array.isArray(n)?n.filter(Boolean):[],t=r[0]||"",o=a=>a===""?"":r.includes(a)?a:t;return{titleField:o(String((e==null?void 0:e.titleField)||"")),selectedTextField:o(String((e==null?void 0:e.selectedTextField)||"")),urlField:o(String((e==null?void 0:e.urlField)||"")),snapshotField:o(String((e==null?void 0:e.snapshotField)||""))}}function Ae(e,n){const r=Array.isArray(n==null?void 0:n.noteTypes)?n.noteTypes:[],t=Array.isArray(n==null?void 0:n.deckNames)?n.deckNames.filter(Boolean):[],o=String((e==null?void 0:e.noteTypeName)||""),a=r.find(w=>(w==null?void 0:w.name)===o)||r[0]||null,l=(a==null?void 0:a.name)||"",i=Array.isArray(a==null?void 0:a.fields)?a.fields:[],s=e!=null&&e.mappingsByNoteType&&typeof e.mappingsByNoteType=="object"?e.mappingsByNoteType:{},p=se(s[l],i),f=String((e==null?void 0:e.deckName)||""),y=t.includes(f)?f:t[0]||"Default";return{noteTypeName:l,deckName:y,priority:ce(e==null?void 0:e.priority),tagsText:String((e==null?void 0:e.tagsText)||""),fieldMappings:p,mappingsByNoteType:s}}function P(e,n,r){return{...e,noteTypeName:n,fieldMappings:{...r},mappingsByNoteType:{...(e==null?void 0:e.mappingsByNoteType)||{},[n]:{...r}}}}function Ie(e,n){var r,t,o,a;return{url:String((e==null?void 0:e.url)||"").trim(),title:String((e==null?void 0:e.title)||"").trim()||String((e==null?void 0:e.url)||"").trim()||"Untitled",selectedText:String((e==null?void 0:e.selectedText)||"").trim(),noteTypeName:String((n==null?void 0:n.noteTypeName)||"").trim(),deckName:String((n==null?void 0:n.deckName)||"").trim(),tags:Fe(n==null?void 0:n.tagsText),priority:ce(n==null?void 0:n.priority),fieldMappings:{titleField:String(((r=n==null?void 0:n.fieldMappings)==null?void 0:r.titleField)||"").trim(),selectedTextField:String(((t=n==null?void 0:n.fieldMappings)==null?void 0:t.selectedTextField)||"").trim(),urlField:String(((o=n==null?void 0:n.fieldMappings)==null?void 0:o.urlField)||"").trim(),snapshotField:String(((a=n==null?void 0:n.fieldMappings)==null?void 0:a.snapshotField)||"").trim()},snapshots:Array.isArray(e==null?void 0:e.snapshots)?e.snapshots.map((l,i)=>({mimeType:"image/png",filename:String((l==null?void 0:l.filename)||`browser-capture-${i+1}.png`),base64:String((l==null?void 0:l.base64)||"").trim()})).filter(l=>l.base64):[]}}function E(e){const n=document.getElementById("incremento-video-time-toast");n&&n.remove();const r=document.createElement("div");r.id="incremento-video-time-toast",r.textContent=String(e||""),Object.assign(r.style,{position:"fixed",zIndex:2147483647,top:"10px",right:"10px",maxWidth:"320px",padding:"10px 14px",background:"rgba(0, 0, 0, 0.86)",color:"#fff",fontSize:"13px",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"6px",boxShadow:"0 2px 8px rgba(0, 0, 0, 0.4)",opacity:"0",transition:"opacity 0.2s ease"}),document.documentElement.appendChild(r),requestAnimationFrame(()=>{r.style.opacity="1"}),setTimeout(()=>{r.style.opacity="0",setTimeout(()=>r.remove(),220)},2400)}function Le(){let e=document.getElementById("incremento-tracking-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-tracking-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483646,top:"52px",right:"10px",display:"none",alignItems:"center",gap:"8px",padding:"8px 12px",background:"linear-gradient(135deg, rgba(10, 34, 64, 0.94), rgba(17, 83, 126, 0.94))",color:"#fff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",letterSpacing:"0.08em",textTransform:"uppercase",borderRadius:"999px",boxShadow:"0 4px 14px rgba(0, 0, 0, 0.28)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"none"});const n=document.createElement("span");n.textContent="●",Object.assign(n.style,{color:"#53f2a5",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(83, 242, 165, 0.85)"}),e.appendChild(n);const r=document.createElement("span");r.textContent="⚠",Object.assign(r.style,{color:"#ffd166",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(255, 209, 102, 0.55)"}),e.appendChild(r);const t=document.createElement("span");return t.id="incremento-tracking-badge-label",t.textContent="Tracking",e.appendChild(t),document.documentElement.appendChild(e),e}function F(e,n=""){const r=Le(),t=document.getElementById("incremento-tracking-badge-label");if(!(!r||!t)){if(!e){r.style.display="none";return}t.textContent=n==="web"?"Tracking Web Card":"Tracking",r.style.display="inline-flex"}}function de(e){const n=Math.max(0,Math.floor(Number(e)||0)),r=Math.floor(n/3600),t=Math.floor(n%3600/60),o=n%60;return r>0?`${r}:${String(t).padStart(2,"0")}:${String(o).padStart(2,"0")}`:`${t}:${String(o).padStart(2,"0")}`}function Pe(){let e=document.getElementById("incremento-browser-media-ref-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-browser-media-ref-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483645,top:"96px",right:"10px",display:"none",alignItems:"center",gap:"8px",maxWidth:"320px",padding:"9px 12px",background:"linear-gradient(135deg, rgba(28, 32, 48, 0.96), rgba(34, 62, 96, 0.96))",color:"#eef5ff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"14px",boxShadow:"0 5px 18px rgba(0, 0, 0, 0.30)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"auto"});const n=document.createElement("span");n.textContent="▶",Object.assign(n.style,{color:"#8fd3ff",fontSize:"11px",lineHeight:"1"}),e.appendChild(n);const r=document.createElement("span");r.id="incremento-browser-media-ref-badge-label",r.textContent="",Object.assign(r.style,{flex:"1 1 auto",minWidth:"0"}),e.appendChild(r);const t=document.createElement("button");return t.type="button",t.textContent="×",t.setAttribute("aria-label","Dismiss saved browser time badge"),Object.assign(t.style,{appearance:"none",border:"0",background:"transparent",color:"#a9bfdc",cursor:"pointer",fontSize:"16px",fontWeight:"700",lineHeight:"1",padding:"0 0 0 4px",margin:"0",pointerEvents:"auto"}),t.addEventListener("click",o=>{o.preventDefault(),o.stopPropagation(),V=!0,e.style.display="none"}),e.appendChild(t),document.documentElement.appendChild(e),e}function D(e){const n=Pe(),r=document.getElementById("incremento-browser-media-ref-badge-label");if(!n||!r)return;if(!!!(e!=null&&e.hasReference)){n.style.display="none";return}if(V)return;const o=String((e==null?void 0:e.timeText)||de(e==null?void 0:e.seconds));r.textContent=o?`Last saved ${o}`:"Last saved",n.style.display="inline-flex"}function Y(){try{return(chrome==null?void 0:chrome.runtime)||null}catch{return null}}try{const e=Y();(_e=e==null?void 0:e.onMessage)==null||_e.addListener((n,r,t)=>{var o;if(!n||!n.type)return!1;if(n.type==="SHOW_TOAST")return E(n.text||""),t==null||t({ok:!0}),!1;if(n.type==="TRIGGER_BROWSER_CAPTURE"){if(String(n.mode||"").trim().toLowerCase()==="snapshot")return X(),t==null||t({ok:!0}),!1;const l=L();return l?(G({mode:"selection",selectedText:l,snapshots:[]}).then(()=>t==null?void 0:t({ok:!0}),i=>{E((i==null?void 0:i.message)||"Failed to open browser capture."),_(),t==null||t({ok:!1,error:String((i==null?void 0:i.message)||"")})}),!0):(E("Select text on the page first."),t==null||t({ok:!1}),!1)}if(n.type==="GET_PAGE_CONTEXT")return t==null||t({ok:!0,html:((o=document.documentElement)==null?void 0:o.outerHTML)||"",selectionText:L(),title:document.title||"",url:window.location.href||""}),!1;if(n.type==="GET_CURRENT_MEDIA_CONTEXT")return t==null||t(ot()),!1;if(n.type==="APPLY_MEDIA_RESUME"){const a=te(n.seconds);return t==null||t({ok:a}),!1}return n.type==="UPDATE_BROWSER_MEDIA_REF_BADGE"&&(V=!1,D(n.reference||null),t==null||t({ok:!0})),!1})}catch{}let x=null,m=null;function U(e){return new Promise((n,r)=>{const t=Y();if(!(t!=null&&t.sendMessage)){r(new Error("Incremento extension runtime is unavailable."));return}t.sendMessage(e,o=>{const a=chrome.runtime.lastError;if(a){r(new Error(a.message||"Extension request failed."));return}n(o||null)})})}async function De(){const e=await U({type:"LOAD_BROWSER_CAPTURE_META"});if(!(e!=null&&e.ok))throw new Error(String((e==null?void 0:e.error)||"Failed to load browser capture metadata."));return e}async function Ue(e){const n=await U({type:"SUBMIT_BROWSER_CAPTURE",payload:e});if(!(n!=null&&n.ok))throw new Error(String((n==null?void 0:n.error)||"Failed to submit browser capture."));return n}async function $e(){const e=await U({type:"CAPTURE_VISIBLE_TAB"});if(!(e!=null&&e.ok)||!(e!=null&&e.dataUrl))throw new Error(String((e==null?void 0:e.error)||"Failed to capture the current tab."));return e.dataUrl}async function Oe(e){let n={};try{const r=await chrome.storage.local.get(Z);n=(r==null?void 0:r[Z])||{}}catch{n={}}return Ae(n,e)}async function We(e){try{await chrome.storage.local.set({[Z]:{noteTypeName:String((e==null?void 0:e.noteTypeName)||""),deckName:String((e==null?void 0:e.deckName)||""),priority:Number((e==null?void 0:e.priority)??I),tagsText:String((e==null?void 0:e.tagsText)||""),mappingsByNoteType:(e==null?void 0:e.mappingsByNoteType)||{}}})}catch{}}function ze(e){return!e||!(e instanceof Element)?!1:e.closest("input, textarea, select")?!0:!!e.closest('[contenteditable=""], [contenteditable="true"]')}function ue(){return!!x}function Re(e){return String((e==null?void 0:e.code)||"").toLowerCase()==="keyx"}function j(){if(x)return x;const e=document.createElement("div");e.id="incremento-browser-capture-root",e.style.all="initial";const n=e.attachShadow({mode:"open"});document.documentElement.appendChild(e);const r=document.createElement("style");r.textContent=`
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
    `,n.appendChild(r);const t=document.createElement("div");return t.className="shell",n.appendChild(t),x={host:e,shadow:n,shell:t},x}function _(){var e;(e=x==null?void 0:x.host)!=null&&e.isConnected&&x.host.remove(),x=null,m=null}function pe(){const e=j();e.shell.textContent=""}function He(e,n){const r=document.createElement("div");r.className="snapshots";for(const t of n){const o=document.createElement("div");o.className="snapshot-card";const a=document.createElement("img");a.src=t.dataUrl,a.alt=t.filename,o.appendChild(a);const l=document.createElement("div");l.className="snapshot-footer";const i=document.createElement("span");i.textContent=t.filename,l.appendChild(i);const s=document.createElement("button");s.type="button",s.textContent="Remove",s.addEventListener("click",()=>{m.snapshots=m.snapshots.filter(p=>p.id!==t.id),M()}),l.appendChild(s),o.appendChild(l),r.appendChild(o)}return r}async function M(){var Ne;const e=j(),{shell:n,shadow:r}=e,t=m;pe();const o=document.createElement("div");o.className="backdrop",o.addEventListener("click",()=>_()),n.appendChild(o);const a=document.createElement("section");a.className="panel",n.appendChild(a);const l=document.createElement("p");l.className="eyebrow",l.textContent=t.mode==="snapshot"?"Browser snapshot":"Browser selection",a.appendChild(l);const i=document.createElement("h2");i.textContent="Send capture to Anki",a.appendChild(i);const s=document.createElement("p");s.className="lead",s.textContent=t.mode==="snapshot"?`${t.snapshots.length} snapshot${t.snapshots.length===1?"":"s"} ready from ${t.context.url}`:`Selected text from ${t.context.url}`,a.appendChild(s);const p=document.createElement("form");p.noValidate=!0;const f=document.createElement("div");f.className="grid",p.appendChild(f);const y=(c,u,T=!1,b="")=>{const k=document.createElement("div");k.className=`field${T?" full":""}`;const Se=document.createElement("label");if(Se.textContent=c,k.appendChild(Se),k.appendChild(u),b){const ie=document.createElement("p");ie.className="field-note",ie.textContent=b,k.appendChild(ie)}return k},w=document.createElement("select");for(const c of t.meta.noteTypes){const u=document.createElement("option");u.value=c.name,u.textContent=c.name,w.appendChild(u)}w.value=t.form.noteTypeName,w.addEventListener("change",()=>{var T;const c=t.meta.noteTypes.find(b=>b.name===w.value),u=se((T=t.form.mappingsByNoteType)==null?void 0:T[w.value],(c==null?void 0:c.fields)||[]);t.form=P(t.form,w.value,u),M()}),f.appendChild(y("Note type",w));const N=document.createElement("select");for(const c of t.meta.deckNames){const u=document.createElement("option");u.value=c,u.textContent=c,N.appendChild(u)}N.value=t.form.deckName,N.addEventListener("change",()=>{t.form.deckName=N.value}),f.appendChild(y("Deck",N));const C=document.createElement("input");C.type="text",C.value=t.form.tagsText,C.placeholder="tag-one tag-two",C.addEventListener("input",()=>{t.form.tagsText=C.value}),f.appendChild(y("Tags",C,!0));const d=document.createElement("div");d.style.display="grid",d.style.gridTemplateColumns="1fr auto",d.style.gap="10px",d.style.alignItems="center";const g=document.createElement("input");g.type="range",g.min="0",g.max="100",g.step="0.1",g.value=String(t.form.priority??I);const h=document.createElement("input");h.type="number",h.min="0",h.max="100",h.step="0.1",h.style.width="92px",h.value=String(t.form.priority??I);const S=c=>{const u=Number(c),T=Number.isFinite(u)?Math.min(100,Math.max(0,u)):I;t.form.priority=Number(T.toFixed(4)),g.value=String(t.form.priority),h.value=String(t.form.priority)};g.addEventListener("input",()=>S(g.value)),h.addEventListener("change",()=>S(h.value)),d.appendChild(g),d.appendChild(h),f.appendChild(y("Priority",d));const W=["",...((Ne=t.meta.noteTypes.find(c=>c.name===t.form.noteTypeName))==null?void 0:Ne.fields)||[]],Q=(c,u)=>{const T=document.createElement("select");for(const b of W){const k=document.createElement("option");k.value=b,k.textContent=b||"Do not insert",T.appendChild(k)}return T.value=W.includes(c)?c:"",T.addEventListener("change",()=>{u(T.value)}),T},at=!!t.context.selectedText;f.appendChild(y("Page title field",Q(t.form.fieldMappings.titleField,c=>{t.form=P(t.form,t.form.noteTypeName,{...t.form.fieldMappings,titleField:c})}),!1,"The current page title is always available. First-field mappings get a unique snapshot suffix.")),f.appendChild(y("Selected text field",Q(t.form.fieldMappings.selectedTextField,c=>{t.form=P(t.form,t.form.noteTypeName,{...t.form.fieldMappings,selectedTextField:c})}),!1,at?`${t.context.selectedText.length} chars ready for insertion.`:"No text added yet.")),f.appendChild(y("Source URL field",Q(t.form.fieldMappings.urlField,c=>{t.form=P(t.form,t.form.noteTypeName,{...t.form.fieldMappings,urlField:c})}),!1,"The current page URL is always available.")),f.appendChild(y("Snapshot field",Q(t.form.fieldMappings.snapshotField,c=>{t.form=P(t.form,t.form.noteTypeName,{...t.form.fieldMappings,snapshotField:c})}),!0,t.snapshots.length>0?`${t.snapshots.length} snapshot${t.snapshots.length===1?"":"s"} selected.`:"No snapshot images in this capture."));const z=document.createElement("textarea");if(z.value=t.context.selectedText,z.placeholder=t.mode==="snapshot"?"Add text to store with these snapshots...":"Selected text will appear here. You can edit it before saving.",z.addEventListener("input",()=>{t.context.selectedText=z.value}),f.appendChild(y(t.mode==="snapshot"?"Text to add":"Selected text",z,!0,"This content is inserted into the selected text field if one is chosen.")),t.snapshots.length>0){const c=document.createElement("div");c.className="field full";const u=document.createElement("label");u.textContent="Snapshots",c.appendChild(u),c.appendChild(He(r,t.snapshots)),f.appendChild(c)}const ae=document.createElement("p");ae.className=`status${t.statusKind?` ${t.statusKind}`:""}`,ae.textContent=t.statusText,p.appendChild(ae);const R=document.createElement("div");if(R.className="actions",t.snapshots.length>0){const c=document.createElement("button");c.type="button",c.className="ghost-btn",c.textContent="Capture more",c.addEventListener("click",()=>X(t.snapshots)),R.appendChild(c)}const H=document.createElement("button");H.type="button",H.className="secondary-btn",H.textContent="Cancel",H.addEventListener("click",()=>_()),R.appendChild(H);const K=document.createElement("button");K.type="submit",K.className="primary-btn",K.textContent=t.submitting?"Saving...":"Create note",K.disabled=!!t.submitting,R.appendChild(K),p.appendChild(R),p.addEventListener("submit",async c=>{if(c.preventDefault(),t.submitting)return;const u=Ie({...t.context,snapshots:t.snapshots.map(b=>({filename:b.filename,base64:b.base64}))},t.form),T=!!(u.fieldMappings.titleField||u.selectedText&&u.fieldMappings.selectedTextField||u.fieldMappings.urlField||u.snapshots.length>0&&u.fieldMappings.snapshotField);if(!u.noteTypeName||!u.deckName){t.statusKind="error",t.statusText="Choose a note type and deck.",M();return}if(!T){t.statusKind="error",t.statusText="Map at least one available capture part to a note field.",M();return}t.submitting=!0,t.statusKind="",t.statusText="Creating note in Anki...",M();try{const b=await Ue(u);await We(t.form),E(`Created ${b.noteTypeName} note in ${b.deckName}.`),_()}catch(b){t.submitting=!1,t.statusKind="error",t.statusText=(b==null?void 0:b.message)||"Failed to create note.",M()}}),a.appendChild(p)}function Ke(e){return new Promise((n,r)=>{const t=new Image;t.onload=()=>n(t),t.onerror=()=>r(new Error("Failed to decode screenshot.")),t.src=e})}async function Ye(e,n){const r=await Ke(e),t=r.width/window.innerWidth,o=r.height/window.innerHeight,a=Math.max(0,Math.round(n.x*t)),l=Math.max(0,Math.round(n.y*o)),i=Math.max(1,Math.round(n.width*t)),s=Math.max(1,Math.round(n.height*o)),p=document.createElement("canvas");return p.width=i,p.height=s,p.getContext("2d").drawImage(r,a,l,i,s,0,0,i,s),p.toDataURL("image/png")}function je(e){const n=String(e||""),r=n.indexOf(",");return r>=0?n.slice(r+1):n}function ee(e){const n=Math.abs(e.width),r=Math.abs(e.height);return{x:e.width>=0?e.x:e.x-n,y:e.height>=0?e.y:e.y-r,width:n,height:r}}function me(e=2){return new Promise(n=>{const r=Math.max(1,Number(e)||1);let t=0;const o=()=>{if(t+=1,t>=r){n();return}requestAnimationFrame(o)};requestAnimationFrame(o)})}function Xe(e,n){if(!(e instanceof Element))return!1;const r=window.getComputedStyle(e),t=n==="x"?r.overflowX:r.overflowY;return/(auto|scroll|overlay)/.test(String(t||""))?n==="x"?e.scrollWidth>e.clientWidth:e.scrollHeight>e.clientHeight:!1}function fe(e,n){let r=e instanceof Element?e:null;for(;r;){if(Xe(r,n))return r;r=r.parentElement}const t=document.scrollingElement;return t instanceof Element?t:document.documentElement}function Ge(e,n){var p;if(!e)return;const r=((p=n==null?void 0:n.style)==null?void 0:p.pointerEvents)||"";n!=null&&n.style&&(n.style.pointerEvents="none");let t=null;try{t=document.elementFromPoint(e.clientX,e.clientY)}finally{n!=null&&n.style&&(n.style.pointerEvents=r)}const o=Number(e.deltaX)||0,a=Number(e.deltaY)||0,l=o?fe(t,"x"):null,i=a?fe(t,"y"):null,s=document.scrollingElement instanceof Element?document.scrollingElement:document.documentElement;o&&(l||s).scrollBy({left:o,top:0,behavior:"auto"}),a&&(i||s).scrollBy({left:0,top:a,behavior:"auto"})}async function qe(e,n=[]){const r=j();r.shell.style.display="none";try{await me(2);const t=await $e(),o=ee(e),a=await Ye(t,o);return{id:`${Date.now()}-${n.length}-${Math.random().toString(16).slice(2,8)}`,filename:`browser-capture-${n.length+1}.png`,dataUrl:a,base64:je(a)}}catch(t){throw new Error((t==null?void 0:t.message)||"Failed to capture the current tab.")}finally{x!=null&&x.shell&&(x.shell.style.display="",await me(1))}}function X(e=[]){var C;const n=j();pe(),m={mode:"snapshot",meta:(m==null?void 0:m.meta)||null,form:(m==null?void 0:m.form)||null,context:{url:window.location.href||"",title:document.title||"",selectedText:((C=m==null?void 0:m.context)==null?void 0:C.selectedText)||""},snapshots:[...e],statusKind:"",statusText:"",submitting:!1};const r=n.shell,t=document.createElement("div");t.className="capture-shell",r.appendChild(t);const o=document.createElement("div");o.className="capture-toolbar",o.innerHTML=`
      <strong>Snapshot Mode</strong>
      <span>Draw one or more rectangles on the page. The capture is limited to the current viewport.</span>
      <span class="spacer"></span>
    `,r.appendChild(o);const a=[...e];let l=null,i=null,s=!1;const p=()=>{o.innerHTML=`
        <strong>Snapshot Mode</strong>
        <span>Draw a rectangle to capture it immediately, then scroll and capture another area if needed.</span>
        <span class="spacer"></span>
      `;const d=document.createElement("span");d.textContent=s?"Capturing...":`${a.length} snapshot${a.length===1?"":"s"} ready`,o.appendChild(d);const g=document.createElement("button");g.type="button",g.className="toolbar-btn",g.textContent="Undo",g.disabled=s||a.length===0,g.addEventListener("click",()=>{a.pop(),p()}),o.appendChild(g);const h=document.createElement("button");h.type="button",h.className="toolbar-btn",h.textContent="Clear",h.disabled=s||a.length===0,h.addEventListener("click",()=>{a.splice(0,a.length),p()}),o.appendChild(h);const S=document.createElement("button");S.type="button",S.className="toolbar-btn",S.textContent="Cancel",S.addEventListener("click",()=>_()),o.appendChild(S);const A=document.createElement("button");A.type="button",A.className="toolbar-btn primary",A.textContent="Continue",A.addEventListener("click",()=>{var W;if(!s){if(!a.length){E("Draw at least one region first.");return}G({mode:"snapshot",selectedText:((W=m==null?void 0:m.context)==null?void 0:W.selectedText)||"",snapshots:[...a]})}}),o.appendChild(A)},f=(d,g)=>{i={x:d,y:g,width:0,height:0},l=document.createElement("div"),l.className="selection-rect",l.dataset.label=`Capture ${a.length+1}`,t.appendChild(l)},y=()=>{if(!l||!i)return;const d=ee(i);Object.assign(l.style,{left:`${d.x}px`,top:`${d.y}px`,width:`${d.width}px`,height:`${d.height}px`})};t.addEventListener("pointerdown",d=>{s||d.button!==0||d.target!==t||(d.preventDefault(),f(d.clientX,d.clientY),y())}),t.addEventListener("pointermove",d=>{i&&(d.preventDefault(),i.width=d.clientX-i.x,i.height=d.clientY-i.y,y())});const w=d=>{i||s||(d.preventDefault(),Ge(d,n.host))};t.addEventListener("wheel",w,{passive:!1}),o.addEventListener("wheel",w,{passive:!1});const N=async()=>{if(!l||!i)return;const d=ee(i),g=l;if(d.width>=24&&d.height>=24){s=!0,p();try{const h=await qe(d,a);a.push(h)}catch(h){E((h==null?void 0:h.message)||"Failed to capture the current tab.")}}else g.remove();g.remove(),l=null,i=null,s=!1,p()};t.addEventListener("pointerup",()=>{N()}),t.addEventListener("pointercancel",()=>{N()}),p()}async function G({mode:e,selectedText:n="",snapshots:r=[]}){const t=(m==null?void 0:m.meta)||await De();if(!Array.isArray(t==null?void 0:t.noteTypes)||t.noteTypes.length===0)throw new Error("No note types are available in Anki.");if(!Array.isArray(t==null?void 0:t.deckNames)||t.deckNames.length===0)throw new Error("No decks are available in Anki.");const o=(m==null?void 0:m.form)||await Oe(t);m={mode:e,meta:t,form:o,context:{url:window.location.href||"",title:document.title||"",selectedText:String(n||L()).trim()},snapshots:Array.isArray(r)?r:[],statusKind:"",statusText:"",submitting:!1},await M()}globalThis.__incrementoTriggerBrowserCapture=e=>{if(String(e||"").trim().toLowerCase()==="snapshot")return X(),{ok:!0};const r=L();return r?(G({mode:"selection",selectedText:r,snapshots:[]}).catch(t=>{E((t==null?void 0:t.message)||"Failed to open browser capture."),_()}),{ok:!0}):(E("Select text on the page first."),{ok:!1,error:"Select text on the page first."})},document.addEventListener("keydown",e=>{if(!e.altKey||!Re(e)||ue()||ze(e.target))return;if(e.metaKey){e.preventDefault(),e.stopPropagation(),X();return}if(e.ctrlKey||e.shiftKey)return;const n=L();n&&(e.preventDefault(),e.stopPropagation(),G({mode:"selection",selectedText:n,snapshots:[]}).catch(r=>{E((r==null?void 0:r.message)||"Failed to open browser capture."),_()}))},!0),document.addEventListener("selectionchange",()=>{var n;const e=String(((n=window.getSelection)==null?void 0:n.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("mouseup",()=>{var n;const e=String(((n=window.getSelection)==null?void 0:n.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keyup",()=>{var n;const e=String(((n=window.getSelection)==null?void 0:n.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keydown",e=>{e.key==="Escape"&&ue()&&(e.preventDefault(),e.stopPropagation(),_())},!0);function Ve(e){try{const n=new URL(e),r=n.searchParams.get("v");if(r)return r;const t=n.pathname.split("/").filter(Boolean);if(n.hostname==="youtu.be"&&t[0])return t[0];if((t[0]==="shorts"||t[0]==="live"||t[0]==="embed")&&t[1])return t[1]}catch{}return""}function Je(e){const n=String(e||"").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);return n?n[1]:""}function Qe(){const e=window.location.href||"",n=window.location.hostname||"";return n.includes("youtube.com")||n==="youtu.be"?{provider:"youtube",videoId:Ve(e)}:n.includes("vimeo.com")?{provider:"vimeo",videoId:Je(e)}:{provider:"",videoId:""}}function he(e){try{const r=new URL(e).searchParams.get("inc_card_id")||"",t=Number(r);if(Number.isFinite(t)&&t>0)return Math.floor(t)}catch{}return 0}function Ze(e){const n=String(e||"").replace(/^#/,"").trim();if(!n)return"";const t=n.indexOf("__incremento_resume__=1");return t<0?n:n.slice(0,t).replace(/[&?]+$/,"")}function et(e){try{const n=new URL(e);n.searchParams.delete("inc_card_id"),n.searchParams.delete("inc_track_web"),n.searchParams.delete("inc_resume_sec"),n.searchParams.delete("inc_resume_media");const r=Ze(n.hash);return n.hash=r?`#${r}`:"",n.toString()}catch{return String(e||"")}}function tt(e){try{const n=new URL(e),r=String(n.searchParams.get("inc_track_web")||"").trim().toLowerCase();return r==="1"||r==="true"||r==="yes"||r==="on"}catch{return!1}}function nt(){if(window.top!==window)return;const e=window.location.href||"";if(!e||!/inc_(card_id|track_web|resume_sec|resume_media)|__incremento_resume__=1/.test(e))return;const n=et(e);if(!(!n||n===e))try{history.replaceState(history.state,document.title||"",n),oe=n}catch{}}function ge(){const e=Array.from(document.querySelectorAll("video"));return e.length===0?null:(e.sort((n,r)=>{const t=(n.videoWidth||0)*(n.videoHeight||0);return(r.videoWidth||0)*(r.videoHeight||0)-t}),e[0])}function te(e,n=12){const r=Math.max(0,Math.floor(Number(e)||0));if(r<=0)return!1;const t=ge();if(!t)return n>0&&window.setTimeout(()=>te(r,n-1),500),!1;try{return t.currentTime=r,E(`Resumed to ${r}s`),!0}catch{return n>0&&window.setTimeout(()=>te(r,n-1),500),!1}}function q(){var l,i;const e=window.location.href||"",{provider:n,videoId:r}=Qe(),t=ge(),o=n?e:String((t==null?void 0:t.currentSrc)||(t==null?void 0:t.src)||"").trim(),a=String(((l=t==null?void 0:t.getAttribute)==null?void 0:l.call(t,"title"))||((i=t==null?void 0:t.getAttribute)==null?void 0:i.call(t,"aria-label"))||document.title||"").trim();return{provider:n,videoId:r,video:t,mediaUrl:o,mediaTitle:a}}function rt(){const{provider:e,video:n}=q();let r=-1,t=!1;if(n&&(r=Math.max(0,Math.floor(Number(n.currentTime)||0)),t=!0),e==="youtube"&&r<=0){const o=re();o>=0&&(r=o,t=!0)}if(e==="vimeo"&&r<=0){const o=ne();o>=0&&(r=o,t=!0)}return{found:t,seconds:t?Math.max(0,r):0}}function ot(){const e=window.location.href||"",{provider:n,videoId:r,mediaUrl:t,mediaTitle:o}=q(),a=rt();return{ok:!0,pageUrl:e,pageTitle:document.title||"",provider:n,videoId:r,mediaUrl:t,mediaTitle:o,hasDetectedTime:!!a.found,seconds:Math.max(0,Math.floor(Number(a.seconds)||0)),timeText:a.found?de(a.seconds):""}}function be(e){const n=String(e||"").trim();if(!n)return-1;const r=n.split(":").map(t=>t.trim());return r.every(t=>/^\d+$/.test(t))?r.length===2?Number(r[0])*60+Number(r[1]):r.length===3?Number(r[0])*3600+Number(r[1])*60+Number(r[2]):-1:-1}function ne(){const e=Array.from(document.querySelectorAll('[data-progress-bar-timecode="true"], [class*="Timecode_module_timecode__"]'));for(const n of e){const r=String((n==null?void 0:n.textContent)||"").trim(),t=be(r);if(t>=0)return t}return-1}function re(){const e=Array.from(document.querySelectorAll(".ytp-time-current, [class*='ytp-time-current']"));for(const n of e){const r=String((n==null?void 0:n.textContent)||"").trim(),t=be(r);if(t>=0)return t}return-1}async function xe(){try{const e=await U({type:"GET_LINKED_CARD_CONTEXT",url:window.location.href||""});if(!(e!=null&&e.linked)||Number(e.cardId)<=0){D(null);return}const n=await U({type:"LOAD_BROWSER_MEDIA_REF"});if(!(n!=null&&n.ok)||!(n!=null&&n.hasReference)){D(null);return}D(n)}catch{D(null)}}let ye=-1,we=0,Te=-1,Ee=0,V=!1,$=!0,O=null,ve=null,oe=window.location.href||"";function J(){$=!1,O!==null&&(clearInterval(O),O=null)}function Ce(e){if(!$)return!1;try{const n=Y();return n!=null&&n.id?(n.sendMessage(e,()=>{try{const r=n==null?void 0:n.lastError;r&&/context invalidated/i.test(String(r.message||""))&&J()}catch{J()}}),!0):(J(),!1)}catch{return J(),!1}}function ke(){if(!$){F(!1);return}try{const e=Y();if(!(e!=null&&e.id)){F(!1);return}e.sendMessage({type:"GET_TRACKING_STATUS",url:window.location.href||""},n=>{try{if(e==null?void 0:e.lastError){F(!1);return}}catch{F(!1);return}F(!!(n!=null&&n.tracked),String((n==null?void 0:n.mode)||""))})}catch{F(!1)}}function v(e=!1,n=!1){if(!$)return;const{provider:r,videoId:t,video:o}=q();if(!r)return;let a=-1;if(o&&(a=Math.max(0,Math.floor(Number(o.currentTime)||0))),r==="youtube"&&a<=0){const i=re();i>=0&&(a=i)}if(r==="vimeo"&&a<=0){const i=ne();i>=0&&(a=i)}if(a<0)return;const l=Date.now();!e&&a===ye&&l-we<4e3||(ye=a,we=l,Ce({type:"heartbeat",provider:r,videoId:t,cardId:he(window.location.href||""),flush:!!n,seconds:a,url:window.location.href||"",title:document.title||""}))}function B(e=!1,n=!1){if(!$)return;const r=window.location.href||"",{provider:t,videoId:o,video:a,mediaUrl:l,mediaTitle:i}=q();if(!a&&!t)return;let s=-1;if(a&&(s=Math.max(0,Math.floor(Number(a.currentTime)||0))),t==="youtube"&&s<=0){const f=re();f>=0&&(s=f)}if(t==="vimeo"&&s<=0){const f=ne();f>=0&&(s=f)}if(s<0)return;const p=Date.now();!e&&s===Te&&p-Ee<4e3||(Te=s,Ee=p,Ce({type:"web_media_heartbeat",provider:t,videoId:o,cardId:he(r),trackEnabled:tt(r),flush:!!n,seconds:s,url:r,mediaUrl:l,mediaTitle:i,title:document.title||""}))}O=window.setInterval(()=>{v(!1,!1),B(!1,!1)},1e3),ve=window.setInterval(()=>{const e=window.location.href||"";e!==oe&&(oe=e,V=!1,ke(),xe())},750),window.addEventListener("pagehide",()=>{v(!0,!0),B(!0,!0)},{capture:!0}),window.addEventListener("beforeunload",()=>{v(!0,!0),B(!0,!0)},{capture:!0}),document.addEventListener("visibilitychange",()=>{document.visibilityState==="hidden"&&(v(!0,!0),B(!0,!0))}),document.addEventListener("timeupdate",()=>{v(!1,!1),B(!1,!1)},!0),document.addEventListener("play",()=>{v(!0,!1),B(!0,!1)},!0),document.addEventListener("pause",()=>{v(!0,!0),B(!0,!0)},!0),document.addEventListener("ended",()=>v(!0,!0),!0),window.setTimeout(()=>v(!0,!1),1200),window.setTimeout(nt,1200),window.setTimeout(ke,300),window.setTimeout(()=>{xe()},320),window.addEventListener("unload",()=>{try{clearInterval(O),clearInterval(ve)}catch{}})})();
