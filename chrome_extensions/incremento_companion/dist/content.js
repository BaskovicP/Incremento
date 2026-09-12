import{L as re,D as kt,o as ge,T as Ct,U as Ve,V as _t,W as oe,I as je,K as Ge,N as Nt,O as qe,Q as At,X as Bt,n as Lt,g as Mt,a as It}from"./assets/extension-shared.js";(()=>{var Ke,Re,He;const G="browser-capture-v8",Qe="incremento-browser-capture-root",ae=window.__incrementoContentScriptState&&typeof window.__incrementoContentScriptState=="object"?window.__incrementoContentScriptState:{};if(ae.version===G&&ae.ready)return;window.__incrementoContentScriptState={...ae,version:G,ready:!1},window.__incrementoContentScriptVersion=G;const ie="incremento_browser_capture_settings",W=50,Je=0,Ze=100;let D=kt,M=null;globalThis.__incrementoLastSelectedText=String(globalThis.__incrementoLastSelectedText||"").trim();function P(){var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();return e?(globalThis.__incrementoLastSelectedText=e,e):String(globalThis.__incrementoLastSelectedText||"").trim()}function be(e){const t=Number(e);return Number.isFinite(t)?Math.min(Ze,Math.max(Je,Number(t.toFixed(4)))):W}function et(e){return Array.from(new Set(String(e||"").replaceAll(","," ").split(/\s+/).map(t=>t.trim()).filter(Boolean)))}function ye(e,t){const r=Array.isArray(t)?t.filter(Boolean):[],n=r[0]||"",o=a=>a===""?"":r.includes(a)?a:n;return{titleField:o(String((e==null?void 0:e.titleField)||"")),selectedTextField:o(String((e==null?void 0:e.selectedTextField)||"")),urlField:o(String((e==null?void 0:e.urlField)||"")),snapshotField:o(String((e==null?void 0:e.snapshotField)||""))}}function tt(e,t){const r=Array.isArray(t==null?void 0:t.noteTypes)?t.noteTypes:[],n=Array.isArray(t==null?void 0:t.deckNames)?t.deckNames.filter(Boolean):[],o=String((e==null?void 0:e.noteTypeName)||""),a=r.find(E=>(E==null?void 0:E.name)===o)||r[0]||null,i=(a==null?void 0:a.name)||"",l=Array.isArray(a==null?void 0:a.fields)?a.fields:[],c=e!=null&&e.mappingsByNoteType&&typeof e.mappingsByNoteType=="object"?e.mappingsByNoteType:{},s=ye(c[i],l),m=String((e==null?void 0:e.deckName)||""),y=n.includes(m)?m:n[0]||"Default";return{noteTypeName:i,deckName:y,priority:be(e==null?void 0:e.priority),tagsText:String((e==null?void 0:e.tagsText)||""),fieldMappings:s,mappingsByNoteType:c}}function z(e,t,r){return{...e,noteTypeName:t,fieldMappings:{...r},mappingsByNoteType:{...(e==null?void 0:e.mappingsByNoteType)||{},[t]:{...r}}}}function xe(e,t){var r,n,o,a;return{url:String((e==null?void 0:e.url)||"").trim(),title:String((e==null?void 0:e.title)||"").trim()||String((e==null?void 0:e.url)||"").trim()||"Untitled",selectedText:String((e==null?void 0:e.selectedText)||"").trim(),noteTypeName:String((t==null?void 0:t.noteTypeName)||"").trim(),deckName:String((t==null?void 0:t.deckName)||"").trim(),tags:et(t==null?void 0:t.tagsText),priority:be(t==null?void 0:t.priority),fieldMappings:{titleField:String(((r=t==null?void 0:t.fieldMappings)==null?void 0:r.titleField)||"").trim(),selectedTextField:String(((n=t==null?void 0:t.fieldMappings)==null?void 0:n.selectedTextField)||"").trim(),urlField:String(((o=t==null?void 0:t.fieldMappings)==null?void 0:o.urlField)||"").trim(),snapshotField:String(((a=t==null?void 0:t.fieldMappings)==null?void 0:a.snapshotField)||"").trim()},snapshots:Array.isArray(e==null?void 0:e.snapshots)?e.snapshots.map((i,l)=>({mimeType:"image/png",filename:String((i==null?void 0:i.filename)||`browser-capture-${l+1}.png`),base64:String((i==null?void 0:i.base64)||"").trim()})).filter(i=>i.base64):[]}}function S(e){const t=document.getElementById("incremento-video-time-toast");t&&t.remove();const r=document.createElement("div");r.id="incremento-video-time-toast",r.textContent=String(e||""),Object.assign(r.style,{position:"fixed",zIndex:2147483647,top:"10px",right:"10px",maxWidth:"320px",padding:"10px 14px",background:"rgba(0, 0, 0, 0.86)",color:"#fff",fontSize:"13px",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"6px",boxShadow:"0 2px 8px rgba(0, 0, 0, 0.4)",opacity:"0",transition:"opacity 0.2s ease"}),document.documentElement.appendChild(r),requestAnimationFrame(()=>{r.style.opacity="1"}),setTimeout(()=>{r.style.opacity="0",setTimeout(()=>r.remove(),220)},2400)}async function nt(){try{const e=await chrome.storage.local.get(re);D=ge(e==null?void 0:e[re])}catch{D=ge(null)}}function Ee(e){var o,a;const t=e instanceof Element?e:(e==null?void 0:e.parentElement)||null,r=(o=t==null?void 0:t.closest)==null?void 0:o.call(t,"a[href]");if(!r)return null;const n=String(r.href||((a=r.getAttribute)==null?void 0:a.call(r,"href"))||"").trim();return Ge(n)?r:null}function we(e){var r;if(!e)return null;const t=String(e.href||((r=e.getAttribute)==null?void 0:r.call(e,"href"))||"").trim();return Ge(t)?{url:t,title:Nt(e.textContent||"",t)}:null}function rt(){let e=document.getElementById("incremento-tracking-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-tracking-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483646,top:"52px",right:"10px",display:"none",alignItems:"center",gap:"8px",padding:"8px 12px",background:"linear-gradient(135deg, rgba(10, 34, 64, 0.94), rgba(17, 83, 126, 0.94))",color:"#fff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",letterSpacing:"0.08em",textTransform:"uppercase",borderRadius:"999px",boxShadow:"0 4px 14px rgba(0, 0, 0, 0.28)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"none"});const t=document.createElement("span");t.textContent="●",Object.assign(t.style,{color:"#53f2a5",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(83, 242, 165, 0.85)"}),e.appendChild(t);const r=document.createElement("span");r.textContent="⚠",Object.assign(r.style,{color:"#ffd166",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(255, 209, 102, 0.55)"}),e.appendChild(r);const n=document.createElement("span");return n.id="incremento-tracking-badge-label",n.textContent="Tracking",e.appendChild(n),document.documentElement.appendChild(e),e}function O(e,t=""){const r=rt(),n=document.getElementById("incremento-tracking-badge-label");if(!(!r||!n)){if(!e){r.style.display="none";return}n.textContent=t==="web"?"Tracking Web Card":"Tracking",r.style.display="inline-flex"}}function Te(e){const t=Math.max(0,Math.floor(Number(e)||0)),r=Math.floor(t/3600),n=Math.floor(t%3600/60),o=t%60;return r>0?`${r}:${String(n).padStart(2,"0")}:${String(o).padStart(2,"0")}`:`${n}:${String(o).padStart(2,"0")}`}function ot(){let e=document.getElementById("incremento-browser-media-ref-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-browser-media-ref-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483645,top:"96px",right:"10px",display:"none",alignItems:"center",gap:"8px",maxWidth:"320px",padding:"9px 12px",background:"linear-gradient(135deg, rgba(28, 32, 48, 0.96), rgba(34, 62, 96, 0.96))",color:"#eef5ff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"14px",boxShadow:"0 5px 18px rgba(0, 0, 0, 0.30)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"auto"});const t=document.createElement("span");t.textContent="▶",Object.assign(t.style,{color:"#8fd3ff",fontSize:"11px",lineHeight:"1"}),e.appendChild(t);const r=document.createElement("span");r.id="incremento-browser-media-ref-badge-label",r.textContent="",Object.assign(r.style,{flex:"1 1 auto",minWidth:"0"}),e.appendChild(r);const n=document.createElement("button");return n.type="button",n.textContent="×",n.setAttribute("aria-label","Dismiss saved browser time badge"),Object.assign(n.style,{appearance:"none",border:"0",background:"transparent",color:"#a9bfdc",cursor:"pointer",fontSize:"16px",fontWeight:"700",lineHeight:"1",padding:"0 0 0 4px",margin:"0",pointerEvents:"auto"}),n.addEventListener("click",o=>{o.preventDefault(),o.stopPropagation(),ee=!0,e.style.display="none"}),e.appendChild(n),document.documentElement.appendChild(e),e}function K(e){const t=ot(),r=document.getElementById("incremento-browser-media-ref-badge-label");if(!t||!r)return;if(!!!(e!=null&&e.hasReference)){t.style.display="none";return}if(ee)return;const o=String((e==null?void 0:e.timeText)||Te(e==null?void 0:e.seconds));r.textContent=o?`Last saved ${o}`:"Last saved",t.style.display="inline-flex"}function R(){try{return(chrome==null?void 0:chrome.runtime)||null}catch{return null}}nt();try{(Re=(Ke=chrome==null?void 0:chrome.storage)==null?void 0:Ke.onChanged)==null||Re.addListener((e,t)=>{var r;t!=="local"||!e||!Object.prototype.hasOwnProperty.call(e,re)||(D=ge((r=e[re])==null?void 0:r.newValue))})}catch{}try{const e=R();(He=e==null?void 0:e.onMessage)==null||He.addListener((t,r,n)=>{var o;if(!t||!t.type)return!1;if(t.type==="SHOW_TOAST")return S(t.text||""),n==null||n({ok:!0}),!1;if(t.type==="TRIGGER_BROWSER_CAPTURE"){if(String(t.mode||"").trim().toLowerCase()==="snapshot")return Q(),n==null||n({ok:!0}),!1;const i=P();return i?(J({mode:"selection",selectedText:i,snapshots:[]}).then(()=>n==null?void 0:n({ok:!0}),l=>{S((l==null?void 0:l.message)||"Failed to open browser capture."),C(),n==null||n({ok:!1,error:String((l==null?void 0:l.message)||"")})}),!0):(S("Select text on the page first."),n==null||n({ok:!1}),!1)}if(t.type==="GET_PAGE_CONTEXT"){const a={html:((o=document.documentElement)==null?void 0:o.outerHTML)||"",selectionText:P(),title:document.title||"",url:window.location.href||""},i=Ct(a);return i.ok?(n==null||n({ok:!0,...a}),!1):(n==null||n(i),!1)}if(t.type==="GET_CONTEXT_LINK_INFO")return n==null||n({ok:!0,url:String((M==null?void 0:M.url)||""),title:String((M==null?void 0:M.title)||"")}),!1;if(t.type==="GET_CURRENT_MEDIA_CONTEXT")return n==null||n(St()),!1;if(t.type==="APPLY_MEDIA_RESUME"){const a=de(t.seconds);return n==null||n({ok:a}),!1}return t.type==="UPDATE_BROWSER_MEDIA_REF_BADGE"&&(ee=!1,K(t.reference||null),n==null||n({ok:!0})),!1})}catch{}let g=null,p=null;function H(e){return new Promise((t,r)=>{const n=R();if(!(n!=null&&n.sendMessage)){r(new Error("Incremento extension runtime is unavailable."));return}n.sendMessage(e,o=>{const a=chrome.runtime.lastError;if(a){r(new Error(a.message||"Extension request failed."));return}t(o||null)})})}async function ve(){const e=await H({type:"LOAD_BROWSER_CAPTURE_META"});if(!(e!=null&&e.ok))throw new Error(String((e==null?void 0:e.error)||"Failed to load browser capture metadata."));return e}async function Se(e){const t=await H({type:"SUBMIT_BROWSER_CAPTURE",payload:e});if(!(t!=null&&t.ok))throw new Error(String((t==null?void 0:t.error)||"Failed to submit browser capture."));return t}async function at(){const e=await H({type:"CAPTURE_VISIBLE_TAB"});if(!(e!=null&&e.ok)||!(e!=null&&e.dataUrl))throw new Error(String((e==null?void 0:e.error)||"Failed to capture the current tab."));return e.dataUrl}async function ke(e){let t={};try{const r=await chrome.storage.local.get(ie);t=(r==null?void 0:r[ie])||{}}catch{t={}}return tt(t,e)}async function Ce(e){try{await chrome.storage.local.set({[ie]:{noteTypeName:String((e==null?void 0:e.noteTypeName)||""),deckName:String((e==null?void 0:e.deckName)||""),priority:Number((e==null?void 0:e.priority)??W),tagsText:String((e==null?void 0:e.tagsText)||""),mappingsByNoteType:(e==null?void 0:e.mappingsByNoteType)||{}}})}catch{}}async function _e(e="",t=[]){const r=(p==null?void 0:p.meta)||await ve();if(!Array.isArray(r==null?void 0:r.noteTypes)||r.noteTypes.length===0)throw new Error("No note types are available in Anki.");if(!Array.isArray(r==null?void 0:r.deckNames)||r.deckNames.length===0)throw new Error("No decks are available in Anki.");const n=(p==null?void 0:p.form)||await ke(r);return p={mode:"snapshot",meta:r,form:n,context:{url:window.location.href||"",title:document.title||"",selectedText:Ve("snapshot",e,P())},snapshots:Array.isArray(t)?t:[],statusKind:"",statusText:"",submitting:!1},p}async function it(e="",t=[]){const r=await _e(e,t),n=xe({...r.context,snapshots:r.snapshots.map(i=>({filename:i.filename,base64:i.base64}))},r.form),o=je(n);if(!o.ok)throw new Error(`${o.error} Open Continue once to choose the destination fields for snapshot capture.`);const a=await Se(n);return await Ce(r.form),a}function Ne(e){const t=e instanceof Element?e:(e==null?void 0:e.parentElement)||null;return t?t.closest("input, textarea, select")?!0:!!t.closest('[contenteditable=""], [contenteditable="true"]'):!1}function le(){return!!g}function lt(e){return String((e==null?void 0:e.code)||"").toLowerCase()==="keyx"}function ce(e){var n;const t=g==null?void 0:g.shell,r=e==null?void 0:e.target;if(!(!t||!(r instanceof Node)||!t.contains(r))){if(e.type==="keydown"&&((n=g==null?void 0:g.handleTagAutocompleteKeyDown)!=null&&n.call(g,e))){e.stopPropagation();return}if(e.type==="keydown"&&e.key==="Escape"){e.preventDefault(),e.stopPropagation(),C();return}e.stopPropagation()}}function q(){if(g)return g;const e=document.createElement("div");e.id=Qe,e.style.all="initial";const t=e.attachShadow({mode:"open"});document.documentElement.appendChild(e),t.addEventListener("keydown",ce,!0),t.addEventListener("keypress",ce,!0),t.addEventListener("keyup",ce,!0);const r=document.createElement("style");r.textContent=`
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
      .tag-autocomplete {
        position: relative;
      }
      .tag-suggestions {
        position: absolute;
        z-index: 10;
        top: calc(100% + 4px);
        right: 0;
        left: 0;
        max-height: 210px;
        overflow-y: auto;
        border: 1px solid rgba(82, 68, 45, 0.18);
        border-radius: 13px;
        background: #fffdf8;
        box-shadow: 0 14px 30px rgba(66, 48, 22, 0.2);
        padding: 4px;
      }
      .tag-suggestions[hidden] { display: none; }
      .tag-suggestions button {
        display: block;
        width: 100%;
        border: 0;
        border-radius: 9px;
        background: transparent;
        padding: 9px 10px;
        color: inherit;
        font: inherit;
        text-align: left;
        cursor: pointer;
      }
      .tag-suggestions button:hover,
      .tag-suggestions button.is-active {
        background: rgba(184, 106, 23, 0.13);
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
    `,t.appendChild(r);const n=document.createElement("div");return n.className="shell",t.appendChild(n),g={host:e,shadow:t,shell:n},g}function C(){var e;(e=g==null?void 0:g.host)!=null&&e.isConnected&&g.host.remove(),g=null,p=null}function Ae(){const e=q();e.handleTagAutocompleteKeyDown=null,e.shell.textContent=""}function ct(e,t,r){const n=document.createElement("div");n.className="tag-autocomplete";const o=document.createElement("input");o.id="incremento-browser-capture-tags",o.type="text",o.value=String(e||""),o.placeholder="tag-one tag-two",o.autocomplete="off",o.spellcheck=!1,o.setAttribute("role","combobox"),o.setAttribute("aria-autocomplete","list");const a=document.createElement("div");a.id="incremento-browser-capture-tag-suggestions",a.className="tag-suggestions",a.setAttribute("role","listbox"),a.hidden=!0,o.setAttribute("aria-controls",a.id),o.setAttribute("aria-expanded","false");const i=Lt(t);let l=!1,c=0,s=[];const m=()=>{var b;Array.from(a.children).forEach((h,d)=>{h.classList.toggle("is-active",d===c),h.setAttribute("aria-selected",d===c?"true":"false")}),!a.hidden&&s.length>0?(o.setAttribute("aria-activedescendant",`${a.id}-${c}`),(b=a.children[c])==null||b.scrollIntoView({block:"nearest"})):o.removeAttribute("aria-activedescendant")},y=()=>{const b=o.selectionStart??o.value.length;if(s=Mt(i,o.value,b),c=s.length>0?Math.min(c,s.length-1):0,a.textContent="",a.hidden=!l||s.length===0,o.setAttribute("aria-expanded",a.hidden?"false":"true"),a.hidden){m();return}s.forEach((h,d)=>{const f=document.createElement("button");f.id=`${a.id}-${d}`,f.type="button",f.setAttribute("role","option"),f.setAttribute("aria-selected",d===c?"true":"false"),f.className=d===c?"is-active":"",f.textContent=h,f.addEventListener("mouseenter",()=>{c=d,m()}),f.addEventListener("mousedown",w=>{w.preventDefault(),E(h)}),a.appendChild(f)}),m()},E=b=>{const h=It(o.value,b,o.selectionStart??o.value.length,o.selectionEnd??o.value.length);o.value=h.value,r(h.value),l=!1,c=0,o.focus(),o.setSelectionRange(h.cursor,h.cursor),y()},_=b=>{if(b.target!==o)return!1;if(b.key==="Escape"&&l)return b.preventDefault(),l=!1,y(),!0;if(!s.length)return!1;if(b.key==="ArrowDown"||b.key==="ArrowUp"){b.preventDefault();const h=b.key==="ArrowDown"?1:-1;if(!l)l=!0,c=h>0?0:s.length-1;else return c=(c+h+s.length)%s.length,m(),!0;return y(),!0}return l&&(b.key==="Enter"||b.key==="Tab")?(b.preventDefault(),E(s[c]),!0):!1};return o.addEventListener("input",()=>{r(o.value),c=0,l=!0,y()}),o.addEventListener("focus",()=>{l=!0,y()}),o.addEventListener("click",()=>{c=0,l=!0,y()}),o.addEventListener("select",y),o.addEventListener("blur",()=>{l=!1,y()}),n.appendChild(o),n.appendChild(a),{element:n,handleKeyDown:_}}function st(e,t){const r=document.createElement("div");r.className="snapshots";for(const n of t){const o=document.createElement("div");o.className="snapshot-card";const a=document.createElement("img");a.src=n.dataUrl,a.alt=n.filename,o.appendChild(a);const i=document.createElement("div");i.className="snapshot-footer";const l=document.createElement("span");l.textContent=n.filename,i.appendChild(l);const c=document.createElement("button");c.type="button",c.textContent="Remove",c.addEventListener("click",()=>{p.snapshots=p.snapshots.filter(s=>s.id!==n.id),$()}),i.appendChild(c),o.appendChild(i),r.appendChild(o)}return r}async function $(){var Ye;const e=q(),{shell:t,shadow:r}=e,n=p;Ae();const o=document.createElement("div");o.className="backdrop",o.addEventListener("click",()=>C()),t.appendChild(o);const a=document.createElement("section");a.className="panel",t.appendChild(a);const i=document.createElement("p");i.className="eyebrow",i.textContent=n.mode==="snapshot"?"Browser snapshot":"Browser selection",a.appendChild(i);const l=document.createElement("h2");l.textContent="Send capture to Anki",a.appendChild(l);const c=document.createElement("p");c.className="lead",c.textContent=n.mode==="snapshot"?`${n.snapshots.length} snapshot${n.snapshots.length===1?"":"s"} ready from ${n.context.url}`:`Selected text from ${n.context.url}`,a.appendChild(c);const s=document.createElement("form");s.noValidate=!0;const m=document.createElement("div");m.className="grid",s.appendChild(m);const y=(u,x,v=!1,T="")=>{const L=document.createElement("div");L.className=`field${v?" full":""}`;const Xe=document.createElement("label");if(Xe.textContent=u,L.appendChild(Xe),L.appendChild(x),T){const he=document.createElement("p");he.className="field-note",he.textContent=T,L.appendChild(he)}return L},E=document.createElement("select");for(const u of n.meta.noteTypes){const x=document.createElement("option");x.value=u.name,x.textContent=u.name,E.appendChild(x)}E.value=n.form.noteTypeName,E.addEventListener("change",()=>{var v;const u=n.meta.noteTypes.find(T=>T.name===E.value),x=ye((v=n.form.mappingsByNoteType)==null?void 0:v[E.value],(u==null?void 0:u.fields)||[]);n.form=z(n.form,E.value,x),$()}),m.appendChild(y("Note type",E));const _=document.createElement("select");for(const u of n.meta.deckNames){const x=document.createElement("option");x.value=u,x.textContent=u,_.appendChild(x)}_.value=n.form.deckName,_.addEventListener("change",()=>{n.form.deckName=_.value}),m.appendChild(y("Deck",_));const b=ct(n.form.tagsText,n.meta.tagNames,u=>{n.form.tagsText=u});g.handleTagAutocompleteKeyDown=b.handleKeyDown,m.appendChild(y("Tags",b.element,!0,"Start typing to choose an existing Anki tag, or enter a new one."));const h=document.createElement("div");h.style.display="grid",h.style.gridTemplateColumns="1fr auto",h.style.gap="10px",h.style.alignItems="center";const d=document.createElement("input");d.type="range",d.min="0",d.max="100",d.step="0.1",d.value=String(n.form.priority??W);const f=document.createElement("input");f.type="number",f.min="0",f.max="100",f.step="0.1",f.style.width="92px",f.value=String(n.form.priority??W);const w=u=>{const x=Number(u),v=Number.isFinite(x)?Math.min(100,Math.max(0,x)):W;n.form.priority=Number(v.toFixed(4)),d.value=String(n.form.priority),f.value=String(n.form.priority)};d.addEventListener("input",()=>w(d.value)),f.addEventListener("change",()=>w(f.value)),h.appendChild(d),h.appendChild(f),m.appendChild(y("Priority",h));const B=["",...((Ye=n.meta.noteTypes.find(u=>u.name===n.form.noteTypeName))==null?void 0:Ye.fields)||[]],N=(u,x)=>{const v=document.createElement("select");for(const T of B){const L=document.createElement("option");L.value=T,L.textContent=T||"Do not insert",v.appendChild(L)}return v.value=B.includes(u)?u:"",v.addEventListener("change",()=>{x(v.value)}),v},F=!!n.context.selectedText;m.appendChild(y("Page title field",N(n.form.fieldMappings.titleField,u=>{n.form=z(n.form,n.form.noteTypeName,{...n.form.fieldMappings,titleField:u})}),!1,"The current page title is always available. First-field mappings get a unique snapshot suffix.")),m.appendChild(y("Selected text field",N(n.form.fieldMappings.selectedTextField,u=>{n.form=z(n.form,n.form.noteTypeName,{...n.form.fieldMappings,selectedTextField:u})}),!1,F?`${n.context.selectedText.length} chars ready for insertion.`:"No text added yet.")),m.appendChild(y("Source URL field",N(n.form.fieldMappings.urlField,u=>{n.form=z(n.form,n.form.noteTypeName,{...n.form.fieldMappings,urlField:u})}),!1,"The current page URL is always available.")),m.appendChild(y("Snapshot field",N(n.form.fieldMappings.snapshotField,u=>{n.form=z(n.form,n.form.noteTypeName,{...n.form.fieldMappings,snapshotField:u})}),!0,n.snapshots.length>0?`${n.snapshots.length} snapshot${n.snapshots.length===1?"":"s"} selected.`:"No snapshot images in this capture."));const k=document.createElement("textarea");if(k.value=n.context.selectedText,k.placeholder=n.mode==="snapshot"?"Add text to store with these snapshots...":"Selected text will appear here. You can edit it before saving.",k.addEventListener("input",()=>{n.context.selectedText=k.value}),m.appendChild(y(n.mode==="snapshot"?"Text to add":"Selected text",k,!0,"This content is inserted into the selected text field if one is chosen.")),n.snapshots.length>0){const u=document.createElement("div");u.className="field full";const x=document.createElement("label");x.textContent="Snapshots",u.appendChild(x),u.appendChild(st(r,n.snapshots)),m.appendChild(u)}const fe=document.createElement("p");fe.className=`status${n.statusKind?` ${n.statusKind}`:""}`,fe.textContent=n.statusText,s.appendChild(fe);const X=document.createElement("div");if(X.className="actions",n.snapshots.length>0){const u=document.createElement("button");u.type="button",u.className="ghost-btn",u.textContent="Capture more",u.addEventListener("click",()=>Q(n.snapshots)),X.appendChild(u)}const V=document.createElement("button");V.type="button",V.className="secondary-btn",V.textContent="Cancel",V.addEventListener("click",()=>C()),X.appendChild(V);const j=document.createElement("button");j.type="submit",j.className="primary-btn",j.textContent=n.submitting?"Saving...":"Create note",j.disabled=!!n.submitting,X.appendChild(j),s.appendChild(X),s.addEventListener("submit",async u=>{if(u.preventDefault(),n.submitting)return;const x=xe({...n.context,snapshots:n.snapshots.map(T=>({filename:T.filename,base64:T.base64}))},n.form),v=je(x);if(!v.ok){n.statusKind="error",n.statusText=v.error,$();return}n.submitting=!0,n.statusKind="",n.statusText="Creating note in Anki...",$();try{const T=await Se(x);await Ce(n.form),S(`Created ${T.noteTypeName} note in ${T.deckName}.`),C()}catch(T){n.submitting=!1,n.statusKind="error",n.statusText=(T==null?void 0:T.message)||"Failed to create note.",$()}}),a.appendChild(s)}function dt(e){return new Promise((t,r)=>{const n=new Image;n.onload=()=>t(n),n.onerror=()=>r(new Error("Failed to decode screenshot.")),n.src=e})}async function ut(e,t){const r=await dt(e),n=r.width/window.innerWidth,o=r.height/window.innerHeight,a=Math.max(0,Math.round(t.x*n)),i=Math.max(0,Math.round(t.y*o)),l=Math.max(1,Math.round(t.width*n)),c=Math.max(1,Math.round(t.height*o)),s=document.createElement("canvas");return s.width=l,s.height=c,s.getContext("2d").drawImage(r,a,i,l,c,0,0,l,c),s.toDataURL("image/png")}function pt(e){const t=String(e||""),r=t.indexOf(",");return r>=0?t.slice(r+1):t}function se(e){const t=Math.abs(e.width),r=Math.abs(e.height);return{x:e.width>=0?e.x:e.x-t,y:e.height>=0?e.y:e.y-r,width:t,height:r}}function Be(e=2){return new Promise(t=>{const r=Math.max(1,Number(e)||1);let n=0;const o=()=>{if(n+=1,n>=r){t();return}requestAnimationFrame(o)};requestAnimationFrame(o)})}function mt(e,t){if(!(e instanceof Element))return!1;const r=window.getComputedStyle(e),n=t==="x"?r.overflowX:r.overflowY;return/(auto|scroll|overlay)/.test(String(n||""))?t==="x"?e.scrollWidth>e.clientWidth:e.scrollHeight>e.clientHeight:!1}function Le(e,t){let r=e instanceof Element?e:null;for(;r;){if(mt(r,t))return r;r=r.parentElement}const n=document.scrollingElement;return n instanceof Element?n:document.documentElement}function ft(e,t){var s;if(!e)return;const r=((s=t==null?void 0:t.style)==null?void 0:s.pointerEvents)||"";t!=null&&t.style&&(t.style.pointerEvents="none");let n=null;try{n=document.elementFromPoint(e.clientX,e.clientY)}finally{t!=null&&t.style&&(t.style.pointerEvents=r)}const o=Number(e.deltaX)||0,a=Number(e.deltaY)||0,i=o?Le(n,"x"):null,l=a?Le(n,"y"):null,c=document.scrollingElement instanceof Element?document.scrollingElement:document.documentElement;o&&(i||c).scrollBy({left:o,top:0,behavior:"auto"}),a&&(l||c).scrollBy({left:0,top:a,behavior:"auto"})}async function ht(e,t=[]){if(t.length>=oe)throw new Error(`Too many snapshots. Maximum is ${oe}.`);const r=q();r.shell.style.display="none";try{await Be(2);const n=await at(),o=qe(n,{maxBytes:At});if(!o.ok)throw new Error(o.error);const a=se(e),i=await ut(n,a),l=qe(i,{maxBytes:Bt});if(!l.ok)throw new Error(l.error);return{id:`${Date.now()}-${t.length}-${Math.random().toString(16).slice(2,8)}`,filename:`browser-capture-${t.length+1}.png`,dataUrl:i,base64:pt(i)}}catch(n){throw new Error((n==null?void 0:n.message)||"Failed to capture the current tab.")}finally{g!=null&&g.shell&&(g.shell.style.display="",await Be(1))}}function Q(e=[]){var h;const t=q();Ae();const r=e.length>0&&((h=p==null?void 0:p.context)==null?void 0:h.selectedText)||"";p={mode:"snapshot",meta:(p==null?void 0:p.meta)||null,form:(p==null?void 0:p.form)||null,context:{url:window.location.href||"",title:document.title||"",selectedText:r},snapshots:[...e],statusKind:"",statusText:"",submitting:!1};const n=t.shell,o=document.createElement("div");o.className="capture-shell",n.appendChild(o);const a=document.createElement("div");a.className="capture-toolbar",a.innerHTML=`
      <strong>Snapshot Mode</strong>
      <span>Draw one or more rectangles on the page. The capture is limited to the current viewport.</span>
      <span class="spacer"></span>
    `,n.appendChild(a);const i=[...e];let l=null,c=null,s=!1;const m=()=>{a.innerHTML=`
        <strong>Snapshot Mode</strong>
        <span>Draw a rectangle to capture it immediately, then scroll and capture another area if needed.</span>
        <span class="spacer"></span>
      `;const d=document.createElement("span");d.textContent=s?"Capturing...":`${i.length} snapshot${i.length===1?"":"s"} ready`,a.appendChild(d);const f=document.createElement("button");f.type="button",f.className="toolbar-btn",f.textContent="Undo",f.disabled=s||i.length===0,f.addEventListener("click",()=>{i.pop(),m()}),a.appendChild(f);const w=document.createElement("button");w.type="button",w.className="toolbar-btn",w.textContent="Clear",w.disabled=s||i.length===0,w.addEventListener("click",()=>{i.splice(0,i.length),m()}),a.appendChild(w);const U=document.createElement("button");U.type="button",U.className="toolbar-btn",U.textContent="Cancel",U.addEventListener("click",()=>C()),a.appendChild(U);const B=document.createElement("button");B.type="button",B.className="toolbar-btn",B.textContent="Extract now",B.disabled=s||i.length===0,B.addEventListener("click",async()=>{var F;if(!s){if(!i.length){S("Draw at least one region first.");return}s=!0,m();try{const k=await it(((F=p==null?void 0:p.context)==null?void 0:F.selectedText)||"",[...i]);S(`Created ${k.noteTypeName} note in ${k.deckName}.`),C()}catch(k){s=!1,m(),S((k==null?void 0:k.message)||"Failed to create note.")}}}),a.appendChild(B);const N=document.createElement("button");N.type="button",N.className="toolbar-btn primary",N.textContent="Continue",N.addEventListener("click",()=>{var F;if(!s){if(!i.length){S("Draw at least one region first.");return}J({mode:"snapshot",selectedText:((F=p==null?void 0:p.context)==null?void 0:F.selectedText)||"",snapshots:[...i]})}}),a.appendChild(N)},y=(d,f)=>{if(i.length>=oe){S(`Too many snapshots. Maximum is ${oe}.`);return}c={x:d,y:f,width:0,height:0},l=document.createElement("div"),l.className="selection-rect",l.dataset.label=`Capture ${i.length+1}`,o.appendChild(l)},E=()=>{if(!l||!c)return;const d=se(c);Object.assign(l.style,{left:`${d.x}px`,top:`${d.y}px`,width:`${d.width}px`,height:`${d.height}px`})};o.addEventListener("pointerdown",d=>{s||d.button!==0||d.target!==o||(d.preventDefault(),y(d.clientX,d.clientY),E())}),o.addEventListener("pointermove",d=>{c&&(d.preventDefault(),c.width=d.clientX-c.x,c.height=d.clientY-c.y,E())});const _=d=>{c||s||(d.preventDefault(),ft(d,t.host))};o.addEventListener("wheel",_,{passive:!1}),a.addEventListener("wheel",_,{passive:!1});const b=async()=>{if(!l||!c)return;const d=se(c),f=l;if(d.width>=24&&d.height>=24){s=!0,m();try{const w=await ht(d,i);i.push(w)}catch(w){S((w==null?void 0:w.message)||"Failed to capture the current tab.")}}else f.remove();f.remove(),l=null,c=null,s=!1,m()};o.addEventListener("pointerup",()=>{b()}),o.addEventListener("pointercancel",()=>{b()}),m()}async function J({mode:e,selectedText:t="",snapshots:r=[]}){if(e==="snapshot")await _e(t,r);else{const n=(p==null?void 0:p.meta)||await ve();if(!Array.isArray(n==null?void 0:n.noteTypes)||n.noteTypes.length===0)throw new Error("No note types are available in Anki.");if(!Array.isArray(n==null?void 0:n.deckNames)||n.deckNames.length===0)throw new Error("No decks are available in Anki.");const o=(p==null?void 0:p.form)||await ke(n);p={mode:e,meta:n,form:o,context:{url:window.location.href||"",title:document.title||"",selectedText:Ve(e,t,P())},snapshots:Array.isArray(r)?r:[],statusKind:"",statusText:"",submitting:!1}}await $()}globalThis.__incrementoTriggerBrowserCapture=e=>{if(String(e||"").trim().toLowerCase()==="snapshot")return Q(),{ok:!0};const r=P();return r?(J({mode:"selection",selectedText:r,snapshots:[]}).catch(n=>{S((n==null?void 0:n.message)||"Failed to open browser capture."),C()}),{ok:!0}):(S("Select text on the page first."),{ok:!1,error:"Select text on the page first."})},document.addEventListener("keydown",e=>{if(!e.altKey||!lt(e)||le()||Ne(e.target))return;if(e.metaKey){e.preventDefault(),e.stopPropagation(),Q();return}if(e.ctrlKey||e.shiftKey)return;const t=P();t&&(e.preventDefault(),e.stopPropagation(),J({mode:"selection",selectedText:t,snapshots:[]}).catch(r=>{S((r==null?void 0:r.message)||"Failed to open browser capture."),C()}))},!0),document.addEventListener("contextmenu",e=>{const t=Ee(e.target);M=we(t)},!0),document.addEventListener("click",e=>{if(!D.modifierClickEnabled||e.defaultPrevented||Number(e.button)!==0||le()||Ne(e.target))return;const t=Ee(e.target);if(!t||!_t(e,D))return;const r=we(t);if(!r)return;D.navigateAfterSave||e.preventDefault();const n=R();n==null||n.sendMessage({type:"SAVE_CLICKED_LINK_AS_WEBPAGE",url:r.url,title:r.title,sourcePageUrl:window.location.href||"",sourcePageTitle:document.title||""},o=>{var a;(a=chrome==null?void 0:chrome.runtime)==null||a.lastError})},!0),document.addEventListener("selectionchange",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("mouseup",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keyup",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keydown",e=>{e.key==="Escape"&&le()&&(e.preventDefault(),e.stopPropagation(),C())},!0);function gt(e){try{const t=new URL(e),r=t.searchParams.get("v");if(r)return r;const n=t.pathname.split("/").filter(Boolean);if(t.hostname==="youtu.be"&&n[0])return n[0];if((n[0]==="shorts"||n[0]==="live"||n[0]==="embed")&&n[1])return n[1]}catch{}return""}function bt(e){const t=String(e||"").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);return t?t[1]:""}function yt(){const e=window.location.href||"",t=window.location.hostname||"";return t.includes("youtube.com")||t==="youtu.be"?{provider:"youtube",videoId:gt(e)}:t.includes("vimeo.com")?{provider:"vimeo",videoId:bt(e)}:{provider:"",videoId:""}}function Me(e){try{const r=new URL(e).searchParams.get("inc_card_id")||"",n=Number(r);if(Number.isFinite(n)&&n>0)return Math.floor(n)}catch{}return 0}function xt(e){const t=String(e||"").replace(/^#/,"").trim();if(!t)return"";const n=t.indexOf("__incremento_resume__=1");return n<0?t:t.slice(0,n).replace(/[&?]+$/,"")}function Et(e){try{const t=new URL(e);t.searchParams.delete("inc_card_id"),t.searchParams.delete("inc_track_web"),t.searchParams.delete("inc_resume_sec"),t.searchParams.delete("inc_resume_media");const r=xt(t.hash);return t.hash=r?`#${r}`:"",t.toString()}catch{return String(e||"")}}function wt(e){try{const t=new URL(e),r=String(t.searchParams.get("inc_track_web")||"").trim().toLowerCase();return r==="1"||r==="true"||r==="yes"||r==="on"}catch{return!1}}function Tt(){if(window.top!==window)return;const e=window.location.href||"";if(!e||!/inc_(card_id|track_web|resume_sec|resume_media)|__incremento_resume__=1/.test(e))return;const t=Et(e);if(!(!t||t===e))try{history.replaceState(history.state,document.title||"",t),me=t}catch{}}function Ie(){const e=Array.from(document.querySelectorAll("video"));return e.length===0?null:(e.sort((t,r)=>{const n=(t.videoWidth||0)*(t.videoHeight||0);return(r.videoWidth||0)*(r.videoHeight||0)-n}),e[0])}function de(e,t=12){const r=Math.max(0,Math.floor(Number(e)||0));if(r<=0)return!1;const n=Ie();if(!n)return t>0&&window.setTimeout(()=>de(r,t-1),500),!1;try{return n.currentTime=r,S(`Resumed to ${r}s`),!0}catch{return t>0&&window.setTimeout(()=>de(r,t-1),500),!1}}function Z(){var i,l;const e=window.location.href||"",{provider:t,videoId:r}=yt(),n=Ie(),o=t?e:String((n==null?void 0:n.currentSrc)||(n==null?void 0:n.src)||"").trim(),a=String(((i=n==null?void 0:n.getAttribute)==null?void 0:i.call(n,"title"))||((l=n==null?void 0:n.getAttribute)==null?void 0:l.call(n,"aria-label"))||document.title||"").trim();return{provider:t,videoId:r,video:n,mediaUrl:o,mediaTitle:a}}function vt(){const{provider:e,video:t}=Z();let r=-1,n=!1;if(t&&(r=Math.max(0,Math.floor(Number(t.currentTime)||0)),n=!0),e==="youtube"&&r<=0){const o=pe();o>=0&&(r=o,n=!0)}if(e==="vimeo"&&r<=0){const o=ue();o>=0&&(r=o,n=!0)}return{found:n,seconds:n?Math.max(0,r):0}}function St(){const e=window.location.href||"",{provider:t,videoId:r,mediaUrl:n,mediaTitle:o}=Z(),a=vt();return{ok:!0,pageUrl:e,pageTitle:document.title||"",provider:t,videoId:r,mediaUrl:n,mediaTitle:o,hasDetectedTime:!!a.found,seconds:Math.max(0,Math.floor(Number(a.seconds)||0)),timeText:a.found?Te(a.seconds):""}}function Fe(e){const t=String(e||"").trim();if(!t)return-1;const r=t.split(":").map(n=>n.trim());return r.every(n=>/^\d+$/.test(n))?r.length===2?Number(r[0])*60+Number(r[1]):r.length===3?Number(r[0])*3600+Number(r[1])*60+Number(r[2]):-1:-1}function ue(){const e=Array.from(document.querySelectorAll('[data-progress-bar-timecode="true"], [class*="Timecode_module_timecode__"]'));for(const t of e){const r=String((t==null?void 0:t.textContent)||"").trim(),n=Fe(r);if(n>=0)return n}return-1}function pe(){const e=Array.from(document.querySelectorAll(".ytp-time-current, [class*='ytp-time-current']"));for(const t of e){const r=String((t==null?void 0:t.textContent)||"").trim(),n=Fe(r);if(n>=0)return n}return-1}async function De(){try{const e=await H({type:"GET_LINKED_CARD_CONTEXT",url:window.location.href||""});if(!(e!=null&&e.linked)||Number(e.cardId)<=0){K(null);return}const t=await H({type:"LOAD_BROWSER_MEDIA_REF"});if(!(t!=null&&t.ok)||!(t!=null&&t.hasReference)){K(null);return}K(t)}catch{K(null)}}let Pe=-1,Oe=0,$e=-1,Ue=0,ee=!1,Y=!0,te=null,me=window.location.href||"";function ne(){Y=!1,te!==null&&(clearInterval(te),te=null)}function We(e){if(!Y)return!1;try{const t=R();return t!=null&&t.id?(t.sendMessage(e,()=>{try{const r=t==null?void 0:t.lastError;r&&/context invalidated/i.test(String(r.message||""))&&ne()}catch{ne()}}),!0):(ne(),!1)}catch{return ne(),!1}}function ze(){if(!Y){O(!1);return}try{const e=R();if(!(e!=null&&e.id)){O(!1);return}e.sendMessage({type:"GET_TRACKING_STATUS",url:window.location.href||""},t=>{try{if(e==null?void 0:e.lastError){O(!1);return}}catch{O(!1);return}O(!!(t!=null&&t.tracked),String((t==null?void 0:t.mode)||""))})}catch{O(!1)}}function A(e=!1,t=!1){if(!Y)return;const{provider:r,videoId:n,video:o}=Z();if(!r)return;let a=-1;if(o&&(a=Math.max(0,Math.floor(Number(o.currentTime)||0))),r==="youtube"&&a<=0){const l=pe();l>=0&&(a=l)}if(r==="vimeo"&&a<=0){const l=ue();l>=0&&(a=l)}if(a<0)return;const i=Date.now();!e&&a===Pe&&i-Oe<4e3||(Pe=a,Oe=i,We({type:"heartbeat",provider:r,videoId:n,cardId:Me(window.location.href||""),flush:!!t,seconds:a,url:window.location.href||"",title:document.title||""}))}function I(e=!1,t=!1){if(!Y)return;const r=window.location.href||"",{provider:n,videoId:o,video:a,mediaUrl:i,mediaTitle:l}=Z();if(!a&&!n)return;let c=-1;if(a&&(c=Math.max(0,Math.floor(Number(a.currentTime)||0))),n==="youtube"&&c<=0){const m=pe();m>=0&&(c=m)}if(n==="vimeo"&&c<=0){const m=ue();m>=0&&(c=m)}if(c<0)return;const s=Date.now();!e&&c===$e&&s-Ue<4e3||($e=c,Ue=s,We({type:"web_media_heartbeat",provider:n,videoId:o,cardId:Me(r),trackEnabled:wt(r),flush:!!t,seconds:c,url:r,mediaUrl:i,mediaTitle:l,title:document.title||""}))}te=window.setInterval(()=>{A(!1,!1),I(!1,!1)},1e3),window.setInterval(()=>{const e=window.location.href||"";e!==me&&(me=e,ee=!1,ze(),De())},750),window.addEventListener("pagehide",()=>{A(!0,!0),I(!0,!0)},{capture:!0}),window.addEventListener("beforeunload",()=>{A(!0,!0),I(!0,!0)},{capture:!0}),document.addEventListener("visibilitychange",()=>{document.visibilityState==="hidden"&&(A(!0,!0),I(!0,!0))}),document.addEventListener("timeupdate",()=>{A(!1,!1),I(!1,!1)},!0),document.addEventListener("play",()=>{A(!0,!1),I(!0,!1)},!0),document.addEventListener("pause",()=>{A(!0,!0),I(!0,!0)},!0),document.addEventListener("ended",()=>A(!0,!0),!0),window.setTimeout(()=>A(!0,!1),1200),window.setTimeout(Tt,1200),window.setTimeout(ze,300),window.setTimeout(()=>{De()},320),window.__incrementoContentScriptState={...window.__incrementoContentScriptState||{},version:G,ready:!0}})();
