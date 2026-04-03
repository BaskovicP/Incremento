(()=>{var de;const Q="browser-capture-v2";if(window.__incrementoContentScriptVersion===Q)return;window.__incrementoContentScriptVersion=Q;const j="incremento_browser_capture_settings",_=50,me=0,fe=100;function Z(e){const n=Number(e);return Number.isFinite(n)?Math.min(fe,Math.max(me,Number(n.toFixed(4)))):_}function he(e){return Array.from(new Set(String(e||"").replaceAll(","," ").split(/\s+/).map(n=>n.trim()).filter(Boolean)))}function ee(e,n){const o=Array.isArray(n)?n.filter(Boolean):[],t=o[0]||"",a=r=>r===""?"":o.includes(r)?r:t;return{selectedTextField:a(String((e==null?void 0:e.selectedTextField)||"")),urlField:a(String((e==null?void 0:e.urlField)||"")),snapshotField:a(String((e==null?void 0:e.snapshotField)||""))}}function ge(e,n){const o=Array.isArray(n==null?void 0:n.noteTypes)?n.noteTypes:[],t=Array.isArray(n==null?void 0:n.deckNames)?n.deckNames.filter(Boolean):[],a=String((e==null?void 0:e.noteTypeName)||""),r=o.find(y=>(y==null?void 0:y.name)===a)||o[0]||null,l=(r==null?void 0:r.name)||"",c=Array.isArray(r==null?void 0:r.fields)?r.fields:[],u=e!=null&&e.mappingsByNoteType&&typeof e.mappingsByNoteType=="object"?e.mappingsByNoteType:{},m=ee(u[l],c),h=String((e==null?void 0:e.deckName)||""),w=t.includes(h)?h:t[0]||"Default";return{noteTypeName:l,deckName:w,priority:Z(e==null?void 0:e.priority),tagsText:String((e==null?void 0:e.tagsText)||""),fieldMappings:m,mappingsByNoteType:u}}function D(e,n,o){return{...e,noteTypeName:n,fieldMappings:{...o},mappingsByNoteType:{...(e==null?void 0:e.mappingsByNoteType)||{},[n]:{...o}}}}function be(e,n){var o,t,a;return{url:String((e==null?void 0:e.url)||"").trim(),title:String((e==null?void 0:e.title)||"").trim()||String((e==null?void 0:e.url)||"").trim()||"Untitled",selectedText:String((e==null?void 0:e.selectedText)||"").trim(),noteTypeName:String((n==null?void 0:n.noteTypeName)||"").trim(),deckName:String((n==null?void 0:n.deckName)||"").trim(),tags:he(n==null?void 0:n.tagsText),priority:Z(n==null?void 0:n.priority),fieldMappings:{selectedTextField:String(((o=n==null?void 0:n.fieldMappings)==null?void 0:o.selectedTextField)||"").trim(),urlField:String(((t=n==null?void 0:n.fieldMappings)==null?void 0:t.urlField)||"").trim(),snapshotField:String(((a=n==null?void 0:n.fieldMappings)==null?void 0:a.snapshotField)||"").trim()},snapshots:Array.isArray(e==null?void 0:e.snapshots)?e.snapshots.map((r,l)=>({mimeType:"image/png",filename:String((r==null?void 0:r.filename)||`browser-capture-${l+1}.png`),base64:String((r==null?void 0:r.base64)||"").trim()})).filter(r=>r.base64):[]}}function T(e){const n=document.getElementById("incremento-video-time-toast");n&&n.remove();const o=document.createElement("div");o.id="incremento-video-time-toast",o.textContent=String(e||""),Object.assign(o.style,{position:"fixed",zIndex:2147483647,top:"10px",right:"10px",maxWidth:"320px",padding:"10px 14px",background:"rgba(0, 0, 0, 0.86)",color:"#fff",fontSize:"13px",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"6px",boxShadow:"0 2px 8px rgba(0, 0, 0, 0.4)",opacity:"0",transition:"opacity 0.2s ease"}),document.documentElement.appendChild(o),requestAnimationFrame(()=>{o.style.opacity="1"}),setTimeout(()=>{o.style.opacity="0",setTimeout(()=>o.remove(),220)},2400)}function xe(){let e=document.getElementById("incremento-tracking-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-tracking-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483646,top:"52px",right:"10px",display:"none",alignItems:"center",gap:"8px",padding:"8px 12px",background:"linear-gradient(135deg, rgba(10, 34, 64, 0.94), rgba(17, 83, 126, 0.94))",color:"#fff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",letterSpacing:"0.08em",textTransform:"uppercase",borderRadius:"999px",boxShadow:"0 4px 14px rgba(0, 0, 0, 0.28)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"none"});const n=document.createElement("span");n.textContent="●",Object.assign(n.style,{color:"#53f2a5",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(83, 242, 165, 0.85)"}),e.appendChild(n);const o=document.createElement("span");o.textContent="⚠",Object.assign(o.style,{color:"#ffd166",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(255, 209, 102, 0.55)"}),e.appendChild(o);const t=document.createElement("span");return t.id="incremento-tracking-badge-label",t.textContent="Tracking",e.appendChild(t),document.documentElement.appendChild(e),e}function A(e,n=""){const o=xe(),t=document.getElementById("incremento-tracking-badge-label");if(!(!o||!t)){if(!e){o.style.display="none";return}t.textContent=n==="web"?"Tracking Web Card":"Tracking",o.style.display="inline-flex"}}function O(){try{return(chrome==null?void 0:chrome.runtime)||null}catch{return null}}try{const e=O();(de=e==null?void 0:e.onMessage)==null||de.addListener((n,o,t)=>{var a;if(!n||!n.type)return!1;if(n.type==="SHOW_TOAST")return T(n.text||""),t==null||t({ok:!0}),!1;if(n.type==="TRIGGER_BROWSER_CAPTURE"){if(String(n.mode||"").trim().toLowerCase()==="snapshot")return K(),t==null||t({ok:!0}),!1;const l=String(((a=window.getSelection)==null?void 0:a.call(window).toString())||"").trim();return l?(W({mode:"selection",selectedText:l,snapshots:[]}).then(()=>t==null?void 0:t({ok:!0}),c=>{T((c==null?void 0:c.message)||"Failed to open browser capture."),k(),t==null||t({ok:!1,error:String((c==null?void 0:c.message)||"")})}),!0):(T("Select text on the page first."),t==null||t({ok:!1}),!1)}return!1})}catch{}let x=null,p=null;function V(e){return new Promise((n,o)=>{const t=O();if(!(t!=null&&t.sendMessage)){o(new Error("Incremento extension runtime is unavailable."));return}t.sendMessage(e,a=>{const r=chrome.runtime.lastError;if(r){o(new Error(r.message||"Extension request failed."));return}n(a||null)})})}async function ye(){const e=await V({type:"LOAD_BROWSER_CAPTURE_META"});if(!(e!=null&&e.ok))throw new Error(String((e==null?void 0:e.error)||"Failed to load browser capture metadata."));return e}async function ve(e){const n=await V({type:"SUBMIT_BROWSER_CAPTURE",payload:e});if(!(n!=null&&n.ok))throw new Error(String((n==null?void 0:n.error)||"Failed to submit browser capture."));return n}async function we(){const e=await V({type:"CAPTURE_VISIBLE_TAB"});if(!(e!=null&&e.ok)||!(e!=null&&e.dataUrl))throw new Error(String((e==null?void 0:e.error)||"Failed to capture the current tab."));return e.dataUrl}async function Te(e){let n={};try{const o=await chrome.storage.local.get(j);n=(o==null?void 0:o[j])||{}}catch{n={}}return ge(n,e)}async function Ee(e){try{await chrome.storage.local.set({[j]:{noteTypeName:String((e==null?void 0:e.noteTypeName)||""),deckName:String((e==null?void 0:e.deckName)||""),priority:Number((e==null?void 0:e.priority)??_),tagsText:String((e==null?void 0:e.tagsText)||""),mappingsByNoteType:(e==null?void 0:e.mappingsByNoteType)||{}}})}catch{}}function Ce(e){return!e||!(e instanceof Element)?!1:e.closest("input, textarea, select")?!0:!!e.closest('[contenteditable=""], [contenteditable="true"]')}function te(){return!!x}function Ne(e){return String((e==null?void 0:e.code)||"").toLowerCase()==="keyx"}function R(){if(x)return x;const e=document.createElement("div");e.id="incremento-browser-capture-root",e.style.all="initial";const n=e.attachShadow({mode:"open"});document.documentElement.appendChild(e);const o=document.createElement("style");o.textContent=`
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
    `,n.appendChild(o);const t=document.createElement("div");return t.className="shell",n.appendChild(t),x={host:e,shadow:n,shell:t},x}function k(){var e;(e=x==null?void 0:x.host)!=null&&e.isConnected&&x.host.remove(),x=null,p=null}function ne(){const e=R();e.shell.textContent=""}function ke(e,n){const o=document.createElement("div");o.className="snapshots";for(const t of n){const a=document.createElement("div");a.className="snapshot-card";const r=document.createElement("img");r.src=t.dataUrl,r.alt=t.filename,a.appendChild(r);const l=document.createElement("div");l.className="snapshot-footer";const c=document.createElement("span");c.textContent=t.filename,l.appendChild(c);const u=document.createElement("button");u.type="button",u.textContent="Remove",u.addEventListener("click",()=>{p.snapshots=p.snapshots.filter(m=>m.id!==t.id),F()}),l.appendChild(u),a.appendChild(l),o.appendChild(a)}return o}async function F(){var ue;const e=R(),{shell:n,shadow:o}=e,t=p;ne();const a=document.createElement("div");a.className="backdrop",a.addEventListener("click",()=>k()),n.appendChild(a);const r=document.createElement("section");r.className="panel",n.appendChild(r);const l=document.createElement("p");l.className="eyebrow",l.textContent=t.mode==="snapshot"?"Browser snapshot":"Browser selection",r.appendChild(l);const c=document.createElement("h2");c.textContent="Send capture to Anki",r.appendChild(c);const u=document.createElement("p");u.className="lead",u.textContent=t.mode==="snapshot"?`${t.snapshots.length} snapshot${t.snapshots.length===1?"":"s"} ready from ${t.context.url}`:`Selected text from ${t.context.url}`,r.appendChild(u);const m=document.createElement("form");m.noValidate=!0;const h=document.createElement("div");h.className="grid",m.appendChild(h);const w=(i,d,v=!1,b="")=>{const N=document.createElement("div");N.className=`field${v?" full":""}`;const pe=document.createElement("label");if(pe.textContent=i,N.appendChild(pe),N.appendChild(d),b){const J=document.createElement("p");J.className="field-note",J.textContent=b,N.appendChild(J)}return N},y=document.createElement("select");for(const i of t.meta.noteTypes){const d=document.createElement("option");d.value=i.name,d.textContent=i.name,y.appendChild(d)}y.value=t.form.noteTypeName,y.addEventListener("change",()=>{var v;const i=t.meta.noteTypes.find(b=>b.name===y.value),d=ee((v=t.form.mappingsByNoteType)==null?void 0:v[y.value],(i==null?void 0:i.fields)||[]);t.form=D(t.form,y.value,d),F()}),h.appendChild(w("Note type",y));const B=document.createElement("select");for(const i of t.meta.deckNames){const d=document.createElement("option");d.value=i,d.textContent=i,B.appendChild(d)}B.value=t.form.deckName,B.addEventListener("change",()=>{t.form.deckName=B.value}),h.appendChild(w("Deck",B));const C=document.createElement("input");C.type="text",C.value=t.form.tagsText,C.placeholder="tag-one tag-two",C.addEventListener("input",()=>{t.form.tagsText=C.value}),h.appendChild(w("Tags",C,!0));const s=document.createElement("div");s.style.display="grid",s.style.gridTemplateColumns="1fr auto",s.style.gap="10px",s.style.alignItems="center";const g=document.createElement("input");g.type="range",g.min="0",g.max="100",g.step="0.1",g.value=String(t.form.priority??_);const f=document.createElement("input");f.type="number",f.min="0",f.max="100",f.step="0.1",f.style.width="92px",f.value=String(t.form.priority??_);const S=i=>{const d=Number(i),v=Number.isFinite(d)?Math.min(100,Math.max(0,d)):_;t.form.priority=Number(v.toFixed(4)),g.value=String(t.form.priority),f.value=String(t.form.priority)};g.addEventListener("input",()=>S(g.value)),f.addEventListener("change",()=>S(f.value)),s.appendChild(g),s.appendChild(f),h.appendChild(w("Priority",s));const L=["",...((ue=t.meta.noteTypes.find(i=>i.name===t.form.noteTypeName))==null?void 0:ue.fields)||[]],G=(i,d)=>{const v=document.createElement("select");for(const b of L){const N=document.createElement("option");N.value=b,N.textContent=b||"Do not insert",v.appendChild(N)}return v.value=L.includes(i)?i:"",v.addEventListener("change",()=>{d(v.value)}),v},De=!!t.context.selectedText;h.appendChild(w("Selected text field",G(t.form.fieldMappings.selectedTextField,i=>{t.form=D(t.form,t.form.noteTypeName,{...t.form.fieldMappings,selectedTextField:i})}),!1,De?`${t.context.selectedText.length} chars ready for insertion.`:"No text added yet.")),h.appendChild(w("Source URL field",G(t.form.fieldMappings.urlField,i=>{t.form=D(t.form,t.form.noteTypeName,{...t.form.fieldMappings,urlField:i})}),!1,"The current page URL is always available.")),h.appendChild(w("Snapshot field",G(t.form.fieldMappings.snapshotField,i=>{t.form=D(t.form,t.form.noteTypeName,{...t.form.fieldMappings,snapshotField:i})}),!0,t.snapshots.length>0?`${t.snapshots.length} snapshot${t.snapshots.length===1?"":"s"} selected.`:"No snapshot images in this capture."));const $=document.createElement("textarea");if($.value=t.context.selectedText,$.placeholder=t.mode==="snapshot"?"Add text to store with these snapshots...":"Selected text will appear here. You can edit it before saving.",$.addEventListener("input",()=>{t.context.selectedText=$.value}),h.appendChild(w(t.mode==="snapshot"?"Text to add":"Selected text",$,!0,"This content is inserted into the selected text field if one is chosen.")),t.snapshots.length>0){const i=document.createElement("div");i.className="field full";const d=document.createElement("label");d.textContent="Snapshots",i.appendChild(d),i.appendChild(ke(o,t.snapshots)),h.appendChild(i)}const X=document.createElement("p");X.className=`status${t.statusKind?` ${t.statusKind}`:""}`,X.textContent=t.statusText,m.appendChild(X);const P=document.createElement("div");if(P.className="actions",t.snapshots.length>0){const i=document.createElement("button");i.type="button",i.className="ghost-btn",i.textContent="Capture more",i.addEventListener("click",()=>K(t.snapshots)),P.appendChild(i)}const U=document.createElement("button");U.type="button",U.className="secondary-btn",U.textContent="Cancel",U.addEventListener("click",()=>k()),P.appendChild(U);const z=document.createElement("button");z.type="submit",z.className="primary-btn",z.textContent=t.submitting?"Saving...":"Create note",z.disabled=!!t.submitting,P.appendChild(z),m.appendChild(P),m.addEventListener("submit",async i=>{if(i.preventDefault(),t.submitting)return;const d=be({...t.context,snapshots:t.snapshots.map(b=>({filename:b.filename,base64:b.base64}))},t.form),v=!!(d.selectedText&&d.fieldMappings.selectedTextField||d.fieldMappings.urlField||d.snapshots.length>0&&d.fieldMappings.snapshotField);if(!d.noteTypeName||!d.deckName){t.statusKind="error",t.statusText="Choose a note type and deck.",F();return}if(!v){t.statusKind="error",t.statusText="Map at least one available capture part to a note field.",F();return}t.submitting=!0,t.statusKind="",t.statusText="Creating note in Anki...",F();try{const b=await ve(d);await Ee(t.form),T(`Created ${b.noteTypeName} note in ${b.deckName}.`),k()}catch(b){t.submitting=!1,t.statusKind="error",t.statusText=(b==null?void 0:b.message)||"Failed to create note.",F()}}),r.appendChild(m)}function Be(e){return new Promise((n,o)=>{const t=new Image;t.onload=()=>n(t),t.onerror=()=>o(new Error("Failed to decode screenshot.")),t.src=e})}async function Se(e,n){const o=await Be(e),t=o.width/window.innerWidth,a=o.height/window.innerHeight,r=Math.max(0,Math.round(n.x*t)),l=Math.max(0,Math.round(n.y*a)),c=Math.max(1,Math.round(n.width*t)),u=Math.max(1,Math.round(n.height*a)),m=document.createElement("canvas");return m.width=c,m.height=u,m.getContext("2d").drawImage(o,r,l,c,u,0,0,c,u),m.toDataURL("image/png")}function Fe(e){const n=String(e||""),o=n.indexOf(",");return o>=0?n.slice(o+1):n}function q(e){const n=Math.abs(e.width),o=Math.abs(e.height);return{x:e.width>=0?e.x:e.x-n,y:e.height>=0?e.y:e.y-o,width:n,height:o}}function oe(e=2){return new Promise(n=>{const o=Math.max(1,Number(e)||1);let t=0;const a=()=>{if(t+=1,t>=o){n();return}requestAnimationFrame(a)};requestAnimationFrame(a)})}async function Ae(e,n=[]){const o=R();o.shell.style.display="none";try{await oe(2);const t=await we(),a=q(e),r=await Se(t,a);return{id:`${Date.now()}-${n.length}-${Math.random().toString(16).slice(2,8)}`,filename:`browser-capture-${n.length+1}.png`,dataUrl:r,base64:Fe(r)}}catch(t){throw new Error((t==null?void 0:t.message)||"Failed to capture the current tab.")}finally{x!=null&&x.shell&&(x.shell.style.display="",await oe(1))}}function K(e=[]){var C;const n=R();ne(),p={mode:"snapshot",meta:(p==null?void 0:p.meta)||null,form:(p==null?void 0:p.form)||null,context:{url:window.location.href||"",title:document.title||"",selectedText:((C=p==null?void 0:p.context)==null?void 0:C.selectedText)||""},snapshots:[...e],statusKind:"",statusText:"",submitting:!1};const o=n.shell,t=document.createElement("div");t.className="backdrop",o.appendChild(t);const a=document.createElement("div");a.className="capture-shell",o.appendChild(a);const r=document.createElement("div");r.className="capture-toolbar",r.innerHTML=`
      <strong>Snapshot Mode</strong>
      <span>Draw one or more rectangles on the page. The capture is limited to the current viewport.</span>
      <span class="spacer"></span>
    `,o.appendChild(r);const l=[...e];let c=null,u=null,m=!1;const h=()=>{r.innerHTML=`
        <strong>Snapshot Mode</strong>
        <span>Draw a rectangle to capture it immediately, then scroll and capture another area if needed.</span>
        <span class="spacer"></span>
      `;const s=document.createElement("span");s.textContent=m?"Capturing...":`${l.length} snapshot${l.length===1?"":"s"} ready`,r.appendChild(s);const g=document.createElement("button");g.type="button",g.className="toolbar-btn",g.textContent="Undo",g.disabled=m||l.length===0,g.addEventListener("click",()=>{l.pop(),h()}),r.appendChild(g);const f=document.createElement("button");f.type="button",f.className="toolbar-btn",f.textContent="Clear",f.disabled=m||l.length===0,f.addEventListener("click",()=>{l.splice(0,l.length),h()}),r.appendChild(f);const S=document.createElement("button");S.type="button",S.className="toolbar-btn",S.textContent="Cancel",S.addEventListener("click",()=>k()),r.appendChild(S);const I=document.createElement("button");I.type="button",I.className="toolbar-btn primary",I.textContent="Continue",I.addEventListener("click",()=>{var L;if(!m){if(!l.length){T("Draw at least one region first.");return}W({mode:"snapshot",selectedText:((L=p==null?void 0:p.context)==null?void 0:L.selectedText)||"",snapshots:[...l]})}}),r.appendChild(I)},w=(s,g)=>{u={x:s,y:g,width:0,height:0},c=document.createElement("div"),c.className="selection-rect",c.dataset.label=`Capture ${l.length+1}`,a.appendChild(c)},y=()=>{if(!c||!u)return;const s=q(u);Object.assign(c.style,{left:`${s.x}px`,top:`${s.y}px`,width:`${s.width}px`,height:`${s.height}px`})};a.addEventListener("pointerdown",s=>{m||s.button!==0||s.target!==a||(s.preventDefault(),w(s.clientX,s.clientY),y())}),a.addEventListener("pointermove",s=>{u&&(s.preventDefault(),u.width=s.clientX-u.x,u.height=s.clientY-u.y,y())});const B=async()=>{if(!c||!u)return;const s=q(u),g=c;if(s.width>=24&&s.height>=24){m=!0,h();try{const f=await Ae(s,l);l.push(f)}catch(f){T((f==null?void 0:f.message)||"Failed to capture the current tab.")}}else g.remove();g.remove(),c=null,u=null,m=!1,h()};a.addEventListener("pointerup",()=>{B()}),a.addEventListener("pointercancel",()=>{B()}),h()}async function W({mode:e,selectedText:n="",snapshots:o=[]}){const t=(p==null?void 0:p.meta)||await ye();if(!Array.isArray(t==null?void 0:t.noteTypes)||t.noteTypes.length===0)throw new Error("No note types are available in Anki.");if(!Array.isArray(t==null?void 0:t.deckNames)||t.deckNames.length===0)throw new Error("No decks are available in Anki.");const a=(p==null?void 0:p.form)||await Te(t);p={mode:e,meta:t,form:a,context:{url:window.location.href||"",title:document.title||"",selectedText:String(n||"").trim()},snapshots:Array.isArray(o)?o:[],statusKind:"",statusText:"",submitting:!1},await F()}globalThis.__incrementoTriggerBrowserCapture=e=>{var t;if(String(e||"").trim().toLowerCase()==="snapshot")return K(),{ok:!0};const o=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();return o?(W({mode:"selection",selectedText:o,snapshots:[]}).catch(a=>{T((a==null?void 0:a.message)||"Failed to open browser capture."),k()}),{ok:!0}):(T("Select text on the page first."),{ok:!1,error:"Select text on the page first."})},document.addEventListener("keydown",e=>{var o;if(!e.altKey||!Ne(e)||te()||Ce(e.target))return;if(e.metaKey){e.preventDefault(),e.stopPropagation(),K();return}if(e.ctrlKey||e.shiftKey)return;const n=String(((o=window.getSelection)==null?void 0:o.call(window).toString())||"").trim();n&&(e.preventDefault(),e.stopPropagation(),W({mode:"selection",selectedText:n,snapshots:[]}).catch(t=>{T((t==null?void 0:t.message)||"Failed to open browser capture."),k()}))},!0),document.addEventListener("keydown",e=>{e.key==="Escape"&&te()&&(e.preventDefault(),e.stopPropagation(),k())},!0);function Ie(e){try{const n=new URL(e),o=n.searchParams.get("v");if(o)return o;const t=n.pathname.split("/").filter(Boolean);if(n.hostname==="youtu.be"&&t[0])return t[0];if((t[0]==="shorts"||t[0]==="live"||t[0]==="embed")&&t[1])return t[1]}catch{}return""}function _e(e){const n=String(e||"").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);return n?n[1]:""}function Me(){const e=window.location.href||"",n=window.location.hostname||"";return n.includes("youtube.com")||n==="youtu.be"?{provider:"youtube",videoId:Ie(e)}:n.includes("vimeo.com")?{provider:"vimeo",videoId:_e(e)}:{provider:"",videoId:""}}function Le(e){try{const o=new URL(e).searchParams.get("inc_card_id")||"",t=Number(o);if(Number.isFinite(t)&&t>0)return Math.floor(t)}catch{}return 0}function $e(){const e=Array.from(document.querySelectorAll("video"));return e.length===0?null:(e.sort((n,o)=>{const t=(n.videoWidth||0)*(n.videoHeight||0);return(o.videoWidth||0)*(o.videoHeight||0)-t}),e[0])}function re(e){const n=String(e||"").trim();if(!n)return-1;const o=n.split(":").map(t=>t.trim());return o.every(t=>/^\d+$/.test(t))?o.length===2?Number(o[0])*60+Number(o[1]):o.length===3?Number(o[0])*3600+Number(o[1])*60+Number(o[2]):-1:-1}function Pe(){const e=Array.from(document.querySelectorAll('[data-progress-bar-timecode="true"], [class*="Timecode_module_timecode__"]'));for(const n of e){const o=String((n==null?void 0:n.textContent)||"").trim(),t=re(o);if(t>=0)return t}return-1}function Ue(){const e=Array.from(document.querySelectorAll(".ytp-time-current, [class*='ytp-time-current']"));for(const n of e){const o=String((n==null?void 0:n.textContent)||"").trim(),t=re(o);if(t>=0)return t}return-1}let ae=-1,ie=0,H=!0,M=null,le=null,ce=window.location.href||"";function Y(){H=!1,M!==null&&(clearInterval(M),M=null)}function ze(e){if(!H)return!1;try{const n=O();return n!=null&&n.id?(n.sendMessage(e,()=>{try{const o=n==null?void 0:n.lastError;o&&/context invalidated/i.test(String(o.message||""))&&Y()}catch{Y()}}),!0):(Y(),!1)}catch{return Y(),!1}}function se(){if(!H){A(!1);return}try{const e=O();if(!(e!=null&&e.id)){A(!1);return}e.sendMessage({type:"GET_TRACKING_STATUS",url:window.location.href||""},n=>{try{if(e==null?void 0:e.lastError){A(!1);return}}catch{A(!1);return}A(!!(n!=null&&n.tracked),String((n==null?void 0:n.mode)||""))})}catch{A(!1)}}function E(e=!1,n=!1){if(!H)return;const{provider:o,videoId:t}=Me();if(!o)return;const a=$e();let r=-1;if(a&&(r=Math.max(0,Math.floor(Number(a.currentTime)||0))),o==="youtube"&&r<=0){const c=Ue();c>=0&&(r=c)}if(o==="vimeo"&&r<=0){const c=Pe();c>=0&&(r=c)}if(r<0)return;const l=Date.now();!e&&r===ae&&l-ie<4e3||(ae=r,ie=l,ze({type:"heartbeat",provider:o,videoId:t,cardId:Le(window.location.href||""),flush:!!n,seconds:r,url:window.location.href||"",title:document.title||""}))}M=window.setInterval(()=>E(!1,!1),1e3),le=window.setInterval(()=>{const e=window.location.href||"";e!==ce&&(ce=e,se())},750),window.addEventListener("pagehide",()=>E(!0,!0),{capture:!0}),window.addEventListener("beforeunload",()=>E(!0,!0),{capture:!0}),document.addEventListener("visibilitychange",()=>{document.visibilityState==="hidden"&&E(!0,!0)}),document.addEventListener("timeupdate",()=>E(!1,!1),!0),document.addEventListener("play",()=>E(!0,!1),!0),document.addEventListener("pause",()=>E(!0,!0),!0),document.addEventListener("ended",()=>E(!0,!0),!0),window.setTimeout(()=>E(!0,!1),1200),window.setTimeout(se,300),window.addEventListener("unload",()=>{try{clearInterval(M),clearInterval(le)}catch{}})})();
