(()=>{var Ee;const ne="browser-capture-v3";if(window.__incrementoContentScriptVersion===ne)return;window.__incrementoContentScriptVersion=ne;const V="incremento_browser_capture_settings",M=50,ke=0,Ne=100;globalThis.__incrementoLastSelectedText=String(globalThis.__incrementoLastSelectedText||"").trim();function I(){var n;const e=String(((n=window.getSelection)==null?void 0:n.call(window).toString())||"").trim();return e?(globalThis.__incrementoLastSelectedText=e,e):String(globalThis.__incrementoLastSelectedText||"").trim()}function re(e){const n=Number(e);return Number.isFinite(n)?Math.min(Ne,Math.max(ke,Number(n.toFixed(4)))):M}function _e(e){return Array.from(new Set(String(e||"").replaceAll(","," ").split(/\s+/).map(n=>n.trim()).filter(Boolean)))}function oe(e,n){const r=Array.isArray(n)?n.filter(Boolean):[],t=r[0]||"",i=o=>o===""?"":r.includes(o)?o:t;return{titleField:i(String((e==null?void 0:e.titleField)||"")),selectedTextField:i(String((e==null?void 0:e.selectedTextField)||"")),urlField:i(String((e==null?void 0:e.urlField)||"")),snapshotField:i(String((e==null?void 0:e.snapshotField)||""))}}function Se(e,n){const r=Array.isArray(n==null?void 0:n.noteTypes)?n.noteTypes:[],t=Array.isArray(n==null?void 0:n.deckNames)?n.deckNames.filter(Boolean):[],i=String((e==null?void 0:e.noteTypeName)||""),o=r.find(w=>(w==null?void 0:w.name)===i)||r[0]||null,l=(o==null?void 0:o.name)||"",a=Array.isArray(o==null?void 0:o.fields)?o.fields:[],s=e!=null&&e.mappingsByNoteType&&typeof e.mappingsByNoteType=="object"?e.mappingsByNoteType:{},p=oe(s[l],a),f=String((e==null?void 0:e.deckName)||""),x=t.includes(f)?f:t[0]||"Default";return{noteTypeName:l,deckName:x,priority:re(e==null?void 0:e.priority),tagsText:String((e==null?void 0:e.tagsText)||""),fieldMappings:p,mappingsByNoteType:s}}function P(e,n,r){return{...e,noteTypeName:n,fieldMappings:{...r},mappingsByNoteType:{...(e==null?void 0:e.mappingsByNoteType)||{},[n]:{...r}}}}function Fe(e,n){var r,t,i,o;return{url:String((e==null?void 0:e.url)||"").trim(),title:String((e==null?void 0:e.title)||"").trim()||String((e==null?void 0:e.url)||"").trim()||"Untitled",selectedText:String((e==null?void 0:e.selectedText)||"").trim(),noteTypeName:String((n==null?void 0:n.noteTypeName)||"").trim(),deckName:String((n==null?void 0:n.deckName)||"").trim(),tags:_e(n==null?void 0:n.tagsText),priority:re(n==null?void 0:n.priority),fieldMappings:{titleField:String(((r=n==null?void 0:n.fieldMappings)==null?void 0:r.titleField)||"").trim(),selectedTextField:String(((t=n==null?void 0:n.fieldMappings)==null?void 0:t.selectedTextField)||"").trim(),urlField:String(((i=n==null?void 0:n.fieldMappings)==null?void 0:i.urlField)||"").trim(),snapshotField:String(((o=n==null?void 0:n.fieldMappings)==null?void 0:o.snapshotField)||"").trim()},snapshots:Array.isArray(e==null?void 0:e.snapshots)?e.snapshots.map((l,a)=>({mimeType:"image/png",filename:String((l==null?void 0:l.filename)||`browser-capture-${a+1}.png`),base64:String((l==null?void 0:l.base64)||"").trim()})).filter(l=>l.base64):[]}}function E(e){const n=document.getElementById("incremento-video-time-toast");n&&n.remove();const r=document.createElement("div");r.id="incremento-video-time-toast",r.textContent=String(e||""),Object.assign(r.style,{position:"fixed",zIndex:2147483647,top:"10px",right:"10px",maxWidth:"320px",padding:"10px 14px",background:"rgba(0, 0, 0, 0.86)",color:"#fff",fontSize:"13px",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"6px",boxShadow:"0 2px 8px rgba(0, 0, 0, 0.4)",opacity:"0",transition:"opacity 0.2s ease"}),document.documentElement.appendChild(r),requestAnimationFrame(()=>{r.style.opacity="1"}),setTimeout(()=>{r.style.opacity="0",setTimeout(()=>r.remove(),220)},2400)}function Ae(){let e=document.getElementById("incremento-tracking-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-tracking-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483646,top:"52px",right:"10px",display:"none",alignItems:"center",gap:"8px",padding:"8px 12px",background:"linear-gradient(135deg, rgba(10, 34, 64, 0.94), rgba(17, 83, 126, 0.94))",color:"#fff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",letterSpacing:"0.08em",textTransform:"uppercase",borderRadius:"999px",boxShadow:"0 4px 14px rgba(0, 0, 0, 0.28)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"none"});const n=document.createElement("span");n.textContent="●",Object.assign(n.style,{color:"#53f2a5",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(83, 242, 165, 0.85)"}),e.appendChild(n);const r=document.createElement("span");r.textContent="⚠",Object.assign(r.style,{color:"#ffd166",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(255, 209, 102, 0.55)"}),e.appendChild(r);const t=document.createElement("span");return t.id="incremento-tracking-badge-label",t.textContent="Tracking",e.appendChild(t),document.documentElement.appendChild(e),e}function L(e,n=""){const r=Ae(),t=document.getElementById("incremento-tracking-badge-label");if(!(!r||!t)){if(!e){r.style.display="none";return}t.textContent=n==="web"?"Tracking Web Card":"Tracking",r.style.display="inline-flex"}}function Y(){try{return(chrome==null?void 0:chrome.runtime)||null}catch{return null}}try{const e=Y();(Ee=e==null?void 0:e.onMessage)==null||Ee.addListener((n,r,t)=>{var i;if(!n||!n.type)return!1;if(n.type==="SHOW_TOAST")return E(n.text||""),t==null||t({ok:!0}),!1;if(n.type==="TRIGGER_BROWSER_CAPTURE"){if(String(n.mode||"").trim().toLowerCase()==="snapshot")return K(),t==null||t({ok:!0}),!1;const l=I();return l?(X({mode:"selection",selectedText:l,snapshots:[]}).then(()=>t==null?void 0:t({ok:!0}),a=>{E((a==null?void 0:a.message)||"Failed to open browser capture."),N(),t==null||t({ok:!1,error:String((a==null?void 0:a.message)||"")})}),!0):(E("Select text on the page first."),t==null||t({ok:!1}),!1)}if(n.type==="GET_PAGE_CONTEXT")return t==null||t({ok:!0,html:((i=document.documentElement)==null?void 0:i.outerHTML)||"",selectionText:I(),title:document.title||"",url:window.location.href||""}),!1;if(n.type==="APPLY_MEDIA_RESUME"){const o=Q(n.seconds);return t==null||t({ok:o}),!1}return!1})}catch{}let y=null,m=null;function G(e){return new Promise((n,r)=>{const t=Y();if(!(t!=null&&t.sendMessage)){r(new Error("Incremento extension runtime is unavailable."));return}t.sendMessage(e,i=>{const o=chrome.runtime.lastError;if(o){r(new Error(o.message||"Extension request failed."));return}n(i||null)})})}async function Le(){const e=await G({type:"LOAD_BROWSER_CAPTURE_META"});if(!(e!=null&&e.ok))throw new Error(String((e==null?void 0:e.error)||"Failed to load browser capture metadata."));return e}async function Be(e){const n=await G({type:"SUBMIT_BROWSER_CAPTURE",payload:e});if(!(n!=null&&n.ok))throw new Error(String((n==null?void 0:n.error)||"Failed to submit browser capture."));return n}async function Me(){const e=await G({type:"CAPTURE_VISIBLE_TAB"});if(!(e!=null&&e.ok)||!(e!=null&&e.dataUrl))throw new Error(String((e==null?void 0:e.error)||"Failed to capture the current tab."));return e.dataUrl}async function Ie(e){let n={};try{const r=await chrome.storage.local.get(V);n=(r==null?void 0:r[V])||{}}catch{n={}}return Se(n,e)}async function Pe(e){try{await chrome.storage.local.set({[V]:{noteTypeName:String((e==null?void 0:e.noteTypeName)||""),deckName:String((e==null?void 0:e.deckName)||""),priority:Number((e==null?void 0:e.priority)??M),tagsText:String((e==null?void 0:e.tagsText)||""),mappingsByNoteType:(e==null?void 0:e.mappingsByNoteType)||{}}})}catch{}}function Ue(e){return!e||!(e instanceof Element)?!1:e.closest("input, textarea, select")?!0:!!e.closest('[contenteditable=""], [contenteditable="true"]')}function ie(){return!!y}function $e(e){return String((e==null?void 0:e.code)||"").toLowerCase()==="keyx"}function H(){if(y)return y;const e=document.createElement("div");e.id="incremento-browser-capture-root",e.style.all="initial";const n=e.attachShadow({mode:"open"});document.documentElement.appendChild(e);const r=document.createElement("style");r.textContent=`
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
    `,n.appendChild(r);const t=document.createElement("div");return t.className="shell",n.appendChild(t),y={host:e,shadow:n,shell:t},y}function N(){var e;(e=y==null?void 0:y.host)!=null&&e.isConnected&&y.host.remove(),y=null,m=null}function ae(){const e=H();e.shell.textContent=""}function De(e,n){const r=document.createElement("div");r.className="snapshots";for(const t of n){const i=document.createElement("div");i.className="snapshot-card";const o=document.createElement("img");o.src=t.dataUrl,o.alt=t.filename,i.appendChild(o);const l=document.createElement("div");l.className="snapshot-footer";const a=document.createElement("span");a.textContent=t.filename,l.appendChild(a);const s=document.createElement("button");s.type="button",s.textContent="Remove",s.addEventListener("click",()=>{m.snapshots=m.snapshots.filter(p=>p.id!==t.id),F()}),l.appendChild(s),i.appendChild(l),r.appendChild(i)}return r}async function F(){var ve;const e=H(),{shell:n,shadow:r}=e,t=m;ae();const i=document.createElement("div");i.className="backdrop",i.addEventListener("click",()=>N()),n.appendChild(i);const o=document.createElement("section");o.className="panel",n.appendChild(o);const l=document.createElement("p");l.className="eyebrow",l.textContent=t.mode==="snapshot"?"Browser snapshot":"Browser selection",o.appendChild(l);const a=document.createElement("h2");a.textContent="Send capture to Anki",o.appendChild(a);const s=document.createElement("p");s.className="lead",s.textContent=t.mode==="snapshot"?`${t.snapshots.length} snapshot${t.snapshots.length===1?"":"s"} ready from ${t.context.url}`:`Selected text from ${t.context.url}`,o.appendChild(s);const p=document.createElement("form");p.noValidate=!0;const f=document.createElement("div");f.className="grid",p.appendChild(f);const x=(c,u,T=!1,b="")=>{const k=document.createElement("div");k.className=`field${T?" full":""}`;const Ce=document.createElement("label");if(Ce.textContent=c,k.appendChild(Ce),k.appendChild(u),b){const te=document.createElement("p");te.className="field-note",te.textContent=b,k.appendChild(te)}return k},w=document.createElement("select");for(const c of t.meta.noteTypes){const u=document.createElement("option");u.value=c.name,u.textContent=c.name,w.appendChild(u)}w.value=t.form.noteTypeName,w.addEventListener("change",()=>{var T;const c=t.meta.noteTypes.find(b=>b.name===w.value),u=oe((T=t.form.mappingsByNoteType)==null?void 0:T[w.value],(c==null?void 0:c.fields)||[]);t.form=P(t.form,w.value,u),F()}),f.appendChild(x("Note type",w));const _=document.createElement("select");for(const c of t.meta.deckNames){const u=document.createElement("option");u.value=c,u.textContent=c,_.appendChild(u)}_.value=t.form.deckName,_.addEventListener("change",()=>{t.form.deckName=_.value}),f.appendChild(x("Deck",_));const C=document.createElement("input");C.type="text",C.value=t.form.tagsText,C.placeholder="tag-one tag-two",C.addEventListener("input",()=>{t.form.tagsText=C.value}),f.appendChild(x("Tags",C,!0));const d=document.createElement("div");d.style.display="grid",d.style.gridTemplateColumns="1fr auto",d.style.gap="10px",d.style.alignItems="center";const g=document.createElement("input");g.type="range",g.min="0",g.max="100",g.step="0.1",g.value=String(t.form.priority??M);const h=document.createElement("input");h.type="number",h.min="0",h.max="100",h.step="0.1",h.style.width="92px",h.value=String(t.form.priority??M);const S=c=>{const u=Number(c),T=Number.isFinite(u)?Math.min(100,Math.max(0,u)):M;t.form.priority=Number(T.toFixed(4)),g.value=String(t.form.priority),h.value=String(t.form.priority)};g.addEventListener("input",()=>S(g.value)),h.addEventListener("change",()=>S(h.value)),d.appendChild(g),d.appendChild(h),f.appendChild(x("Priority",d));const D=["",...((ve=t.meta.noteTypes.find(c=>c.name===t.form.noteTypeName))==null?void 0:ve.fields)||[]],q=(c,u)=>{const T=document.createElement("select");for(const b of D){const k=document.createElement("option");k.value=b,k.textContent=b||"Do not insert",T.appendChild(k)}return T.value=D.includes(c)?c:"",T.addEventListener("change",()=>{u(T.value)}),T},Qe=!!t.context.selectedText;f.appendChild(x("Page title field",q(t.form.fieldMappings.titleField,c=>{t.form=P(t.form,t.form.noteTypeName,{...t.form.fieldMappings,titleField:c})}),!1,"The current page title is always available. First-field mappings get a unique snapshot suffix.")),f.appendChild(x("Selected text field",q(t.form.fieldMappings.selectedTextField,c=>{t.form=P(t.form,t.form.noteTypeName,{...t.form.fieldMappings,selectedTextField:c})}),!1,Qe?`${t.context.selectedText.length} chars ready for insertion.`:"No text added yet.")),f.appendChild(x("Source URL field",q(t.form.fieldMappings.urlField,c=>{t.form=P(t.form,t.form.noteTypeName,{...t.form.fieldMappings,urlField:c})}),!1,"The current page URL is always available.")),f.appendChild(x("Snapshot field",q(t.form.fieldMappings.snapshotField,c=>{t.form=P(t.form,t.form.noteTypeName,{...t.form.fieldMappings,snapshotField:c})}),!0,t.snapshots.length>0?`${t.snapshots.length} snapshot${t.snapshots.length===1?"":"s"} selected.`:"No snapshot images in this capture."));const z=document.createElement("textarea");if(z.value=t.context.selectedText,z.placeholder=t.mode==="snapshot"?"Add text to store with these snapshots...":"Selected text will appear here. You can edit it before saving.",z.addEventListener("input",()=>{t.context.selectedText=z.value}),f.appendChild(x(t.mode==="snapshot"?"Text to add":"Selected text",z,!0,"This content is inserted into the selected text field if one is chosen.")),t.snapshots.length>0){const c=document.createElement("div");c.className="field full";const u=document.createElement("label");u.textContent="Snapshots",c.appendChild(u),c.appendChild(De(r,t.snapshots)),f.appendChild(c)}const ee=document.createElement("p");ee.className=`status${t.statusKind?` ${t.statusKind}`:""}`,ee.textContent=t.statusText,p.appendChild(ee);const O=document.createElement("div");if(O.className="actions",t.snapshots.length>0){const c=document.createElement("button");c.type="button",c.className="ghost-btn",c.textContent="Capture more",c.addEventListener("click",()=>K(t.snapshots)),O.appendChild(c)}const W=document.createElement("button");W.type="button",W.className="secondary-btn",W.textContent="Cancel",W.addEventListener("click",()=>N()),O.appendChild(W);const R=document.createElement("button");R.type="submit",R.className="primary-btn",R.textContent=t.submitting?"Saving...":"Create note",R.disabled=!!t.submitting,O.appendChild(R),p.appendChild(O),p.addEventListener("submit",async c=>{if(c.preventDefault(),t.submitting)return;const u=Fe({...t.context,snapshots:t.snapshots.map(b=>({filename:b.filename,base64:b.base64}))},t.form),T=!!(u.fieldMappings.titleField||u.selectedText&&u.fieldMappings.selectedTextField||u.fieldMappings.urlField||u.snapshots.length>0&&u.fieldMappings.snapshotField);if(!u.noteTypeName||!u.deckName){t.statusKind="error",t.statusText="Choose a note type and deck.",F();return}if(!T){t.statusKind="error",t.statusText="Map at least one available capture part to a note field.",F();return}t.submitting=!0,t.statusKind="",t.statusText="Creating note in Anki...",F();try{const b=await Be(u);await Pe(t.form),E(`Created ${b.noteTypeName} note in ${b.deckName}.`),N()}catch(b){t.submitting=!1,t.statusKind="error",t.statusText=(b==null?void 0:b.message)||"Failed to create note.",F()}}),o.appendChild(p)}function ze(e){return new Promise((n,r)=>{const t=new Image;t.onload=()=>n(t),t.onerror=()=>r(new Error("Failed to decode screenshot.")),t.src=e})}async function Oe(e,n){const r=await ze(e),t=r.width/window.innerWidth,i=r.height/window.innerHeight,o=Math.max(0,Math.round(n.x*t)),l=Math.max(0,Math.round(n.y*i)),a=Math.max(1,Math.round(n.width*t)),s=Math.max(1,Math.round(n.height*i)),p=document.createElement("canvas");return p.width=a,p.height=s,p.getContext("2d").drawImage(r,o,l,a,s,0,0,a,s),p.toDataURL("image/png")}function We(e){const n=String(e||""),r=n.indexOf(",");return r>=0?n.slice(r+1):n}function J(e){const n=Math.abs(e.width),r=Math.abs(e.height);return{x:e.width>=0?e.x:e.x-n,y:e.height>=0?e.y:e.y-r,width:n,height:r}}function le(e=2){return new Promise(n=>{const r=Math.max(1,Number(e)||1);let t=0;const i=()=>{if(t+=1,t>=r){n();return}requestAnimationFrame(i)};requestAnimationFrame(i)})}function Re(e,n){if(!(e instanceof Element))return!1;const r=window.getComputedStyle(e),t=n==="x"?r.overflowX:r.overflowY;return/(auto|scroll|overlay)/.test(String(t||""))?n==="x"?e.scrollWidth>e.clientWidth:e.scrollHeight>e.clientHeight:!1}function ce(e,n){let r=e instanceof Element?e:null;for(;r;){if(Re(r,n))return r;r=r.parentElement}const t=document.scrollingElement;return t instanceof Element?t:document.documentElement}function Ye(e,n){var p;if(!e)return;const r=((p=n==null?void 0:n.style)==null?void 0:p.pointerEvents)||"";n!=null&&n.style&&(n.style.pointerEvents="none");let t=null;try{t=document.elementFromPoint(e.clientX,e.clientY)}finally{n!=null&&n.style&&(n.style.pointerEvents=r)}const i=Number(e.deltaX)||0,o=Number(e.deltaY)||0,l=i?ce(t,"x"):null,a=o?ce(t,"y"):null,s=document.scrollingElement instanceof Element?document.scrollingElement:document.documentElement;i&&(l||s).scrollBy({left:i,top:0,behavior:"auto"}),o&&(a||s).scrollBy({left:0,top:o,behavior:"auto"})}async function He(e,n=[]){const r=H();r.shell.style.display="none";try{await le(2);const t=await Me(),i=J(e),o=await Oe(t,i);return{id:`${Date.now()}-${n.length}-${Math.random().toString(16).slice(2,8)}`,filename:`browser-capture-${n.length+1}.png`,dataUrl:o,base64:We(o)}}catch(t){throw new Error((t==null?void 0:t.message)||"Failed to capture the current tab.")}finally{y!=null&&y.shell&&(y.shell.style.display="",await le(1))}}function K(e=[]){var C;const n=H();ae(),m={mode:"snapshot",meta:(m==null?void 0:m.meta)||null,form:(m==null?void 0:m.form)||null,context:{url:window.location.href||"",title:document.title||"",selectedText:((C=m==null?void 0:m.context)==null?void 0:C.selectedText)||""},snapshots:[...e],statusKind:"",statusText:"",submitting:!1};const r=n.shell,t=document.createElement("div");t.className="capture-shell",r.appendChild(t);const i=document.createElement("div");i.className="capture-toolbar",i.innerHTML=`
      <strong>Snapshot Mode</strong>
      <span>Draw one or more rectangles on the page. The capture is limited to the current viewport.</span>
      <span class="spacer"></span>
    `,r.appendChild(i);const o=[...e];let l=null,a=null,s=!1;const p=()=>{i.innerHTML=`
        <strong>Snapshot Mode</strong>
        <span>Draw a rectangle to capture it immediately, then scroll and capture another area if needed.</span>
        <span class="spacer"></span>
      `;const d=document.createElement("span");d.textContent=s?"Capturing...":`${o.length} snapshot${o.length===1?"":"s"} ready`,i.appendChild(d);const g=document.createElement("button");g.type="button",g.className="toolbar-btn",g.textContent="Undo",g.disabled=s||o.length===0,g.addEventListener("click",()=>{o.pop(),p()}),i.appendChild(g);const h=document.createElement("button");h.type="button",h.className="toolbar-btn",h.textContent="Clear",h.disabled=s||o.length===0,h.addEventListener("click",()=>{o.splice(0,o.length),p()}),i.appendChild(h);const S=document.createElement("button");S.type="button",S.className="toolbar-btn",S.textContent="Cancel",S.addEventListener("click",()=>N()),i.appendChild(S);const B=document.createElement("button");B.type="button",B.className="toolbar-btn primary",B.textContent="Continue",B.addEventListener("click",()=>{var D;if(!s){if(!o.length){E("Draw at least one region first.");return}X({mode:"snapshot",selectedText:((D=m==null?void 0:m.context)==null?void 0:D.selectedText)||"",snapshots:[...o]})}}),i.appendChild(B)},f=(d,g)=>{a={x:d,y:g,width:0,height:0},l=document.createElement("div"),l.className="selection-rect",l.dataset.label=`Capture ${o.length+1}`,t.appendChild(l)},x=()=>{if(!l||!a)return;const d=J(a);Object.assign(l.style,{left:`${d.x}px`,top:`${d.y}px`,width:`${d.width}px`,height:`${d.height}px`})};t.addEventListener("pointerdown",d=>{s||d.button!==0||d.target!==t||(d.preventDefault(),f(d.clientX,d.clientY),x())}),t.addEventListener("pointermove",d=>{a&&(d.preventDefault(),a.width=d.clientX-a.x,a.height=d.clientY-a.y,x())});const w=d=>{a||s||(d.preventDefault(),Ye(d,n.host))};t.addEventListener("wheel",w,{passive:!1}),i.addEventListener("wheel",w,{passive:!1});const _=async()=>{if(!l||!a)return;const d=J(a),g=l;if(d.width>=24&&d.height>=24){s=!0,p();try{const h=await He(d,o);o.push(h)}catch(h){E((h==null?void 0:h.message)||"Failed to capture the current tab.")}}else g.remove();g.remove(),l=null,a=null,s=!1,p()};t.addEventListener("pointerup",()=>{_()}),t.addEventListener("pointercancel",()=>{_()}),p()}async function X({mode:e,selectedText:n="",snapshots:r=[]}){const t=(m==null?void 0:m.meta)||await Le();if(!Array.isArray(t==null?void 0:t.noteTypes)||t.noteTypes.length===0)throw new Error("No note types are available in Anki.");if(!Array.isArray(t==null?void 0:t.deckNames)||t.deckNames.length===0)throw new Error("No decks are available in Anki.");const i=(m==null?void 0:m.form)||await Ie(t);m={mode:e,meta:t,form:i,context:{url:window.location.href||"",title:document.title||"",selectedText:String(n||I()).trim()},snapshots:Array.isArray(r)?r:[],statusKind:"",statusText:"",submitting:!1},await F()}globalThis.__incrementoTriggerBrowserCapture=e=>{if(String(e||"").trim().toLowerCase()==="snapshot")return K(),{ok:!0};const r=I();return r?(X({mode:"selection",selectedText:r,snapshots:[]}).catch(t=>{E((t==null?void 0:t.message)||"Failed to open browser capture."),N()}),{ok:!0}):(E("Select text on the page first."),{ok:!1,error:"Select text on the page first."})},document.addEventListener("keydown",e=>{if(!e.altKey||!$e(e)||ie()||Ue(e.target))return;if(e.metaKey){e.preventDefault(),e.stopPropagation(),K();return}if(e.ctrlKey||e.shiftKey)return;const n=I();n&&(e.preventDefault(),e.stopPropagation(),X({mode:"selection",selectedText:n,snapshots:[]}).catch(r=>{E((r==null?void 0:r.message)||"Failed to open browser capture."),N()}))},!0),document.addEventListener("selectionchange",()=>{var n;const e=String(((n=window.getSelection)==null?void 0:n.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("mouseup",()=>{var n;const e=String(((n=window.getSelection)==null?void 0:n.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keyup",()=>{var n;const e=String(((n=window.getSelection)==null?void 0:n.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keydown",e=>{e.key==="Escape"&&ie()&&(e.preventDefault(),e.stopPropagation(),N())},!0);function Ke(e){try{const n=new URL(e),r=n.searchParams.get("v");if(r)return r;const t=n.pathname.split("/").filter(Boolean);if(n.hostname==="youtu.be"&&t[0])return t[0];if((t[0]==="shorts"||t[0]==="live"||t[0]==="embed")&&t[1])return t[1]}catch{}return""}function Xe(e){const n=String(e||"").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);return n?n[1]:""}function je(){const e=window.location.href||"",n=window.location.hostname||"";return n.includes("youtube.com")||n==="youtu.be"?{provider:"youtube",videoId:Ke(e)}:n.includes("vimeo.com")?{provider:"vimeo",videoId:Xe(e)}:{provider:"",videoId:""}}function se(e){try{const r=new URL(e).searchParams.get("inc_card_id")||"",t=Number(r);if(Number.isFinite(t)&&t>0)return Math.floor(t)}catch{}return 0}function qe(e){const n=String(e||"").replace(/^#/,"").trim();if(!n)return"";const t=n.indexOf("__incremento_resume__=1");return t<0?n:n.slice(0,t).replace(/[&?]+$/,"")}function Ve(e){try{const n=new URL(e);n.searchParams.delete("inc_card_id"),n.searchParams.delete("inc_track_web"),n.searchParams.delete("inc_resume_sec"),n.searchParams.delete("inc_resume_media");const r=qe(n.hash);return n.hash=r?`#${r}`:"",n.toString()}catch{return String(e||"")}}function Ge(e){try{const n=new URL(e),r=String(n.searchParams.get("inc_track_web")||"").trim().toLowerCase();return r==="1"||r==="true"||r==="yes"||r==="on"}catch{return!1}}function Je(){if(window.top!==window)return;const e=window.location.href||"";if(!e||!/inc_(card_id|track_web|resume_sec|resume_media)|__incremento_resume__=1/.test(e))return;const n=Ve(e);if(!(!n||n===e))try{history.replaceState(history.state,document.title||"",n),Z=n}catch{}}function de(){const e=Array.from(document.querySelectorAll("video"));return e.length===0?null:(e.sort((n,r)=>{const t=(n.videoWidth||0)*(n.videoHeight||0);return(r.videoWidth||0)*(r.videoHeight||0)-t}),e[0])}function Q(e,n=12){const r=Math.max(0,Math.floor(Number(e)||0));if(r<=0)return!1;const t=de();if(!t)return n>0&&window.setTimeout(()=>Q(r,n-1),500),!1;try{return t.currentTime=r,E(`Resumed to ${r}s`),!0}catch{return n>0&&window.setTimeout(()=>Q(r,n-1),500),!1}}function ue(){var l,a;const e=window.location.href||"",{provider:n,videoId:r}=je(),t=de(),i=n?e:String((t==null?void 0:t.currentSrc)||(t==null?void 0:t.src)||"").trim(),o=String(((l=t==null?void 0:t.getAttribute)==null?void 0:l.call(t,"title"))||((a=t==null?void 0:t.getAttribute)==null?void 0:a.call(t,"aria-label"))||document.title||"").trim();return{provider:n,videoId:r,video:t,mediaUrl:i,mediaTitle:o}}function pe(e){const n=String(e||"").trim();if(!n)return-1;const r=n.split(":").map(t=>t.trim());return r.every(t=>/^\d+$/.test(t))?r.length===2?Number(r[0])*60+Number(r[1]):r.length===3?Number(r[0])*3600+Number(r[1])*60+Number(r[2]):-1:-1}function me(){const e=Array.from(document.querySelectorAll('[data-progress-bar-timecode="true"], [class*="Timecode_module_timecode__"]'));for(const n of e){const r=String((n==null?void 0:n.textContent)||"").trim(),t=pe(r);if(t>=0)return t}return-1}function fe(){const e=Array.from(document.querySelectorAll(".ytp-time-current, [class*='ytp-time-current']"));for(const n of e){const r=String((n==null?void 0:n.textContent)||"").trim(),t=pe(r);if(t>=0)return t}return-1}let he=-1,ge=0,be=-1,ye=0,U=!0,$=null,xe=null,Z=window.location.href||"";function j(){U=!1,$!==null&&(clearInterval($),$=null)}function we(e){if(!U)return!1;try{const n=Y();return n!=null&&n.id?(n.sendMessage(e,()=>{try{const r=n==null?void 0:n.lastError;r&&/context invalidated/i.test(String(r.message||""))&&j()}catch{j()}}),!0):(j(),!1)}catch{return j(),!1}}function Te(){if(!U){L(!1);return}try{const e=Y();if(!(e!=null&&e.id)){L(!1);return}e.sendMessage({type:"GET_TRACKING_STATUS",url:window.location.href||""},n=>{try{if(e==null?void 0:e.lastError){L(!1);return}}catch{L(!1);return}L(!!(n!=null&&n.tracked),String((n==null?void 0:n.mode)||""))})}catch{L(!1)}}function v(e=!1,n=!1){if(!U)return;const{provider:r,videoId:t,video:i}=ue();if(!r)return;let o=-1;if(i&&(o=Math.max(0,Math.floor(Number(i.currentTime)||0))),r==="youtube"&&o<=0){const a=fe();a>=0&&(o=a)}if(r==="vimeo"&&o<=0){const a=me();a>=0&&(o=a)}if(o<0)return;const l=Date.now();!e&&o===he&&l-ge<4e3||(he=o,ge=l,we({type:"heartbeat",provider:r,videoId:t,cardId:se(window.location.href||""),flush:!!n,seconds:o,url:window.location.href||"",title:document.title||""}))}function A(e=!1,n=!1){if(!U)return;const r=window.location.href||"",{provider:t,videoId:i,video:o,mediaUrl:l,mediaTitle:a}=ue();if(!o&&!t)return;let s=-1;if(o&&(s=Math.max(0,Math.floor(Number(o.currentTime)||0))),t==="youtube"&&s<=0){const f=fe();f>=0&&(s=f)}if(t==="vimeo"&&s<=0){const f=me();f>=0&&(s=f)}if(s<0)return;const p=Date.now();!e&&s===be&&p-ye<4e3||(be=s,ye=p,we({type:"web_media_heartbeat",provider:t,videoId:i,cardId:se(r),trackEnabled:Ge(r),flush:!!n,seconds:s,url:r,mediaUrl:l,mediaTitle:a,title:document.title||""}))}$=window.setInterval(()=>{v(!1,!1),A(!1,!1)},1e3),xe=window.setInterval(()=>{const e=window.location.href||"";e!==Z&&(Z=e,Te())},750),window.addEventListener("pagehide",()=>{v(!0,!0),A(!0,!0)},{capture:!0}),window.addEventListener("beforeunload",()=>{v(!0,!0),A(!0,!0)},{capture:!0}),document.addEventListener("visibilitychange",()=>{document.visibilityState==="hidden"&&(v(!0,!0),A(!0,!0))}),document.addEventListener("timeupdate",()=>{v(!1,!1),A(!1,!1)},!0),document.addEventListener("play",()=>{v(!0,!1),A(!0,!1)},!0),document.addEventListener("pause",()=>{v(!0,!0),A(!0,!0)},!0),document.addEventListener("ended",()=>v(!0,!0),!0),window.setTimeout(()=>v(!0,!1),1200),window.setTimeout(Je,1200),window.setTimeout(Te,300),window.addEventListener("unload",()=>{try{clearInterval($),clearInterval(xe)}catch{}})})();
