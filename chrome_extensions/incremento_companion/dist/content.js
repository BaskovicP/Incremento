(()=>{var Te;const te="browser-capture-v3";if(window.__incrementoContentScriptVersion===te)return;window.__incrementoContentScriptVersion=te;const q="incremento_browser_capture_settings",M=50,Ce=0,ke=100;globalThis.__incrementoLastSelectedText=String(globalThis.__incrementoLastSelectedText||"").trim();function B(){var n;const e=String(((n=window.getSelection)==null?void 0:n.call(window).toString())||"").trim();return e?(globalThis.__incrementoLastSelectedText=e,e):String(globalThis.__incrementoLastSelectedText||"").trim()}function ne(e){const n=Number(e);return Number.isFinite(n)?Math.min(ke,Math.max(Ce,Number(n.toFixed(4)))):M}function Ne(e){return Array.from(new Set(String(e||"").replaceAll(","," ").split(/\s+/).map(n=>n.trim()).filter(Boolean)))}function re(e,n){const r=Array.isArray(n)?n.filter(Boolean):[],t=r[0]||"",o=a=>a===""?"":r.includes(a)?a:t;return{titleField:o(String((e==null?void 0:e.titleField)||"")),selectedTextField:o(String((e==null?void 0:e.selectedTextField)||"")),urlField:o(String((e==null?void 0:e.urlField)||"")),snapshotField:o(String((e==null?void 0:e.snapshotField)||""))}}function _e(e,n){const r=Array.isArray(n==null?void 0:n.noteTypes)?n.noteTypes:[],t=Array.isArray(n==null?void 0:n.deckNames)?n.deckNames.filter(Boolean):[],o=String((e==null?void 0:e.noteTypeName)||""),a=r.find(w=>(w==null?void 0:w.name)===o)||r[0]||null,i=(a==null?void 0:a.name)||"",c=Array.isArray(a==null?void 0:a.fields)?a.fields:[],s=e!=null&&e.mappingsByNoteType&&typeof e.mappingsByNoteType=="object"?e.mappingsByNoteType:{},m=re(s[i],c),f=String((e==null?void 0:e.deckName)||""),T=t.includes(f)?f:t[0]||"Default";return{noteTypeName:i,deckName:T,priority:ne(e==null?void 0:e.priority),tagsText:String((e==null?void 0:e.tagsText)||""),fieldMappings:m,mappingsByNoteType:s}}function I(e,n,r){return{...e,noteTypeName:n,fieldMappings:{...r},mappingsByNoteType:{...(e==null?void 0:e.mappingsByNoteType)||{},[n]:{...r}}}}function Se(e,n){var r,t,o,a;return{url:String((e==null?void 0:e.url)||"").trim(),title:String((e==null?void 0:e.title)||"").trim()||String((e==null?void 0:e.url)||"").trim()||"Untitled",selectedText:String((e==null?void 0:e.selectedText)||"").trim(),noteTypeName:String((n==null?void 0:n.noteTypeName)||"").trim(),deckName:String((n==null?void 0:n.deckName)||"").trim(),tags:Ne(n==null?void 0:n.tagsText),priority:ne(n==null?void 0:n.priority),fieldMappings:{titleField:String(((r=n==null?void 0:n.fieldMappings)==null?void 0:r.titleField)||"").trim(),selectedTextField:String(((t=n==null?void 0:n.fieldMappings)==null?void 0:t.selectedTextField)||"").trim(),urlField:String(((o=n==null?void 0:n.fieldMappings)==null?void 0:o.urlField)||"").trim(),snapshotField:String(((a=n==null?void 0:n.fieldMappings)==null?void 0:a.snapshotField)||"").trim()},snapshots:Array.isArray(e==null?void 0:e.snapshots)?e.snapshots.map((i,c)=>({mimeType:"image/png",filename:String((i==null?void 0:i.filename)||`browser-capture-${c+1}.png`),base64:String((i==null?void 0:i.base64)||"").trim()})).filter(i=>i.base64):[]}}function v(e){const n=document.getElementById("incremento-video-time-toast");n&&n.remove();const r=document.createElement("div");r.id="incremento-video-time-toast",r.textContent=String(e||""),Object.assign(r.style,{position:"fixed",zIndex:2147483647,top:"10px",right:"10px",maxWidth:"320px",padding:"10px 14px",background:"rgba(0, 0, 0, 0.86)",color:"#fff",fontSize:"13px",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"6px",boxShadow:"0 2px 8px rgba(0, 0, 0, 0.4)",opacity:"0",transition:"opacity 0.2s ease"}),document.documentElement.appendChild(r),requestAnimationFrame(()=>{r.style.opacity="1"}),setTimeout(()=>{r.style.opacity="0",setTimeout(()=>r.remove(),220)},2400)}function Fe(){let e=document.getElementById("incremento-tracking-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-tracking-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483646,top:"52px",right:"10px",display:"none",alignItems:"center",gap:"8px",padding:"8px 12px",background:"linear-gradient(135deg, rgba(10, 34, 64, 0.94), rgba(17, 83, 126, 0.94))",color:"#fff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",letterSpacing:"0.08em",textTransform:"uppercase",borderRadius:"999px",boxShadow:"0 4px 14px rgba(0, 0, 0, 0.28)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"none"});const n=document.createElement("span");n.textContent="●",Object.assign(n.style,{color:"#53f2a5",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(83, 242, 165, 0.85)"}),e.appendChild(n);const r=document.createElement("span");r.textContent="⚠",Object.assign(r.style,{color:"#ffd166",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(255, 209, 102, 0.55)"}),e.appendChild(r);const t=document.createElement("span");return t.id="incremento-tracking-badge-label",t.textContent="Tracking",e.appendChild(t),document.documentElement.appendChild(e),e}function L(e,n=""){const r=Fe(),t=document.getElementById("incremento-tracking-badge-label");if(!(!r||!t)){if(!e){r.style.display="none";return}t.textContent=n==="web"?"Tracking Web Card":"Tracking",r.style.display="inline-flex"}}function W(){try{return(chrome==null?void 0:chrome.runtime)||null}catch{return null}}try{const e=W();(Te=e==null?void 0:e.onMessage)==null||Te.addListener((n,r,t)=>{var o;if(!n||!n.type)return!1;if(n.type==="SHOW_TOAST")return v(n.text||""),t==null||t({ok:!0}),!1;if(n.type==="TRIGGER_BROWSER_CAPTURE"){if(String(n.mode||"").trim().toLowerCase()==="snapshot")return K(),t==null||t({ok:!0}),!1;const i=B();return i?(H({mode:"selection",selectedText:i,snapshots:[]}).then(()=>t==null?void 0:t({ok:!0}),c=>{v((c==null?void 0:c.message)||"Failed to open browser capture."),N(),t==null||t({ok:!1,error:String((c==null?void 0:c.message)||"")})}),!0):(v("Select text on the page first."),t==null||t({ok:!1}),!1)}if(n.type==="GET_PAGE_CONTEXT")return t==null||t({ok:!0,html:((o=document.documentElement)==null?void 0:o.outerHTML)||"",selectionText:B(),title:document.title||"",url:window.location.href||""}),!1;if(n.type==="APPLY_MEDIA_RESUME"){const a=X(n.seconds);return t==null||t({ok:a}),!1}return!1})}catch{}let y=null,p=null;function V(e){return new Promise((n,r)=>{const t=W();if(!(t!=null&&t.sendMessage)){r(new Error("Incremento extension runtime is unavailable."));return}t.sendMessage(e,o=>{const a=chrome.runtime.lastError;if(a){r(new Error(a.message||"Extension request failed."));return}n(o||null)})})}async function Ae(){const e=await V({type:"LOAD_BROWSER_CAPTURE_META"});if(!(e!=null&&e.ok))throw new Error(String((e==null?void 0:e.error)||"Failed to load browser capture metadata."));return e}async function Le(e){const n=await V({type:"SUBMIT_BROWSER_CAPTURE",payload:e});if(!(n!=null&&n.ok))throw new Error(String((n==null?void 0:n.error)||"Failed to submit browser capture."));return n}async function Me(){const e=await V({type:"CAPTURE_VISIBLE_TAB"});if(!(e!=null&&e.ok)||!(e!=null&&e.dataUrl))throw new Error(String((e==null?void 0:e.error)||"Failed to capture the current tab."));return e.dataUrl}async function Be(e){let n={};try{const r=await chrome.storage.local.get(q);n=(r==null?void 0:r[q])||{}}catch{n={}}return _e(n,e)}async function Ie(e){try{await chrome.storage.local.set({[q]:{noteTypeName:String((e==null?void 0:e.noteTypeName)||""),deckName:String((e==null?void 0:e.deckName)||""),priority:Number((e==null?void 0:e.priority)??M),tagsText:String((e==null?void 0:e.tagsText)||""),mappingsByNoteType:(e==null?void 0:e.mappingsByNoteType)||{}}})}catch{}}function Pe(e){return!e||!(e instanceof Element)?!1:e.closest("input, textarea, select")?!0:!!e.closest('[contenteditable=""], [contenteditable="true"]')}function ae(){return!!y}function Ue(e){return String((e==null?void 0:e.code)||"").toLowerCase()==="keyx"}function R(){if(y)return y;const e=document.createElement("div");e.id="incremento-browser-capture-root",e.style.all="initial";const n=e.attachShadow({mode:"open"});document.documentElement.appendChild(e);const r=document.createElement("style");r.textContent=`
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
    `,n.appendChild(r);const t=document.createElement("div");return t.className="shell",n.appendChild(t),y={host:e,shadow:n,shell:t},y}function N(){var e;(e=y==null?void 0:y.host)!=null&&e.isConnected&&y.host.remove(),y=null,p=null}function oe(){const e=R();e.shell.textContent=""}function $e(e,n){const r=document.createElement("div");r.className="snapshots";for(const t of n){const o=document.createElement("div");o.className="snapshot-card";const a=document.createElement("img");a.src=t.dataUrl,a.alt=t.filename,o.appendChild(a);const i=document.createElement("div");i.className="snapshot-footer";const c=document.createElement("span");c.textContent=t.filename,i.appendChild(c);const s=document.createElement("button");s.type="button",s.textContent="Remove",s.addEventListener("click",()=>{p.snapshots=p.snapshots.filter(m=>m.id!==t.id),F()}),i.appendChild(s),o.appendChild(i),r.appendChild(o)}return r}async function F(){var Ee;const e=R(),{shell:n,shadow:r}=e,t=p;oe();const o=document.createElement("div");o.className="backdrop",o.addEventListener("click",()=>N()),n.appendChild(o);const a=document.createElement("section");a.className="panel",n.appendChild(a);const i=document.createElement("p");i.className="eyebrow",i.textContent=t.mode==="snapshot"?"Browser snapshot":"Browser selection",a.appendChild(i);const c=document.createElement("h2");c.textContent="Send capture to Anki",a.appendChild(c);const s=document.createElement("p");s.className="lead",s.textContent=t.mode==="snapshot"?`${t.snapshots.length} snapshot${t.snapshots.length===1?"":"s"} ready from ${t.context.url}`:`Selected text from ${t.context.url}`,a.appendChild(s);const m=document.createElement("form");m.noValidate=!0;const f=document.createElement("div");f.className="grid",m.appendChild(f);const T=(l,u,E=!1,b="")=>{const k=document.createElement("div");k.className=`field${E?" full":""}`;const ve=document.createElement("label");if(ve.textContent=l,k.appendChild(ve),k.appendChild(u),b){const ee=document.createElement("p");ee.className="field-note",ee.textContent=b,k.appendChild(ee)}return k},w=document.createElement("select");for(const l of t.meta.noteTypes){const u=document.createElement("option");u.value=l.name,u.textContent=l.name,w.appendChild(u)}w.value=t.form.noteTypeName,w.addEventListener("change",()=>{var E;const l=t.meta.noteTypes.find(b=>b.name===w.value),u=re((E=t.form.mappingsByNoteType)==null?void 0:E[w.value],(l==null?void 0:l.fields)||[]);t.form=I(t.form,w.value,u),F()}),f.appendChild(T("Note type",w));const _=document.createElement("select");for(const l of t.meta.deckNames){const u=document.createElement("option");u.value=l,u.textContent=l,_.appendChild(u)}_.value=t.form.deckName,_.addEventListener("change",()=>{t.form.deckName=_.value}),f.appendChild(T("Deck",_));const d=document.createElement("input");d.type="text",d.value=t.form.tagsText,d.placeholder="tag-one tag-two",d.addEventListener("input",()=>{t.form.tagsText=d.value}),f.appendChild(T("Tags",d,!0));const g=document.createElement("div");g.style.display="grid",g.style.gridTemplateColumns="1fr auto",g.style.gap="10px",g.style.alignItems="center";const h=document.createElement("input");h.type="range",h.min="0",h.max="100",h.step="0.1",h.value=String(t.form.priority??M);const x=document.createElement("input");x.type="number",x.min="0",x.max="100",x.step="0.1",x.style.width="92px",x.value=String(t.form.priority??M);const S=l=>{const u=Number(l),E=Number.isFinite(u)?Math.min(100,Math.max(0,u)):M;t.form.priority=Number(E.toFixed(4)),h.value=String(t.form.priority),x.value=String(t.form.priority)};h.addEventListener("input",()=>S(h.value)),x.addEventListener("change",()=>S(x.value)),g.appendChild(h),g.appendChild(x),f.appendChild(T("Priority",g));const we=["",...((Ee=t.meta.noteTypes.find(l=>l.name===t.form.noteTypeName))==null?void 0:Ee.fields)||[]],j=(l,u)=>{const E=document.createElement("select");for(const b of we){const k=document.createElement("option");k.value=b,k.textContent=b||"Do not insert",E.appendChild(k)}return E.value=we.includes(l)?l:"",E.addEventListener("change",()=>{u(E.value)}),E},Ge=!!t.context.selectedText;f.appendChild(T("Page title field",j(t.form.fieldMappings.titleField,l=>{t.form=I(t.form,t.form.noteTypeName,{...t.form.fieldMappings,titleField:l})}),!1,"The current page title is always available. First-field mappings get a unique snapshot suffix.")),f.appendChild(T("Selected text field",j(t.form.fieldMappings.selectedTextField,l=>{t.form=I(t.form,t.form.noteTypeName,{...t.form.fieldMappings,selectedTextField:l})}),!1,Ge?`${t.context.selectedText.length} chars ready for insertion.`:"No text added yet.")),f.appendChild(T("Source URL field",j(t.form.fieldMappings.urlField,l=>{t.form=I(t.form,t.form.noteTypeName,{...t.form.fieldMappings,urlField:l})}),!1,"The current page URL is always available.")),f.appendChild(T("Snapshot field",j(t.form.fieldMappings.snapshotField,l=>{t.form=I(t.form,t.form.noteTypeName,{...t.form.fieldMappings,snapshotField:l})}),!0,t.snapshots.length>0?`${t.snapshots.length} snapshot${t.snapshots.length===1?"":"s"} selected.`:"No snapshot images in this capture."));const $=document.createElement("textarea");if($.value=t.context.selectedText,$.placeholder=t.mode==="snapshot"?"Add text to store with these snapshots...":"Selected text will appear here. You can edit it before saving.",$.addEventListener("input",()=>{t.context.selectedText=$.value}),f.appendChild(T(t.mode==="snapshot"?"Text to add":"Selected text",$,!0,"This content is inserted into the selected text field if one is chosen.")),t.snapshots.length>0){const l=document.createElement("div");l.className="field full";const u=document.createElement("label");u.textContent="Snapshots",l.appendChild(u),l.appendChild($e(r,t.snapshots)),f.appendChild(l)}const Z=document.createElement("p");Z.className=`status${t.statusKind?` ${t.statusKind}`:""}`,Z.textContent=t.statusText,m.appendChild(Z);const z=document.createElement("div");if(z.className="actions",t.snapshots.length>0){const l=document.createElement("button");l.type="button",l.className="ghost-btn",l.textContent="Capture more",l.addEventListener("click",()=>K(t.snapshots)),z.appendChild(l)}const D=document.createElement("button");D.type="button",D.className="secondary-btn",D.textContent="Cancel",D.addEventListener("click",()=>N()),z.appendChild(D);const O=document.createElement("button");O.type="submit",O.className="primary-btn",O.textContent=t.submitting?"Saving...":"Create note",O.disabled=!!t.submitting,z.appendChild(O),m.appendChild(z),m.addEventListener("submit",async l=>{if(l.preventDefault(),t.submitting)return;const u=Se({...t.context,snapshots:t.snapshots.map(b=>({filename:b.filename,base64:b.base64}))},t.form),E=!!(u.fieldMappings.titleField||u.selectedText&&u.fieldMappings.selectedTextField||u.fieldMappings.urlField||u.snapshots.length>0&&u.fieldMappings.snapshotField);if(!u.noteTypeName||!u.deckName){t.statusKind="error",t.statusText="Choose a note type and deck.",F();return}if(!E){t.statusKind="error",t.statusText="Map at least one available capture part to a note field.",F();return}t.submitting=!0,t.statusKind="",t.statusText="Creating note in Anki...",F();try{const b=await Le(u);await Ie(t.form),v(`Created ${b.noteTypeName} note in ${b.deckName}.`),N()}catch(b){t.submitting=!1,t.statusKind="error",t.statusText=(b==null?void 0:b.message)||"Failed to create note.",F()}}),a.appendChild(m)}function ze(e){return new Promise((n,r)=>{const t=new Image;t.onload=()=>n(t),t.onerror=()=>r(new Error("Failed to decode screenshot.")),t.src=e})}async function De(e,n){const r=await ze(e),t=r.width/window.innerWidth,o=r.height/window.innerHeight,a=Math.max(0,Math.round(n.x*t)),i=Math.max(0,Math.round(n.y*o)),c=Math.max(1,Math.round(n.width*t)),s=Math.max(1,Math.round(n.height*o)),m=document.createElement("canvas");return m.width=c,m.height=s,m.getContext("2d").drawImage(r,a,i,c,s,0,0,c,s),m.toDataURL("image/png")}function Oe(e){const n=String(e||""),r=n.indexOf(",");return r>=0?n.slice(r+1):n}function G(e){const n=Math.abs(e.width),r=Math.abs(e.height);return{x:e.width>=0?e.x:e.x-n,y:e.height>=0?e.y:e.y-r,width:n,height:r}}function ie(e=2){return new Promise(n=>{const r=Math.max(1,Number(e)||1);let t=0;const o=()=>{if(t+=1,t>=r){n();return}requestAnimationFrame(o)};requestAnimationFrame(o)})}async function We(e,n=[]){const r=R();r.shell.style.display="none";try{await ie(2);const t=await Me(),o=G(e),a=await De(t,o);return{id:`${Date.now()}-${n.length}-${Math.random().toString(16).slice(2,8)}`,filename:`browser-capture-${n.length+1}.png`,dataUrl:a,base64:Oe(a)}}catch(t){throw new Error((t==null?void 0:t.message)||"Failed to capture the current tab.")}finally{y!=null&&y.shell&&(y.shell.style.display="",await ie(1))}}function K(e=[]){var _;const n=R();oe(),p={mode:"snapshot",meta:(p==null?void 0:p.meta)||null,form:(p==null?void 0:p.form)||null,context:{url:window.location.href||"",title:document.title||"",selectedText:((_=p==null?void 0:p.context)==null?void 0:_.selectedText)||""},snapshots:[...e],statusKind:"",statusText:"",submitting:!1};const r=n.shell,t=document.createElement("div");t.className="capture-shell",r.appendChild(t);const o=document.createElement("div");o.className="capture-toolbar",o.innerHTML=`
      <strong>Snapshot Mode</strong>
      <span>Draw one or more rectangles on the page. The capture is limited to the current viewport.</span>
      <span class="spacer"></span>
    `,r.appendChild(o);const a=[...e];let i=null,c=null,s=!1;const m=()=>{o.innerHTML=`
        <strong>Snapshot Mode</strong>
        <span>Draw a rectangle to capture it immediately, then scroll and capture another area if needed.</span>
        <span class="spacer"></span>
      `;const d=document.createElement("span");d.textContent=s?"Capturing...":`${a.length} snapshot${a.length===1?"":"s"} ready`,o.appendChild(d);const g=document.createElement("button");g.type="button",g.className="toolbar-btn",g.textContent="Undo",g.disabled=s||a.length===0,g.addEventListener("click",()=>{a.pop(),m()}),o.appendChild(g);const h=document.createElement("button");h.type="button",h.className="toolbar-btn",h.textContent="Clear",h.disabled=s||a.length===0,h.addEventListener("click",()=>{a.splice(0,a.length),m()}),o.appendChild(h);const x=document.createElement("button");x.type="button",x.className="toolbar-btn",x.textContent="Cancel",x.addEventListener("click",()=>N()),o.appendChild(x);const S=document.createElement("button");S.type="button",S.className="toolbar-btn primary",S.textContent="Continue",S.addEventListener("click",()=>{var Q;if(!s){if(!a.length){v("Draw at least one region first.");return}H({mode:"snapshot",selectedText:((Q=p==null?void 0:p.context)==null?void 0:Q.selectedText)||"",snapshots:[...a]})}}),o.appendChild(S)},f=(d,g)=>{c={x:d,y:g,width:0,height:0},i=document.createElement("div"),i.className="selection-rect",i.dataset.label=`Capture ${a.length+1}`,t.appendChild(i)},T=()=>{if(!i||!c)return;const d=G(c);Object.assign(i.style,{left:`${d.x}px`,top:`${d.y}px`,width:`${d.width}px`,height:`${d.height}px`})};t.addEventListener("pointerdown",d=>{s||d.button!==0||d.target!==t||(d.preventDefault(),f(d.clientX,d.clientY),T())}),t.addEventListener("pointermove",d=>{c&&(d.preventDefault(),c.width=d.clientX-c.x,c.height=d.clientY-c.y,T())});const w=async()=>{if(!i||!c)return;const d=G(c),g=i;if(d.width>=24&&d.height>=24){s=!0,m();try{const h=await We(d,a);a.push(h)}catch(h){v((h==null?void 0:h.message)||"Failed to capture the current tab.")}}else g.remove();g.remove(),i=null,c=null,s=!1,m()};t.addEventListener("pointerup",()=>{w()}),t.addEventListener("pointercancel",()=>{w()}),m()}async function H({mode:e,selectedText:n="",snapshots:r=[]}){const t=(p==null?void 0:p.meta)||await Ae();if(!Array.isArray(t==null?void 0:t.noteTypes)||t.noteTypes.length===0)throw new Error("No note types are available in Anki.");if(!Array.isArray(t==null?void 0:t.deckNames)||t.deckNames.length===0)throw new Error("No decks are available in Anki.");const o=(p==null?void 0:p.form)||await Be(t);p={mode:e,meta:t,form:o,context:{url:window.location.href||"",title:document.title||"",selectedText:String(n||B()).trim()},snapshots:Array.isArray(r)?r:[],statusKind:"",statusText:"",submitting:!1},await F()}globalThis.__incrementoTriggerBrowserCapture=e=>{if(String(e||"").trim().toLowerCase()==="snapshot")return K(),{ok:!0};const r=B();return r?(H({mode:"selection",selectedText:r,snapshots:[]}).catch(t=>{v((t==null?void 0:t.message)||"Failed to open browser capture."),N()}),{ok:!0}):(v("Select text on the page first."),{ok:!1,error:"Select text on the page first."})},document.addEventListener("keydown",e=>{if(!e.altKey||!Ue(e)||ae()||Pe(e.target))return;if(e.metaKey){e.preventDefault(),e.stopPropagation(),K();return}if(e.ctrlKey||e.shiftKey)return;const n=B();n&&(e.preventDefault(),e.stopPropagation(),H({mode:"selection",selectedText:n,snapshots:[]}).catch(r=>{v((r==null?void 0:r.message)||"Failed to open browser capture."),N()}))},!0),document.addEventListener("selectionchange",()=>{var n;const e=String(((n=window.getSelection)==null?void 0:n.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("mouseup",()=>{var n;const e=String(((n=window.getSelection)==null?void 0:n.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keyup",()=>{var n;const e=String(((n=window.getSelection)==null?void 0:n.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keydown",e=>{e.key==="Escape"&&ae()&&(e.preventDefault(),e.stopPropagation(),N())},!0);function Re(e){try{const n=new URL(e),r=n.searchParams.get("v");if(r)return r;const t=n.pathname.split("/").filter(Boolean);if(n.hostname==="youtu.be"&&t[0])return t[0];if((t[0]==="shorts"||t[0]==="live"||t[0]==="embed")&&t[1])return t[1]}catch{}return""}function Ke(e){const n=String(e||"").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);return n?n[1]:""}function He(){const e=window.location.href||"",n=window.location.hostname||"";return n.includes("youtube.com")||n==="youtu.be"?{provider:"youtube",videoId:Re(e)}:n.includes("vimeo.com")?{provider:"vimeo",videoId:Ke(e)}:{provider:"",videoId:""}}function ce(e){try{const r=new URL(e).searchParams.get("inc_card_id")||"",t=Number(r);if(Number.isFinite(t)&&t>0)return Math.floor(t)}catch{}return 0}function Ye(e){const n=String(e||"").replace(/^#/,"").trim();if(!n)return"";const t=n.indexOf("__incremento_resume__=1");return t<0?n:n.slice(0,t).replace(/[&?]+$/,"")}function je(e){try{const n=new URL(e);n.searchParams.delete("inc_card_id"),n.searchParams.delete("inc_track_web"),n.searchParams.delete("inc_resume_sec"),n.searchParams.delete("inc_resume_media");const r=Ye(n.hash);return n.hash=r?`#${r}`:"",n.toString()}catch{return String(e||"")}}function qe(e){try{const n=new URL(e),r=String(n.searchParams.get("inc_track_web")||"").trim().toLowerCase();return r==="1"||r==="true"||r==="yes"||r==="on"}catch{return!1}}function Ve(){if(window.top!==window)return;const e=window.location.href||"";if(!e||!/inc_(card_id|track_web|resume_sec|resume_media)|__incremento_resume__=1/.test(e))return;const n=je(e);if(!(!n||n===e))try{history.replaceState(history.state,document.title||"",n),J=n}catch{}}function le(){const e=Array.from(document.querySelectorAll("video"));return e.length===0?null:(e.sort((n,r)=>{const t=(n.videoWidth||0)*(n.videoHeight||0);return(r.videoWidth||0)*(r.videoHeight||0)-t}),e[0])}function X(e,n=12){const r=Math.max(0,Math.floor(Number(e)||0));if(r<=0)return!1;const t=le();if(!t)return n>0&&window.setTimeout(()=>X(r,n-1),500),!1;try{return t.currentTime=r,v(`Resumed to ${r}s`),!0}catch{return n>0&&window.setTimeout(()=>X(r,n-1),500),!1}}function se(){var i,c;const e=window.location.href||"",{provider:n,videoId:r}=He(),t=le(),o=n?e:String((t==null?void 0:t.currentSrc)||(t==null?void 0:t.src)||"").trim(),a=String(((i=t==null?void 0:t.getAttribute)==null?void 0:i.call(t,"title"))||((c=t==null?void 0:t.getAttribute)==null?void 0:c.call(t,"aria-label"))||document.title||"").trim();return{provider:n,videoId:r,video:t,mediaUrl:o,mediaTitle:a}}function de(e){const n=String(e||"").trim();if(!n)return-1;const r=n.split(":").map(t=>t.trim());return r.every(t=>/^\d+$/.test(t))?r.length===2?Number(r[0])*60+Number(r[1]):r.length===3?Number(r[0])*3600+Number(r[1])*60+Number(r[2]):-1:-1}function ue(){const e=Array.from(document.querySelectorAll('[data-progress-bar-timecode="true"], [class*="Timecode_module_timecode__"]'));for(const n of e){const r=String((n==null?void 0:n.textContent)||"").trim(),t=de(r);if(t>=0)return t}return-1}function pe(){const e=Array.from(document.querySelectorAll(".ytp-time-current, [class*='ytp-time-current']"));for(const n of e){const r=String((n==null?void 0:n.textContent)||"").trim(),t=de(r);if(t>=0)return t}return-1}let me=-1,fe=0,he=-1,ge=0,P=!0,U=null,be=null,J=window.location.href||"";function Y(){P=!1,U!==null&&(clearInterval(U),U=null)}function xe(e){if(!P)return!1;try{const n=W();return n!=null&&n.id?(n.sendMessage(e,()=>{try{const r=n==null?void 0:n.lastError;r&&/context invalidated/i.test(String(r.message||""))&&Y()}catch{Y()}}),!0):(Y(),!1)}catch{return Y(),!1}}function ye(){if(!P){L(!1);return}try{const e=W();if(!(e!=null&&e.id)){L(!1);return}e.sendMessage({type:"GET_TRACKING_STATUS",url:window.location.href||""},n=>{try{if(e==null?void 0:e.lastError){L(!1);return}}catch{L(!1);return}L(!!(n!=null&&n.tracked),String((n==null?void 0:n.mode)||""))})}catch{L(!1)}}function C(e=!1,n=!1){if(!P)return;const{provider:r,videoId:t,video:o}=se();if(!r)return;let a=-1;if(o&&(a=Math.max(0,Math.floor(Number(o.currentTime)||0))),r==="youtube"&&a<=0){const c=pe();c>=0&&(a=c)}if(r==="vimeo"&&a<=0){const c=ue();c>=0&&(a=c)}if(a<0)return;const i=Date.now();!e&&a===me&&i-fe<4e3||(me=a,fe=i,xe({type:"heartbeat",provider:r,videoId:t,cardId:ce(window.location.href||""),flush:!!n,seconds:a,url:window.location.href||"",title:document.title||""}))}function A(e=!1,n=!1){if(!P)return;const r=window.location.href||"",{provider:t,videoId:o,video:a,mediaUrl:i,mediaTitle:c}=se();if(!a&&!t)return;let s=-1;if(a&&(s=Math.max(0,Math.floor(Number(a.currentTime)||0))),t==="youtube"&&s<=0){const f=pe();f>=0&&(s=f)}if(t==="vimeo"&&s<=0){const f=ue();f>=0&&(s=f)}if(s<0)return;const m=Date.now();!e&&s===he&&m-ge<4e3||(he=s,ge=m,xe({type:"web_media_heartbeat",provider:t,videoId:o,cardId:ce(r),trackEnabled:qe(r),flush:!!n,seconds:s,url:r,mediaUrl:i,mediaTitle:c,title:document.title||""}))}U=window.setInterval(()=>{C(!1,!1),A(!1,!1)},1e3),be=window.setInterval(()=>{const e=window.location.href||"";e!==J&&(J=e,ye())},750),window.addEventListener("pagehide",()=>{C(!0,!0),A(!0,!0)},{capture:!0}),window.addEventListener("beforeunload",()=>{C(!0,!0),A(!0,!0)},{capture:!0}),document.addEventListener("visibilitychange",()=>{document.visibilityState==="hidden"&&(C(!0,!0),A(!0,!0))}),document.addEventListener("timeupdate",()=>{C(!1,!1),A(!1,!1)},!0),document.addEventListener("play",()=>{C(!0,!1),A(!0,!1)},!0),document.addEventListener("pause",()=>{C(!0,!0),A(!0,!0)},!0),document.addEventListener("ended",()=>C(!0,!0),!0),window.setTimeout(()=>C(!0,!1),1200),window.setTimeout(Ve,1200),window.setTimeout(ye,300),window.addEventListener("unload",()=>{try{clearInterval(U),clearInterval(be)}catch{}})})();
