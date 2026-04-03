(()=>{var se;const Q="browser-capture-v2";if(window.__incrementoContentScriptVersion===Q)return;window.__incrementoContentScriptVersion=Q;const j="incremento_browser_capture_settings",L=50,ue=0,me=100;function Z(e){const n=Number(e);return Number.isFinite(n)?Math.min(me,Math.max(ue,Number(n.toFixed(4)))):L}function fe(e){return Array.from(new Set(String(e||"").replaceAll(","," ").split(/\s+/).map(n=>n.trim()).filter(Boolean)))}function ee(e,n){const o=Array.isArray(n)?n.filter(Boolean):[],t=o[0]||"",a=r=>r===""?"":o.includes(r)?r:t;return{selectedTextField:a(String((e==null?void 0:e.selectedTextField)||"")),urlField:a(String((e==null?void 0:e.urlField)||"")),snapshotField:a(String((e==null?void 0:e.snapshotField)||""))}}function he(e,n){const o=Array.isArray(n==null?void 0:n.noteTypes)?n.noteTypes:[],t=Array.isArray(n==null?void 0:n.deckNames)?n.deckNames.filter(Boolean):[],a=String((e==null?void 0:e.noteTypeName)||""),r=o.find(v=>(v==null?void 0:v.name)===a)||o[0]||null,i=(r==null?void 0:r.name)||"",l=Array.isArray(r==null?void 0:r.fields)?r.fields:[],s=e!=null&&e.mappingsByNoteType&&typeof e.mappingsByNoteType=="object"?e.mappingsByNoteType:{},m=ee(s[i],l),f=String((e==null?void 0:e.deckName)||""),w=t.includes(f)?f:t[0]||"Default";return{noteTypeName:i,deckName:w,priority:Z(e==null?void 0:e.priority),tagsText:String((e==null?void 0:e.tagsText)||""),fieldMappings:m,mappingsByNoteType:s}}function D(e,n,o){return{...e,noteTypeName:n,fieldMappings:{...o},mappingsByNoteType:{...(e==null?void 0:e.mappingsByNoteType)||{},[n]:{...o}}}}function ge(e,n){var o,t,a;return{url:String((e==null?void 0:e.url)||"").trim(),title:String((e==null?void 0:e.title)||"").trim()||String((e==null?void 0:e.url)||"").trim()||"Untitled",selectedText:String((e==null?void 0:e.selectedText)||"").trim(),noteTypeName:String((n==null?void 0:n.noteTypeName)||"").trim(),deckName:String((n==null?void 0:n.deckName)||"").trim(),tags:fe(n==null?void 0:n.tagsText),priority:Z(n==null?void 0:n.priority),fieldMappings:{selectedTextField:String(((o=n==null?void 0:n.fieldMappings)==null?void 0:o.selectedTextField)||"").trim(),urlField:String(((t=n==null?void 0:n.fieldMappings)==null?void 0:t.urlField)||"").trim(),snapshotField:String(((a=n==null?void 0:n.fieldMappings)==null?void 0:a.snapshotField)||"").trim()},snapshots:Array.isArray(e==null?void 0:e.snapshots)?e.snapshots.map((r,i)=>({mimeType:"image/png",filename:String((r==null?void 0:r.filename)||`browser-capture-${i+1}.png`),base64:String((r==null?void 0:r.base64)||"").trim()})).filter(r=>r.base64):[]}}function E(e){const n=document.getElementById("incremento-video-time-toast");n&&n.remove();const o=document.createElement("div");o.id="incremento-video-time-toast",o.textContent=String(e||""),Object.assign(o.style,{position:"fixed",zIndex:2147483647,top:"10px",right:"10px",maxWidth:"320px",padding:"10px 14px",background:"rgba(0, 0, 0, 0.86)",color:"#fff",fontSize:"13px",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"6px",boxShadow:"0 2px 8px rgba(0, 0, 0, 0.4)",opacity:"0",transition:"opacity 0.2s ease"}),document.documentElement.appendChild(o),requestAnimationFrame(()=>{o.style.opacity="1"}),setTimeout(()=>{o.style.opacity="0",setTimeout(()=>o.remove(),220)},2400)}function be(){let e=document.getElementById("incremento-tracking-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-tracking-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483646,top:"52px",right:"10px",display:"none",alignItems:"center",gap:"8px",padding:"8px 12px",background:"linear-gradient(135deg, rgba(10, 34, 64, 0.94), rgba(17, 83, 126, 0.94))",color:"#fff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",letterSpacing:"0.08em",textTransform:"uppercase",borderRadius:"999px",boxShadow:"0 4px 14px rgba(0, 0, 0, 0.28)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"none"});const n=document.createElement("span");n.textContent="●",Object.assign(n.style,{color:"#53f2a5",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(83, 242, 165, 0.85)"}),e.appendChild(n);const o=document.createElement("span");o.textContent="⚠",Object.assign(o.style,{color:"#ffd166",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(255, 209, 102, 0.55)"}),e.appendChild(o);const t=document.createElement("span");return t.id="incremento-tracking-badge-label",t.textContent="Tracking",e.appendChild(t),document.documentElement.appendChild(e),e}function I(e,n=""){const o=be(),t=document.getElementById("incremento-tracking-badge-label");if(!(!o||!t)){if(!e){o.style.display="none";return}t.textContent=n==="web"?"Tracking Web Card":"Tracking",o.style.display="inline-flex"}}function O(){try{return(chrome==null?void 0:chrome.runtime)||null}catch{return null}}try{const e=O();(se=e==null?void 0:e.onMessage)==null||se.addListener((n,o,t)=>{var a;if(!n||!n.type)return!1;if(n.type==="SHOW_TOAST")return E(n.text||""),t==null||t({ok:!0}),!1;if(n.type==="TRIGGER_BROWSER_CAPTURE"){if(String(n.mode||"").trim().toLowerCase()==="snapshot")return K(),t==null||t({ok:!0}),!1;const i=String(((a=window.getSelection)==null?void 0:a.call(window).toString())||"").trim();return i?(W({mode:"selection",selectedText:i,snapshots:[]}).then(()=>t==null?void 0:t({ok:!0}),l=>{E((l==null?void 0:l.message)||"Failed to open browser capture."),C(),t==null||t({ok:!1,error:String((l==null?void 0:l.message)||"")})}),!0):(E("Select text on the page first."),t==null||t({ok:!1}),!1)}return!1})}catch{}let y=null,u=null;function V(e){return new Promise((n,o)=>{const t=O();if(!(t!=null&&t.sendMessage)){o(new Error("Incremento extension runtime is unavailable."));return}t.sendMessage(e,a=>{const r=chrome.runtime.lastError;if(r){o(new Error(r.message||"Extension request failed."));return}n(a||null)})})}async function xe(){const e=await V({type:"LOAD_BROWSER_CAPTURE_META"});if(!(e!=null&&e.ok))throw new Error(String((e==null?void 0:e.error)||"Failed to load browser capture metadata."));return e}async function ye(e){const n=await V({type:"SUBMIT_BROWSER_CAPTURE",payload:e});if(!(n!=null&&n.ok))throw new Error(String((n==null?void 0:n.error)||"Failed to submit browser capture."));return n}async function ve(){const e=await V({type:"CAPTURE_VISIBLE_TAB"});if(!(e!=null&&e.ok)||!(e!=null&&e.dataUrl))throw new Error(String((e==null?void 0:e.error)||"Failed to capture the current tab."));return e.dataUrl}async function Te(e){let n={};try{const o=await chrome.storage.local.get(j);n=(o==null?void 0:o[j])||{}}catch{n={}}return he(n,e)}async function we(e){try{await chrome.storage.local.set({[j]:{noteTypeName:String((e==null?void 0:e.noteTypeName)||""),deckName:String((e==null?void 0:e.deckName)||""),priority:Number((e==null?void 0:e.priority)??L),tagsText:String((e==null?void 0:e.tagsText)||""),mappingsByNoteType:(e==null?void 0:e.mappingsByNoteType)||{}}})}catch{}}function Ee(e){return!e||!(e instanceof Element)?!1:e.closest("input, textarea, select")?!0:!!e.closest('[contenteditable=""], [contenteditable="true"]')}function te(){return!!y}function Ce(e){return String((e==null?void 0:e.code)||"").toLowerCase()==="keyx"}function R(){if(y)return y;const e=document.createElement("div");e.id="incremento-browser-capture-root",e.style.all="initial";const n=e.attachShadow({mode:"open"});document.documentElement.appendChild(e);const o=document.createElement("style");o.textContent=`
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
    `,n.appendChild(o);const t=document.createElement("div");return t.className="shell",n.appendChild(t),y={host:e,shadow:n,shell:t},y}function C(){var e;(e=y==null?void 0:y.host)!=null&&e.isConnected&&y.host.remove(),y=null,u=null}function ne(){const e=R();e.shell.textContent=""}function Ne(e,n){const o=document.createElement("div");o.className="snapshots";for(const t of n){const a=document.createElement("div");a.className="snapshot-card";const r=document.createElement("img");r.src=t.dataUrl,r.alt=t.filename,a.appendChild(r);const i=document.createElement("div");i.className="snapshot-footer";const l=document.createElement("span");l.textContent=t.filename,i.appendChild(l);const s=document.createElement("button");s.type="button",s.textContent="Remove",s.addEventListener("click",()=>{u.snapshots=u.snapshots.filter(m=>m.id!==t.id),_()}),i.appendChild(s),a.appendChild(i),o.appendChild(a)}return o}async function _(){var de;const e=R(),{shell:n,shadow:o}=e,t=u;ne();const a=document.createElement("div");a.className="backdrop",a.addEventListener("click",()=>C()),n.appendChild(a);const r=document.createElement("section");r.className="panel",n.appendChild(r);const i=document.createElement("p");i.className="eyebrow",i.textContent=t.mode==="snapshot"?"Browser snapshot":"Browser selection",r.appendChild(i);const l=document.createElement("h2");l.textContent="Send capture to Anki",r.appendChild(l);const s=document.createElement("p");s.className="lead",s.textContent=t.mode==="snapshot"?`${t.snapshots.length} snapshot${t.snapshots.length===1?"":"s"} ready from ${t.context.url}`:`Selected text from ${t.context.url}`,r.appendChild(s);const m=document.createElement("form");m.noValidate=!0;const f=document.createElement("div");f.className="grid",m.appendChild(f);const w=(c,p,T=!1,h="")=>{const B=document.createElement("div");B.className=`field${T?" full":""}`;const pe=document.createElement("label");if(pe.textContent=c,B.appendChild(pe),B.appendChild(p),h){const J=document.createElement("p");J.className="field-note",J.textContent=h,B.appendChild(J)}return B},v=document.createElement("select");for(const c of t.meta.noteTypes){const p=document.createElement("option");p.value=c.name,p.textContent=c.name,v.appendChild(p)}v.value=t.form.noteTypeName,v.addEventListener("change",()=>{var T;const c=t.meta.noteTypes.find(h=>h.name===v.value),p=ee((T=t.form.mappingsByNoteType)==null?void 0:T[v.value],(c==null?void 0:c.fields)||[]);t.form=D(t.form,v.value,p),_()}),f.appendChild(w("Note type",v));const S=document.createElement("select");for(const c of t.meta.deckNames){const p=document.createElement("option");p.value=c,p.textContent=c,S.appendChild(p)}S.value=t.form.deckName,S.addEventListener("change",()=>{t.form.deckName=S.value}),f.appendChild(w("Deck",S));const d=document.createElement("input");d.type="text",d.value=t.form.tagsText,d.placeholder="tag-one tag-two",d.addEventListener("input",()=>{t.form.tagsText=d.value}),f.appendChild(w("Tags",d,!0));const g=document.createElement("div");g.style.display="grid",g.style.gridTemplateColumns="1fr auto",g.style.gap="10px",g.style.alignItems="center";const b=document.createElement("input");b.type="range",b.min="0",b.max="100",b.step="0.1",b.value=String(t.form.priority??L);const x=document.createElement("input");x.type="number",x.min="0",x.max="100",x.step="0.1",x.style.width="92px",x.value=String(t.form.priority??L);const A=c=>{const p=Number(c),T=Number.isFinite(p)?Math.min(100,Math.max(0,p)):L;t.form.priority=Number(T.toFixed(4)),b.value=String(t.form.priority),x.value=String(t.form.priority)};b.addEventListener("input",()=>A(b.value)),x.addEventListener("change",()=>A(x.value)),g.appendChild(b),g.appendChild(x),f.appendChild(w("Priority",g));const F=["",...((de=t.meta.noteTypes.find(c=>c.name===t.form.noteTypeName))==null?void 0:de.fields)||[]],G=(c,p)=>{const T=document.createElement("select");for(const h of F){const B=document.createElement("option");B.value=h,B.textContent=h||"Do not insert",T.appendChild(B)}return T.value=F.includes(c)?c:"",T.addEventListener("change",()=>{p(T.value)}),T},Pe=!!t.context.selectedText;f.appendChild(w("Selected text field",G(t.form.fieldMappings.selectedTextField,c=>{t.form=D(t.form,t.form.noteTypeName,{...t.form.fieldMappings,selectedTextField:c})}),!1,Pe?`${t.context.selectedText.length} chars ready for insertion.`:"No text added yet.")),f.appendChild(w("Source URL field",G(t.form.fieldMappings.urlField,c=>{t.form=D(t.form,t.form.noteTypeName,{...t.form.fieldMappings,urlField:c})}),!1,"The current page URL is always available.")),f.appendChild(w("Snapshot field",G(t.form.fieldMappings.snapshotField,c=>{t.form=D(t.form,t.form.noteTypeName,{...t.form.fieldMappings,snapshotField:c})}),!0,t.snapshots.length>0?`${t.snapshots.length} snapshot${t.snapshots.length===1?"":"s"} selected.`:"No snapshot images in this capture."));const $=document.createElement("textarea");if($.value=t.context.selectedText,$.placeholder=t.mode==="snapshot"?"Add text to store with these snapshots...":"Selected text will appear here. You can edit it before saving.",$.addEventListener("input",()=>{t.context.selectedText=$.value}),f.appendChild(w(t.mode==="snapshot"?"Text to add":"Selected text",$,!0,"This content is inserted into the selected text field if one is chosen.")),t.snapshots.length>0){const c=document.createElement("div");c.className="field full";const p=document.createElement("label");p.textContent="Snapshots",c.appendChild(p),c.appendChild(Ne(o,t.snapshots)),f.appendChild(c)}const X=document.createElement("p");X.className=`status${t.statusKind?` ${t.statusKind}`:""}`,X.textContent=t.statusText,m.appendChild(X);const U=document.createElement("div");if(U.className="actions",t.snapshots.length>0){const c=document.createElement("button");c.type="button",c.className="ghost-btn",c.textContent="Capture more",c.addEventListener("click",()=>K(t.snapshots)),U.appendChild(c)}const z=document.createElement("button");z.type="button",z.className="secondary-btn",z.textContent="Cancel",z.addEventListener("click",()=>C()),U.appendChild(z);const P=document.createElement("button");P.type="submit",P.className="primary-btn",P.textContent=t.submitting?"Saving...":"Create note",P.disabled=!!t.submitting,U.appendChild(P),m.appendChild(U),m.addEventListener("submit",async c=>{if(c.preventDefault(),t.submitting)return;const p=ge({...t.context,snapshots:t.snapshots.map(h=>({filename:h.filename,base64:h.base64}))},t.form),T=!!(p.selectedText&&p.fieldMappings.selectedTextField||p.fieldMappings.urlField||p.snapshots.length>0&&p.fieldMappings.snapshotField);if(!p.noteTypeName||!p.deckName){t.statusKind="error",t.statusText="Choose a note type and deck.",_();return}if(!T){t.statusKind="error",t.statusText="Map at least one available capture part to a note field.",_();return}t.submitting=!0,t.statusKind="",t.statusText="Creating note in Anki...",_();try{const h=await ye(p);await we(t.form),E(`Created ${h.noteTypeName} note in ${h.deckName}.`),C()}catch(h){t.submitting=!1,t.statusKind="error",t.statusText=(h==null?void 0:h.message)||"Failed to create note.",_()}}),r.appendChild(m)}function ke(e){return new Promise((n,o)=>{const t=new Image;t.onload=()=>n(t),t.onerror=()=>o(new Error("Failed to decode screenshot.")),t.src=e})}async function Be(e,n){const o=await ke(e),t=o.width/window.innerWidth,a=o.height/window.innerHeight,r=Math.max(0,Math.round(n.x*t)),i=Math.max(0,Math.round(n.y*a)),l=Math.max(1,Math.round(n.width*t)),s=Math.max(1,Math.round(n.height*a)),m=document.createElement("canvas");return m.width=l,m.height=s,m.getContext("2d").drawImage(o,r,i,l,s,0,0,l,s),m.toDataURL("image/png")}function Se(e){const n=String(e||""),o=n.indexOf(",");return o>=0?n.slice(o+1):n}function q(e){const n=Math.abs(e.width),o=Math.abs(e.height);return{x:e.width>=0?e.x:e.x-n,y:e.height>=0?e.y:e.y-o,width:n,height:o}}async function Ae(e,n=[]){var t;if(!e.length){E("Draw at least one region first.");return}const o=R();o.shell.style.display="none";try{const a=await ve(),r=[];for(let i=0;i<e.length;i+=1){const l=q(e[i]),s=await Be(a,l);r.push({id:`${Date.now()}-${i}-${Math.random().toString(16).slice(2,8)}`,filename:`browser-capture-${n.length+i+1}.png`,dataUrl:s,base64:Se(s)})}await W({mode:"snapshot",selectedText:((t=u==null?void 0:u.context)==null?void 0:t.selectedText)||"",snapshots:[...n,...r]})}catch(a){E((a==null?void 0:a.message)||"Failed to capture the current tab."),C()}finally{y!=null&&y.shell&&(y.shell.style.display="")}}function K(e=[]){var S;const n=R();ne(),u={mode:"snapshot",meta:(u==null?void 0:u.meta)||null,form:(u==null?void 0:u.form)||null,context:{url:window.location.href||"",title:document.title||"",selectedText:((S=u==null?void 0:u.context)==null?void 0:S.selectedText)||""},snapshots:[...e],statusKind:"",statusText:"",submitting:!1};const o=n.shell,t=document.createElement("div");t.className="backdrop",o.appendChild(t);const a=document.createElement("div");a.className="capture-shell",o.appendChild(a);const r=document.createElement("div");r.className="capture-toolbar",r.innerHTML=`
      <strong>Snapshot Mode</strong>
      <span>Draw one or more rectangles on the page. The capture is limited to the current viewport.</span>
      <span class="spacer"></span>
    `,o.appendChild(r);const i=[];let l=null,s=null;const m=()=>{r.innerHTML=`
        <strong>Snapshot Mode</strong>
        <span>Draw one or more rectangles on the page. The capture is limited to the current viewport.</span>
        <span class="spacer"></span>
      `;const d=document.createElement("span");d.textContent=`${i.length} region${i.length===1?"":"s"} ready`,r.appendChild(d);const g=document.createElement("button");g.type="button",g.className="toolbar-btn",g.textContent="Undo",g.disabled=i.length===0,g.addEventListener("click",()=>{var F;const k=i.pop();(F=k==null?void 0:k.el)==null||F.remove(),m()}),r.appendChild(g);const b=document.createElement("button");b.type="button",b.className="toolbar-btn",b.textContent="Clear",b.disabled=i.length===0,b.addEventListener("click",()=>{var k,F;for(;i.length>0;)(F=(k=i.pop())==null?void 0:k.el)==null||F.remove();m()}),r.appendChild(b);const x=document.createElement("button");x.type="button",x.className="toolbar-btn",x.textContent="Cancel",x.addEventListener("click",()=>C()),r.appendChild(x);const A=document.createElement("button");A.type="button",A.className="toolbar-btn primary",A.textContent="Continue",A.addEventListener("click",()=>{Ae(i.map(k=>k.region),e)}),r.appendChild(A)},f=(d,g)=>{s={x:d,y:g,width:0,height:0},l=document.createElement("div"),l.className="selection-rect",l.dataset.label=`Region ${i.length+1}`,a.appendChild(l)},w=()=>{if(!l||!s)return;const d=q(s);Object.assign(l.style,{left:`${d.x}px`,top:`${d.y}px`,width:`${d.width}px`,height:`${d.height}px`})};a.addEventListener("pointerdown",d=>{d.button!==0||d.target!==a||(d.preventDefault(),f(d.clientX,d.clientY),w())}),a.addEventListener("pointermove",d=>{s&&(d.preventDefault(),s.width=d.clientX-s.x,s.height=d.clientY-s.y,w())});const v=()=>{if(!l||!s)return;const d=q(s);d.width>=24&&d.height>=24?(l.dataset.label=`Region ${i.length+1}`,i.push({region:d,el:l})):l.remove(),l=null,s=null,m()};a.addEventListener("pointerup",v),a.addEventListener("pointercancel",v),m()}async function W({mode:e,selectedText:n="",snapshots:o=[]}){const t=(u==null?void 0:u.meta)||await xe();if(!Array.isArray(t==null?void 0:t.noteTypes)||t.noteTypes.length===0)throw new Error("No note types are available in Anki.");if(!Array.isArray(t==null?void 0:t.deckNames)||t.deckNames.length===0)throw new Error("No decks are available in Anki.");const a=(u==null?void 0:u.form)||await Te(t);u={mode:e,meta:t,form:a,context:{url:window.location.href||"",title:document.title||"",selectedText:String(n||"").trim()},snapshots:Array.isArray(o)?o:[],statusKind:"",statusText:"",submitting:!1},await _()}globalThis.__incrementoTriggerBrowserCapture=e=>{var t;if(String(e||"").trim().toLowerCase()==="snapshot")return K(),{ok:!0};const o=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();return o?(W({mode:"selection",selectedText:o,snapshots:[]}).catch(a=>{E((a==null?void 0:a.message)||"Failed to open browser capture."),C()}),{ok:!0}):(E("Select text on the page first."),{ok:!1,error:"Select text on the page first."})},document.addEventListener("keydown",e=>{var o;if(!e.altKey||!Ce(e)||te()||Ee(e.target))return;if(e.metaKey){e.preventDefault(),e.stopPropagation(),K();return}if(e.ctrlKey||e.shiftKey)return;const n=String(((o=window.getSelection)==null?void 0:o.call(window).toString())||"").trim();n&&(e.preventDefault(),e.stopPropagation(),W({mode:"selection",selectedText:n,snapshots:[]}).catch(t=>{E((t==null?void 0:t.message)||"Failed to open browser capture."),C()}))},!0),document.addEventListener("keydown",e=>{e.key==="Escape"&&te()&&(e.preventDefault(),e.stopPropagation(),C())},!0);function Fe(e){try{const n=new URL(e),o=n.searchParams.get("v");if(o)return o;const t=n.pathname.split("/").filter(Boolean);if(n.hostname==="youtu.be"&&t[0])return t[0];if((t[0]==="shorts"||t[0]==="live"||t[0]==="embed")&&t[1])return t[1]}catch{}return""}function _e(e){const n=String(e||"").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);return n?n[1]:""}function Ie(){const e=window.location.href||"",n=window.location.hostname||"";return n.includes("youtube.com")||n==="youtu.be"?{provider:"youtube",videoId:Fe(e)}:n.includes("vimeo.com")?{provider:"vimeo",videoId:_e(e)}:{provider:"",videoId:""}}function Le(e){try{const o=new URL(e).searchParams.get("inc_card_id")||"",t=Number(o);if(Number.isFinite(t)&&t>0)return Math.floor(t)}catch{}return 0}function Me(){const e=Array.from(document.querySelectorAll("video"));return e.length===0?null:(e.sort((n,o)=>{const t=(n.videoWidth||0)*(n.videoHeight||0);return(o.videoWidth||0)*(o.videoHeight||0)-t}),e[0])}function oe(e){const n=String(e||"").trim();if(!n)return-1;const o=n.split(":").map(t=>t.trim());return o.every(t=>/^\d+$/.test(t))?o.length===2?Number(o[0])*60+Number(o[1]):o.length===3?Number(o[0])*3600+Number(o[1])*60+Number(o[2]):-1:-1}function $e(){const e=Array.from(document.querySelectorAll('[data-progress-bar-timecode="true"], [class*="Timecode_module_timecode__"]'));for(const n of e){const o=String((n==null?void 0:n.textContent)||"").trim(),t=oe(o);if(t>=0)return t}return-1}function Ue(){const e=Array.from(document.querySelectorAll(".ytp-time-current, [class*='ytp-time-current']"));for(const n of e){const o=String((n==null?void 0:n.textContent)||"").trim(),t=oe(o);if(t>=0)return t}return-1}let re=-1,ae=0,H=!0,M=null,ie=null,le=window.location.href||"";function Y(){H=!1,M!==null&&(clearInterval(M),M=null)}function ze(e){if(!H)return!1;try{const n=O();return n!=null&&n.id?(n.sendMessage(e,()=>{try{const o=n==null?void 0:n.lastError;o&&/context invalidated/i.test(String(o.message||""))&&Y()}catch{Y()}}),!0):(Y(),!1)}catch{return Y(),!1}}function ce(){if(!H){I(!1);return}try{const e=O();if(!(e!=null&&e.id)){I(!1);return}e.sendMessage({type:"GET_TRACKING_STATUS",url:window.location.href||""},n=>{try{if(e==null?void 0:e.lastError){I(!1);return}}catch{I(!1);return}I(!!(n!=null&&n.tracked),String((n==null?void 0:n.mode)||""))})}catch{I(!1)}}function N(e=!1,n=!1){if(!H)return;const{provider:o,videoId:t}=Ie();if(!o)return;const a=Me();let r=-1;if(a&&(r=Math.max(0,Math.floor(Number(a.currentTime)||0))),o==="youtube"&&r<=0){const l=Ue();l>=0&&(r=l)}if(o==="vimeo"&&r<=0){const l=$e();l>=0&&(r=l)}if(r<0)return;const i=Date.now();!e&&r===re&&i-ae<4e3||(re=r,ae=i,ze({type:"heartbeat",provider:o,videoId:t,cardId:Le(window.location.href||""),flush:!!n,seconds:r,url:window.location.href||"",title:document.title||""}))}M=window.setInterval(()=>N(!1,!1),1e3),ie=window.setInterval(()=>{const e=window.location.href||"";e!==le&&(le=e,ce())},750),window.addEventListener("pagehide",()=>N(!0,!0),{capture:!0}),window.addEventListener("beforeunload",()=>N(!0,!0),{capture:!0}),document.addEventListener("visibilitychange",()=>{document.visibilityState==="hidden"&&N(!0,!0)}),document.addEventListener("timeupdate",()=>N(!1,!1),!0),document.addEventListener("play",()=>N(!0,!1),!0),document.addEventListener("pause",()=>N(!0,!0),!0),document.addEventListener("ended",()=>N(!0,!0),!0),window.setTimeout(()=>N(!0,!1),1200),window.setTimeout(ce,300),window.addEventListener("unload",()=>{try{clearInterval(M),clearInterval(ie)}catch{}})})();
