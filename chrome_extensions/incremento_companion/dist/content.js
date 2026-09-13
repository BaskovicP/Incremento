import{Z as Bt,$ as Lt,_ as Mt,ag as It,t as i,L as ie,D as Ft,v as xe,ah as Pt,ai as Je,aj as Dt,a2 as _e,ak as le,f as Ot,a6 as Qe,a8 as et,a9 as zt,aa as tt,ac as Wt,al as Ut,n as Kt,g as $t,a as Rt}from"./assets/extension-shared.js";import"./assets/extension-vendor.js";(()=>{var Xe,je,Ge;const J="browser-capture-v8",nt="incremento-browser-capture-root",ce=window.__incrementoContentScriptState&&typeof window.__incrementoContentScriptState=="object"?window.__incrementoContentScriptState:{};if(ce.version===J&&ce.ready)return;window.__incrementoContentScriptState={...ce,version:J,ready:!1},window.__incrementoContentScriptVersion=J;const se="incremento_browser_capture_settings",V=50,rt=0,at=100;let U=Ft,P=null,de=null,Ee="";const K=e=>{if(!(e!=null&&e.errorCode))return String((e==null?void 0:e.error)||"");const t={...e.errorParams};return t.count!=null&&(t.count=Ot(t.count)),i(e.errorCode,t,e.error)};globalThis.__incrementoLastSelectedText=String(globalThis.__incrementoLastSelectedText||"").trim();function $(){var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();return e?(globalThis.__incrementoLastSelectedText=e,e):String(globalThis.__incrementoLastSelectedText||"").trim()}function we(e){const t=Number(e);return Number.isFinite(t)?Math.min(at,Math.max(rt,Number(t.toFixed(4)))):V}function ot(e){return Array.from(new Set(String(e||"").replaceAll(","," ").split(/\s+/).map(t=>t.trim()).filter(Boolean)))}function Te(e,t){const r=Array.isArray(t)?t.filter(Boolean):[],n=r[0]||"",a=o=>o===""?"":r.includes(o)?o:n;return{titleField:a(String((e==null?void 0:e.titleField)||"")),selectedTextField:a(String((e==null?void 0:e.selectedTextField)||"")),urlField:a(String((e==null?void 0:e.urlField)||"")),snapshotField:a(String((e==null?void 0:e.snapshotField)||""))}}function it(e,t){const r=Array.isArray(t==null?void 0:t.noteTypes)?t.noteTypes:[],n=Array.isArray(t==null?void 0:t.deckNames)?t.deckNames.filter(Boolean):[],a=String((e==null?void 0:e.noteTypeName)||""),o=r.find(T=>(T==null?void 0:T.name)===a)||r[0]||null,s=(o==null?void 0:o.name)||"",l=Array.isArray(o==null?void 0:o.fields)?o.fields:[],c=e!=null&&e.mappingsByNoteType&&typeof e.mappingsByNoteType=="object"?e.mappingsByNoteType:{},u=Te(c[s],l),m=String((e==null?void 0:e.deckName)||""),g=n.includes(m)?m:n[0]||"Default";return{noteTypeName:s,deckName:g,priority:we(e==null?void 0:e.priority),tagsText:String((e==null?void 0:e.tagsText)||""),fieldMappings:u,mappingsByNoteType:c}}function Y(e,t,r){return{...e,noteTypeName:t,fieldMappings:{...r},mappingsByNoteType:{...(e==null?void 0:e.mappingsByNoteType)||{},[t]:{...r}}}}function ve(e,t){var r,n,a,o;return{url:String((e==null?void 0:e.url)||"").trim(),title:String((e==null?void 0:e.title)||"").trim()||String((e==null?void 0:e.url)||"").trim()||"Untitled",selectedText:String((e==null?void 0:e.selectedText)||"").trim(),noteTypeName:String((t==null?void 0:t.noteTypeName)||"").trim(),deckName:String((t==null?void 0:t.deckName)||"").trim(),tags:ot(t==null?void 0:t.tagsText),priority:we(t==null?void 0:t.priority),fieldMappings:{titleField:String(((r=t==null?void 0:t.fieldMappings)==null?void 0:r.titleField)||"").trim(),selectedTextField:String(((n=t==null?void 0:t.fieldMappings)==null?void 0:n.selectedTextField)||"").trim(),urlField:String(((a=t==null?void 0:t.fieldMappings)==null?void 0:a.urlField)||"").trim(),snapshotField:String(((o=t==null?void 0:t.fieldMappings)==null?void 0:o.snapshotField)||"").trim()},snapshots:Array.isArray(e==null?void 0:e.snapshots)?e.snapshots.map((s,l)=>({mimeType:"image/png",filename:String((s==null?void 0:s.filename)||`browser-capture-${l+1}.png`),base64:String((s==null?void 0:s.base64)||"").trim()})).filter(s=>s.base64):[]}}function S(e){const t=document.getElementById("incremento-video-time-toast");t&&t.remove();const r=document.createElement("div");r.id="incremento-video-time-toast",r.textContent=String(e||""),Object.assign(r.style,{position:"fixed",zIndex:2147483647,top:"10px",right:"10px",maxWidth:"320px",padding:"10px 14px",background:"rgba(0, 0, 0, 0.86)",color:"#fff",fontSize:"13px",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"6px",boxShadow:"0 2px 8px rgba(0, 0, 0, 0.4)",opacity:"0",transition:"opacity 0.2s ease"}),document.documentElement.appendChild(r),requestAnimationFrame(()=>{r.style.opacity="1"}),setTimeout(()=>{r.style.opacity="0",setTimeout(()=>r.remove(),220)},2400)}async function lt(){try{const e=await chrome.storage.local.get(ie);U=xe(e==null?void 0:e[ie])}catch{U=xe(null)}}function ke(e){var a,o;const t=e instanceof Element?e:(e==null?void 0:e.parentElement)||null,r=(a=t==null?void 0:t.closest)==null?void 0:a.call(t,"a[href]");if(!r)return null;const n=String(r.href||((o=r.getAttribute)==null?void 0:o.call(r,"href"))||"").trim();return et(n)?r:null}function Se(e){var r;if(!e)return null;const t=String(e.href||((r=e.getAttribute)==null?void 0:r.call(e,"href"))||"").trim();return et(t)?{url:t,title:zt(e.textContent||"",t)}:null}function ct(){let e=document.getElementById("incremento-tracking-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-tracking-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483646,top:"52px",right:"10px",display:"none",alignItems:"center",gap:"8px",padding:"8px 12px",background:"linear-gradient(135deg, rgba(10, 34, 64, 0.94), rgba(17, 83, 126, 0.94))",color:"#fff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",letterSpacing:"0.08em",textTransform:"uppercase",borderRadius:"999px",boxShadow:"0 4px 14px rgba(0, 0, 0, 0.28)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"none"});const t=document.createElement("span");t.textContent="●",Object.assign(t.style,{color:"#53f2a5",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(83, 242, 165, 0.85)"}),e.appendChild(t);const r=document.createElement("span");r.textContent="⚠",Object.assign(r.style,{color:"#ffd166",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(255, 209, 102, 0.55)"}),e.appendChild(r);const n=document.createElement("span");return n.id="incremento-tracking-badge-label",n.textContent=i("tracking"),e.appendChild(n),document.documentElement.appendChild(e),e}function D(e,t=""){Ee=e?t:"";const r=ct(),n=document.getElementById("incremento-tracking-badge-label");if(!(!r||!n)){if(!e){r.style.display="none";return}n.textContent=t==="web"?i("tracking_web_card"):i("tracking"),r.style.display="inline-flex"}}function Ce(e){const t=Math.max(0,Math.floor(Number(e)||0)),r=Math.floor(t/3600),n=Math.floor(t%3600/60),a=t%60;return r>0?`${r}:${String(n).padStart(2,"0")}:${String(a).padStart(2,"0")}`:`${n}:${String(a).padStart(2,"0")}`}function st(){let e=document.getElementById("incremento-browser-media-ref-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-browser-media-ref-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483645,top:"96px",right:"10px",display:"none",alignItems:"center",gap:"8px",maxWidth:"320px",padding:"9px 12px",background:"linear-gradient(135deg, rgba(28, 32, 48, 0.96), rgba(34, 62, 96, 0.96))",color:"#eef5ff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"14px",boxShadow:"0 5px 18px rgba(0, 0, 0, 0.30)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"auto"});const t=document.createElement("span");t.textContent="▶",Object.assign(t.style,{color:"#8fd3ff",fontSize:"11px",lineHeight:"1"}),e.appendChild(t);const r=document.createElement("span");r.id="incremento-browser-media-ref-badge-label",r.textContent="",Object.assign(r.style,{flex:"1 1 auto",minWidth:"0"}),e.appendChild(r);const n=document.createElement("button");return n.type="button",n.textContent="×",n.setAttribute("aria-label",i("saved_time_badge_dismiss")),Object.assign(n.style,{appearance:"none",border:"0",background:"transparent",color:"#a9bfdc",cursor:"pointer",fontSize:"16px",fontWeight:"700",lineHeight:"1",padding:"0 0 0 4px",margin:"0",pointerEvents:"auto"}),n.addEventListener("click",a=>{a.preventDefault(),a.stopPropagation(),re=!0,e.style.display="none"}),e.appendChild(n),document.documentElement.appendChild(e),e}function R(e){de=e;const t=st(),r=document.getElementById("incremento-browser-media-ref-badge-label");if(!t||!r)return;if(!!!(e!=null&&e.hasReference)){t.style.display="none";return}if(re)return;const a=String((e==null?void 0:e.timeText)||Ce(e==null?void 0:e.seconds));r.textContent=a?i("last_saved_time",{time:a}):i("last_saved"),t.style.display="inline-flex"}function H(){try{return(chrome==null?void 0:chrome.runtime)||null}catch{return null}}Bt(),Lt(),Mt(()=>{var r;const e=document.getElementById("incremento-tracking-badge");It(e,()=>D(!0,Ee)),de&&R(de);const t=document.querySelector("#incremento-browser-media-ref-badge button");t==null||t.setAttribute("aria-label",i("saved_time_badge_dismiss")),(r=h==null?void 0:h.refreshLanguage)==null||r.call(h)}),lt();try{(je=(Xe=chrome==null?void 0:chrome.storage)==null?void 0:Xe.onChanged)==null||je.addListener((e,t)=>{var r;t!=="local"||!e||!Object.prototype.hasOwnProperty.call(e,ie)||(U=xe((r=e[ie])==null?void 0:r.newValue))})}catch{}try{const e=H();(Ge=e==null?void 0:e.onMessage)==null||Ge.addListener((t,r,n)=>{var a;if(!t||!t.type)return!1;if(t.type==="SHOW_TOAST")return S(t.text||""),n==null||n({ok:!0}),!1;if(t.type==="TRIGGER_BROWSER_CAPTURE"){if(String(t.mode||"").trim().toLowerCase()==="snapshot")return ee(),n==null||n({ok:!0}),!1;const s=$();return s?(te({mode:"selection",selectedText:s,snapshots:[]}).then(()=>n==null?void 0:n({ok:!0}),l=>{S((l==null?void 0:l.message)||i("open_capture_failed")),B(),n==null||n({ok:!1,error:String((l==null?void 0:l.message)||"")})}),!0):(S(i("select_page_text")),n==null||n({ok:!1}),!1)}if(t.type==="GET_PAGE_CONTEXT"){const o={html:((a=document.documentElement)==null?void 0:a.outerHTML)||"",selectionText:$(),title:document.title||"",url:window.location.href||""},s=Pt(o);return s.ok?(n==null||n({ok:!0,...o}),!1):(n==null||n({...s,error:K(s)}),!1)}if(t.type==="GET_CONTEXT_LINK_INFO")return n==null||n({ok:!0,url:String((P==null?void 0:P.url)||""),title:String((P==null?void 0:P.title)||"")}),!1;if(t.type==="GET_CURRENT_MEDIA_CONTEXT")return n==null||n(At()),!1;if(t.type==="APPLY_MEDIA_RESUME"){const o=fe(t.seconds);return n==null||n({ok:o}),!1}return t.type==="UPDATE_BROWSER_MEDIA_REF_BADGE"&&(re=!1,R(t.reference||null),n==null||n({ok:!0})),!1})}catch{}let h=null,f=null;function X(e){return new Promise((t,r)=>{const n=H();if(!(n!=null&&n.sendMessage)){r(new Error(i("extension_runtime_unavailable")));return}n.sendMessage(e,a=>{const o=chrome.runtime.lastError;if(o){r(new Error(o.message||i("extension_request_failed")));return}t(a||null)})})}async function Ne(){const e=await X({type:"LOAD_BROWSER_CAPTURE_META"});if(!(e!=null&&e.ok))throw new Error(String((e==null?void 0:e.error)||i("load_capture_meta_failed")));return e}async function Ae(e){const t=await X({type:"SUBMIT_BROWSER_CAPTURE",payload:e});if(!(t!=null&&t.ok))throw new Error(String((t==null?void 0:t.error)||i("failed_submit_capture")));return t}async function dt(){const e=await X({type:"CAPTURE_VISIBLE_TAB"});if(!(e!=null&&e.ok)||!(e!=null&&e.dataUrl))throw new Error(String((e==null?void 0:e.error)||i("failed_capture_tab")));return e.dataUrl}async function Be(e){let t={};try{const r=await chrome.storage.local.get(se);t=(r==null?void 0:r[se])||{}}catch{t={}}return it(t,e)}async function Le(e){try{await chrome.storage.local.set({[se]:{noteTypeName:String((e==null?void 0:e.noteTypeName)||""),deckName:String((e==null?void 0:e.deckName)||""),priority:Number((e==null?void 0:e.priority)??V),tagsText:String((e==null?void 0:e.tagsText)||""),mappingsByNoteType:(e==null?void 0:e.mappingsByNoteType)||{}}})}catch{}}async function Me(e="",t=[]){const r=(f==null?void 0:f.meta)||await Ne();if(!Array.isArray(r==null?void 0:r.noteTypes)||r.noteTypes.length===0)throw new Error(i("no_note_types"));if(!Array.isArray(r==null?void 0:r.deckNames)||r.deckNames.length===0)throw new Error(i("no_decks"));const n=(f==null?void 0:f.form)||await Be(r);return f={mode:"snapshot",meta:r,form:n,context:{url:window.location.href||"",title:document.title||"",selectedText:Je("snapshot",e,$())},snapshots:Array.isArray(t)?t:[],statusKind:"",statusText:"",submitting:!1},f}async function ut(e="",t=[]){const r=await Me(e,t),n=ve({...r.context,snapshots:r.snapshots.map(s=>({filename:s.filename,base64:s.base64}))},r.form),a=Qe(n);if(!a.ok)throw new Error(i("continue_choose_fields",{error:K(a)}));const o=await Ae(n);return await Le(r.form),o}function Ie(e){const t=e instanceof Element?e:(e==null?void 0:e.parentElement)||null;return t?t.closest("input, textarea, select")?!0:!!t.closest('[contenteditable=""], [contenteditable="true"]'):!1}function ue(){return!!h}function pt(e){return String((e==null?void 0:e.code)||"").toLowerCase()==="keyx"}function pe(e){var n;const t=h==null?void 0:h.shell,r=e==null?void 0:e.target;if(!(!t||!(r instanceof Node)||!t.contains(r))){if(e.type==="keydown"&&((n=h==null?void 0:h.handleTagAutocompleteKeyDown)!=null&&n.call(h,e))){e.stopPropagation();return}if(e.type==="keydown"&&e.key==="Escape"){e.preventDefault(),e.stopPropagation(),B();return}e.stopPropagation()}}function Q(){if(h)return h;const e=document.createElement("div");e.id=nt,e.style.all="initial";const t=e.attachShadow({mode:"open"});document.documentElement.appendChild(e),t.addEventListener("keydown",pe,!0),t.addEventListener("keypress",pe,!0),t.addEventListener("keyup",pe,!0);const r=document.createElement("style");r.textContent=`
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
    `,t.appendChild(r);const n=document.createElement("div");return n.className="shell",t.appendChild(n),h={host:e,shadow:t,shell:n},h}function B(){var e;(e=h==null?void 0:h.host)!=null&&e.isConnected&&h.host.remove(),h=null,f=null}function Fe(){const e=Q();e.handleTagAutocompleteKeyDown=null,e.shell.textContent=""}function mt(e,t,r){const n=document.createElement("div");n.className="tag-autocomplete";const a=document.createElement("input");a.id="incremento-browser-capture-tags",a.type="text",a.value=String(e||""),a.placeholder="tag-one tag-two",a.autocomplete="off",a.spellcheck=!1,a.setAttribute("role","combobox"),a.setAttribute("aria-autocomplete","list");const o=document.createElement("div");o.id="incremento-browser-capture-tag-suggestions",o.className="tag-suggestions",o.setAttribute("role","listbox"),o.hidden=!0,a.setAttribute("aria-controls",o.id),a.setAttribute("aria-expanded","false");const s=Kt(t);let l=!1,c=0,u=[];const m=()=>{var y;Array.from(o.children).forEach((b,_)=>{b.classList.toggle("is-active",_===c),b.setAttribute("aria-selected",_===c?"true":"false")}),!o.hidden&&u.length>0?(a.setAttribute("aria-activedescendant",`${o.id}-${c}`),(y=o.children[c])==null||y.scrollIntoView({block:"nearest"})):a.removeAttribute("aria-activedescendant")},g=()=>{const y=a.selectionStart??a.value.length;if(u=$t(s,a.value,y),c=u.length>0?Math.min(c,u.length-1):0,o.textContent="",o.hidden=!l||u.length===0,a.setAttribute("aria-expanded",o.hidden?"false":"true"),o.hidden){m();return}u.forEach((b,_)=>{const d=document.createElement("button");d.id=`${o.id}-${_}`,d.type="button",d.setAttribute("role","option"),d.setAttribute("aria-selected",_===c?"true":"false"),d.className=_===c?"is-active":"",d.textContent=b,d.addEventListener("mouseenter",()=>{c=_,m()}),d.addEventListener("mousedown",E=>{E.preventDefault(),T(b)}),o.appendChild(d)}),m()},T=y=>{const b=Rt(a.value,y,a.selectionStart??a.value.length,a.selectionEnd??a.value.length);a.value=b.value,r(b.value),l=!1,c=0,a.focus(),a.setSelectionRange(b.cursor,b.cursor),g()},L=y=>{if(y.target!==a)return!1;if(y.key==="Escape"&&l)return y.preventDefault(),l=!1,g(),!0;if(!u.length)return!1;if(y.key==="ArrowDown"||y.key==="ArrowUp"){y.preventDefault();const b=y.key==="ArrowDown"?1:-1;if(!l)l=!0,c=b>0?0:u.length-1;else return c=(c+b+u.length)%u.length,m(),!0;return g(),!0}return l&&(y.key==="Enter"||y.key==="Tab")?(y.preventDefault(),T(u[c]),!0):!1};return a.addEventListener("input",()=>{r(a.value),c=0,l=!0,g()}),a.addEventListener("focus",()=>{l=!0,g()}),a.addEventListener("click",()=>{c=0,l=!0,g()}),a.addEventListener("select",g),a.addEventListener("blur",()=>{l=!1,g()}),n.appendChild(a),n.appendChild(o),{element:n,handleKeyDown:L}}function ft(e,t){const r=document.createElement("div");r.className="snapshots";for(const n of t){const a=document.createElement("div");a.className="snapshot-card";const o=document.createElement("img");o.src=n.dataUrl,o.alt=n.filename,a.appendChild(o);const s=document.createElement("div");s.className="snapshot-footer";const l=document.createElement("span");l.textContent=n.filename,s.appendChild(l);const c=document.createElement("button");c.type="button",c.textContent=i("remove"),c.addEventListener("click",()=>{f.snapshots=f.snapshots.filter(u=>u.id!==n.id),O()}),s.appendChild(c),a.appendChild(s),r.appendChild(a)}return r}async function O(){var qe;const e=Q(),{shell:t,shadow:r}=e;e.refreshLanguage=()=>{O()};const n=f;Fe();const a=document.createElement("div");a.className="backdrop",a.addEventListener("click",()=>B()),t.appendChild(a);const o=document.createElement("section");o.className="panel",t.appendChild(o);const s=document.createElement("p");s.className="eyebrow",s.textContent=n.mode==="snapshot"?i("browser_snapshot"):i("browser_selection"),o.appendChild(s);const l=document.createElement("h2");l.textContent=i("send_capture_anki"),o.appendChild(l);const c=document.createElement("p");c.className="lead",c.textContent=n.mode==="snapshot"?_e("snapshots_ready",n.snapshots.length,{url:n.context.url}):i("selected_text_from",{url:n.context.url}),o.appendChild(c);const u=document.createElement("form");u.noValidate=!0;const m=document.createElement("div");m.className="grid",u.appendChild(m);const g=(p,x,k=!1,w="")=>{const F=document.createElement("div");F.className=`field${k?" full":""}`;const Ze=document.createElement("label");if(Ze.textContent=p,F.appendChild(Ze),F.appendChild(x),w){const ye=document.createElement("p");ye.className="field-note",ye.textContent=w,F.appendChild(ye)}return F},T=document.createElement("select");for(const p of n.meta.noteTypes){const x=document.createElement("option");x.value=p.name,x.textContent=p.name,T.appendChild(x)}T.value=n.form.noteTypeName,T.addEventListener("change",()=>{var k;const p=n.meta.noteTypes.find(w=>w.name===T.value),x=Te((k=n.form.mappingsByNoteType)==null?void 0:k[T.value],(p==null?void 0:p.fields)||[]);n.form=Y(n.form,T.value,x),O()}),m.appendChild(g(i("note_type"),T));const L=document.createElement("select");for(const p of n.meta.deckNames){const x=document.createElement("option");x.value=p,x.textContent=p,L.appendChild(x)}L.value=n.form.deckName,L.addEventListener("change",()=>{n.form.deckName=L.value}),m.appendChild(g(i("deck"),L));const y=mt(n.form.tagsText,n.meta.tagNames,p=>{n.form.tagsText=p});h.handleTagAutocompleteKeyDown=y.handleKeyDown,m.appendChild(g(i("tags"),y.element,!0,i("tag_hint")));const b=document.createElement("div");b.style.display="grid",b.style.gridTemplateColumns="1fr auto",b.style.gap="10px",b.style.alignItems="center";const _=document.createElement("input");_.type="range",_.min="0",_.max="100",_.step="0.1",_.value=String(n.form.priority??V);const d=document.createElement("input");d.type="number",d.min="0",d.max="100",d.step="0.1",d.style.width="92px",d.value=String(n.form.priority??V);const E=p=>{const x=Number(p),k=Number.isFinite(x)?Math.min(100,Math.max(0,x)):V;n.form.priority=Number(k.toFixed(4)),_.value=String(n.form.priority),d.value=String(n.form.priority)};_.addEventListener("input",()=>E(_.value)),d.addEventListener("change",()=>E(d.value)),b.appendChild(_),b.appendChild(d),m.appendChild(g(i("priority"),b));const C=["",...((qe=n.meta.noteTypes.find(p=>p.name===n.form.noteTypeName))==null?void 0:qe.fields)||[]],N=(p,x)=>{const k=document.createElement("select");for(const w of C){const F=document.createElement("option");F.value=w,F.textContent=w||i("do_not_insert"),k.appendChild(F)}return k.value=C.includes(p)?p:"",k.addEventListener("change",()=>{x(k.value)}),k},W=!!n.context.selectedText;m.appendChild(g(i("page_title_field"),N(n.form.fieldMappings.titleField,p=>{n.form=Y(n.form,n.form.noteTypeName,{...n.form.fieldMappings,titleField:p})}),!1,i("page_title_field_note"))),m.appendChild(g(i("selected_text_field"),N(n.form.fieldMappings.selectedTextField,p=>{n.form=Y(n.form,n.form.noteTypeName,{...n.form.fieldMappings,selectedTextField:p})}),!1,W?i("chars_ready",{count:n.context.selectedText.length}):i("no_text_added"))),m.appendChild(g(i("source_url_field"),N(n.form.fieldMappings.urlField,p=>{n.form=Y(n.form,n.form.noteTypeName,{...n.form.fieldMappings,urlField:p})}),!1,i("source_url_note"))),m.appendChild(g(i("snapshot_field"),N(n.form.fieldMappings.snapshotField,p=>{n.form=Y(n.form,n.form.noteTypeName,{...n.form.fieldMappings,snapshotField:p})}),!0,n.snapshots.length>0?_e("snapshots_selected",n.snapshots.length):i("no_snapshots")));const A=document.createElement("textarea");if(A.value=n.context.selectedText,A.placeholder=n.mode==="snapshot"?i("add_text_snapshots"):i("selected_text_edit"),A.addEventListener("input",()=>{n.context.selectedText=A.value}),m.appendChild(g(n.mode==="snapshot"?i("text_to_add"):i("selected_text"),A,!0,i("inserted_text_note"))),n.snapshots.length>0){const p=document.createElement("div");p.className="field full";const x=document.createElement("label");x.textContent=i("snapshots"),p.appendChild(x),p.appendChild(ft(r,n.snapshots)),m.appendChild(p)}const M=document.createElement("p");M.className=`status${n.statusKind?` ${n.statusKind}`:""}`,M.textContent=n.statusValidation?K(n.statusValidation):n.statusCode?i(n.statusCode):n.statusText,u.appendChild(M);const G=document.createElement("div");if(G.className="actions",n.snapshots.length>0){const p=document.createElement("button");p.type="button",p.className="ghost-btn",p.textContent=i("capture_more"),p.addEventListener("click",()=>ee(n.snapshots)),G.appendChild(p)}const q=document.createElement("button");q.type="button",q.className="secondary-btn",q.textContent=i("language_cancel"),q.addEventListener("click",()=>B()),G.appendChild(q);const Z=document.createElement("button");Z.type="submit",Z.className="primary-btn",Z.textContent=n.submitting?i("saving"):i("create_note"),Z.disabled=!!n.submitting,G.appendChild(Z),u.appendChild(G),u.addEventListener("submit",async p=>{if(p.preventDefault(),n.submitting)return;const x=ve({...n.context,snapshots:n.snapshots.map(w=>({filename:w.filename,base64:w.base64}))},n.form),k=Qe(x);if(!k.ok){n.statusKind="error",n.statusCode="",n.statusValidation=k,n.statusText=K(k),O();return}n.submitting=!0,n.statusKind="",n.statusValidation=null,n.statusCode="creating_note",n.statusText=i("creating_note"),O();try{const w=await Ae(x);await Le(n.form),S(i("created_note",{type:w.noteTypeName,deck:w.deckName})),B()}catch(w){n.submitting=!1,n.statusKind="error",n.statusValidation=null,n.statusCode="",n.statusText=(w==null?void 0:w.message)||i("create_note_failed"),O()}}),o.appendChild(u)}function gt(e){return new Promise((t,r)=>{const n=new Image;n.onload=()=>t(n),n.onerror=()=>r(new Error(i("failed_decode_screenshot"))),n.src=e})}async function ht(e,t){const r=await gt(e),n=r.width/window.innerWidth,a=r.height/window.innerHeight,o=Math.max(0,Math.round(t.x*n)),s=Math.max(0,Math.round(t.y*a)),l=Math.max(1,Math.round(t.width*n)),c=Math.max(1,Math.round(t.height*a)),u=document.createElement("canvas");return u.width=l,u.height=c,u.getContext("2d").drawImage(r,o,s,l,c,0,0,l,c),u.toDataURL("image/png")}function bt(e){const t=String(e||""),r=t.indexOf(",");return r>=0?t.slice(r+1):t}function me(e){const t=Math.abs(e.width),r=Math.abs(e.height);return{x:e.width>=0?e.x:e.x-t,y:e.height>=0?e.y:e.y-r,width:t,height:r}}function Pe(e=2){return new Promise(t=>{const r=Math.max(1,Number(e)||1);let n=0;const a=()=>{if(n+=1,n>=r){t();return}requestAnimationFrame(a)};requestAnimationFrame(a)})}function yt(e,t){if(!(e instanceof Element))return!1;const r=window.getComputedStyle(e),n=t==="x"?r.overflowX:r.overflowY;return/(auto|scroll|overlay)/.test(String(n||""))?t==="x"?e.scrollWidth>e.clientWidth:e.scrollHeight>e.clientHeight:!1}function De(e,t){let r=e instanceof Element?e:null;for(;r;){if(yt(r,t))return r;r=r.parentElement}const n=document.scrollingElement;return n instanceof Element?n:document.documentElement}function xt(e,t){var u;if(!e)return;const r=((u=t==null?void 0:t.style)==null?void 0:u.pointerEvents)||"";t!=null&&t.style&&(t.style.pointerEvents="none");let n=null;try{n=document.elementFromPoint(e.clientX,e.clientY)}finally{t!=null&&t.style&&(t.style.pointerEvents=r)}const a=Number(e.deltaX)||0,o=Number(e.deltaY)||0,s=a?De(n,"x"):null,l=o?De(n,"y"):null,c=document.scrollingElement instanceof Element?document.scrollingElement:document.documentElement;a&&(s||c).scrollBy({left:a,top:0,behavior:"auto"}),o&&(l||c).scrollBy({left:0,top:o,behavior:"auto"})}async function _t(e,t=[]){if(t.length>=le)throw new Error(i("too_many_snapshots",{count:le}));const r=Q();r.shell.style.display="none";try{await Pe(2);const n=await dt(),a=tt(n,{maxBytes:Wt});if(!a.ok)throw new Error(K(a));const o=me(e),s=await ht(n,o),l=tt(s,{maxBytes:Ut});if(!l.ok)throw new Error(K(l));return{id:`${Date.now()}-${t.length}-${Math.random().toString(16).slice(2,8)}`,filename:`browser-capture-${t.length+1}.png`,dataUrl:s,base64:bt(s)}}catch(n){throw new Error((n==null?void 0:n.message)||i("failed_capture_tab"))}finally{h!=null&&h.shell&&(h.shell.style.display="",await Pe(1))}}function ee(e=[]){var _;const t=Q();Fe();const r=e.length>0&&((_=f==null?void 0:f.context)==null?void 0:_.selectedText)||"";f={mode:"snapshot",meta:(f==null?void 0:f.meta)||null,form:(f==null?void 0:f.form)||null,context:{url:window.location.href||"",title:document.title||"",selectedText:r},snapshots:[...e],statusKind:"",statusText:"",submitting:!1};const n=t.shell,a=document.createElement("div");a.className="capture-shell",n.appendChild(a);const o=document.createElement("div");o.className="capture-toolbar";const s=d=>{o.replaceChildren();const E=document.createElement("strong");E.textContent=i("snapshot_mode"),o.appendChild(E);const v=document.createElement("span");v.textContent=i(d),o.appendChild(v);const C=document.createElement("span");C.className="spacer",o.appendChild(C)};s("snapshot_mode_intro"),n.appendChild(o);const l=[...e];let c=null,u=null,m=!1;const g=()=>{s("snapshot_mode_hint");const d=document.createElement("span");d.textContent=m?i("capturing"):_e("snapshot_ready",l.length),o.appendChild(d);const E=document.createElement("button");E.type="button",E.className="toolbar-btn",E.textContent=i("undo"),E.disabled=m||l.length===0,E.addEventListener("click",()=>{l.pop(),g()}),o.appendChild(E);const v=document.createElement("button");v.type="button",v.className="toolbar-btn",v.textContent=i("clear"),v.disabled=m||l.length===0,v.addEventListener("click",()=>{l.splice(0,l.length),g()}),o.appendChild(v);const C=document.createElement("button");C.type="button",C.className="toolbar-btn",C.textContent=i("language_cancel"),C.addEventListener("click",()=>B()),o.appendChild(C);const N=document.createElement("button");N.type="button",N.className="toolbar-btn",N.textContent=i("extract_now"),N.disabled=m||l.length===0,N.addEventListener("click",async()=>{var A;if(!m){if(!l.length){S(i("draw_region_first"));return}m=!0,g();try{const M=await ut(((A=f==null?void 0:f.context)==null?void 0:A.selectedText)||"",[...l]);S(i("created_note",{type:M.noteTypeName,deck:M.deckName})),B()}catch(M){m=!1,g(),S((M==null?void 0:M.message)||i("create_note_failed"))}}}),o.appendChild(N);const W=document.createElement("button");W.type="button",W.className="toolbar-btn primary",W.textContent=i("continue"),W.addEventListener("click",()=>{var A;if(!m){if(!l.length){S(i("draw_region_first"));return}te({mode:"snapshot",selectedText:((A=f==null?void 0:f.context)==null?void 0:A.selectedText)||"",snapshots:[...l]})}}),o.appendChild(W)};t.refreshLanguage=g;const T=(d,E)=>{if(l.length>=le){S(i("too_many_snapshots",{count:le}));return}u={x:d,y:E,width:0,height:0},c=document.createElement("div"),c.className="selection-rect",c.dataset.label=i("capture_label",{count:l.length+1}),a.appendChild(c)},L=()=>{if(!c||!u)return;const d=me(u);Object.assign(c.style,{left:`${d.x}px`,top:`${d.y}px`,width:`${d.width}px`,height:`${d.height}px`})};a.addEventListener("pointerdown",d=>{m||d.button!==0||d.target!==a||(d.preventDefault(),T(d.clientX,d.clientY),L())}),a.addEventListener("pointermove",d=>{u&&(d.preventDefault(),u.width=d.clientX-u.x,u.height=d.clientY-u.y,L())});const y=d=>{u||m||(d.preventDefault(),xt(d,t.host))};a.addEventListener("wheel",y,{passive:!1}),o.addEventListener("wheel",y,{passive:!1});const b=async()=>{if(!c||!u)return;const d=me(u),E=c;if(d.width>=24&&d.height>=24){m=!0,g();try{const v=await _t(d,l);l.push(v)}catch(v){S((v==null?void 0:v.message)||i("failed_capture_tab"))}}else E.remove();E.remove(),c=null,u=null,m=!1,g()};a.addEventListener("pointerup",()=>{b()}),a.addEventListener("pointercancel",()=>{b()}),g()}async function te({mode:e,selectedText:t="",snapshots:r=[]}){if(e==="snapshot")await Me(t,r);else{const n=(f==null?void 0:f.meta)||await Ne();if(!Array.isArray(n==null?void 0:n.noteTypes)||n.noteTypes.length===0)throw new Error(i("no_note_types"));if(!Array.isArray(n==null?void 0:n.deckNames)||n.deckNames.length===0)throw new Error(i("no_decks"));const a=(f==null?void 0:f.form)||await Be(n);f={mode:e,meta:n,form:a,context:{url:window.location.href||"",title:document.title||"",selectedText:Je(e,t,$())},snapshots:Array.isArray(r)?r:[],statusKind:"",statusText:"",submitting:!1}}await O()}globalThis.__incrementoTriggerBrowserCapture=e=>{if(String(e||"").trim().toLowerCase()==="snapshot")return ee(),{ok:!0};const r=$();return r?(te({mode:"selection",selectedText:r,snapshots:[]}).catch(n=>{S((n==null?void 0:n.message)||i("open_capture_failed")),B()}),{ok:!0}):(S(i("select_page_text")),{ok:!1,error:i("select_page_text")})},document.addEventListener("keydown",e=>{if(!e.altKey||!pt(e)||ue()||Ie(e.target))return;if(e.metaKey){e.preventDefault(),e.stopPropagation(),ee();return}if(e.ctrlKey||e.shiftKey)return;const t=$();t&&(e.preventDefault(),e.stopPropagation(),te({mode:"selection",selectedText:t,snapshots:[]}).catch(r=>{S((r==null?void 0:r.message)||i("open_capture_failed")),B()}))},!0),document.addEventListener("contextmenu",e=>{const t=ke(e.target);P=Se(t)},!0),document.addEventListener("click",e=>{if(!U.modifierClickEnabled||e.defaultPrevented||Number(e.button)!==0||ue()||Ie(e.target))return;const t=ke(e.target);if(!t||!Dt(e,U))return;const r=Se(t);if(!r)return;U.navigateAfterSave||e.preventDefault();const n=H();n==null||n.sendMessage({type:"SAVE_CLICKED_LINK_AS_WEBPAGE",url:r.url,title:r.title,sourcePageUrl:window.location.href||"",sourcePageTitle:document.title||""},a=>{var o;(o=chrome==null?void 0:chrome.runtime)==null||o.lastError})},!0),document.addEventListener("selectionchange",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("mouseup",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keyup",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keydown",e=>{e.key==="Escape"&&ue()&&(e.preventDefault(),e.stopPropagation(),B())},!0);function Et(e){try{const t=new URL(e),r=t.searchParams.get("v");if(r)return r;const n=t.pathname.split("/").filter(Boolean);if(t.hostname==="youtu.be"&&n[0])return n[0];if((n[0]==="shorts"||n[0]==="live"||n[0]==="embed")&&n[1])return n[1]}catch{}return""}function wt(e){const t=String(e||"").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);return t?t[1]:""}function Tt(){const e=window.location.href||"",t=window.location.hostname||"";return t.includes("youtube.com")||t==="youtu.be"?{provider:"youtube",videoId:Et(e)}:t.includes("vimeo.com")?{provider:"vimeo",videoId:wt(e)}:{provider:"",videoId:""}}function Oe(e){try{const r=new URL(e).searchParams.get("inc_card_id")||"",n=Number(r);if(Number.isFinite(n)&&n>0)return Math.floor(n)}catch{}return 0}function vt(e){const t=String(e||"").replace(/^#/,"").trim();if(!t)return"";const n=t.indexOf("__incremento_resume__=1");return n<0?t:t.slice(0,n).replace(/[&?]+$/,"")}function kt(e){try{const t=new URL(e);t.searchParams.delete("inc_card_id"),t.searchParams.delete("inc_track_web"),t.searchParams.delete("inc_resume_sec"),t.searchParams.delete("inc_resume_media");const r=vt(t.hash);return t.hash=r?`#${r}`:"",t.toString()}catch{return String(e||"")}}function St(e){try{const t=new URL(e),r=String(t.searchParams.get("inc_track_web")||"").trim().toLowerCase();return r==="1"||r==="true"||r==="yes"||r==="on"}catch{return!1}}function Ct(){if(window.top!==window)return;const e=window.location.href||"";if(!e||!/inc_(card_id|track_web|resume_sec|resume_media)|__incremento_resume__=1/.test(e))return;const t=kt(e);if(!(!t||t===e))try{history.replaceState(history.state,document.title||"",t),be=t}catch{}}function ze(){const e=Array.from(document.querySelectorAll("video"));return e.length===0?null:(e.sort((t,r)=>{const n=(t.videoWidth||0)*(t.videoHeight||0);return(r.videoWidth||0)*(r.videoHeight||0)-n}),e[0])}function fe(e,t=12){const r=Math.max(0,Math.floor(Number(e)||0));if(r<=0)return!1;const n=ze();if(!n)return t>0&&window.setTimeout(()=>fe(r,t-1),500),!1;try{return n.currentTime=r,S(i("resumed_to",{seconds:r})),!0}catch{return t>0&&window.setTimeout(()=>fe(r,t-1),500),!1}}function ne(){var s,l;const e=window.location.href||"",{provider:t,videoId:r}=Tt(),n=ze(),a=t?e:String((n==null?void 0:n.currentSrc)||(n==null?void 0:n.src)||"").trim(),o=String(((s=n==null?void 0:n.getAttribute)==null?void 0:s.call(n,"title"))||((l=n==null?void 0:n.getAttribute)==null?void 0:l.call(n,"aria-label"))||document.title||"").trim();return{provider:t,videoId:r,video:n,mediaUrl:a,mediaTitle:o}}function Nt(){const{provider:e,video:t}=ne();let r=-1,n=!1;if(t&&(r=Math.max(0,Math.floor(Number(t.currentTime)||0)),n=!0),e==="youtube"&&r<=0){const a=he();a>=0&&(r=a,n=!0)}if(e==="vimeo"&&r<=0){const a=ge();a>=0&&(r=a,n=!0)}return{found:n,seconds:n?Math.max(0,r):0}}function At(){const e=window.location.href||"",{provider:t,videoId:r,mediaUrl:n,mediaTitle:a}=ne(),o=Nt();return{ok:!0,pageUrl:e,pageTitle:document.title||"",provider:t,videoId:r,mediaUrl:n,mediaTitle:a,hasDetectedTime:!!o.found,seconds:Math.max(0,Math.floor(Number(o.seconds)||0)),timeText:o.found?Ce(o.seconds):""}}function We(e){const t=String(e||"").trim();if(!t)return-1;const r=t.split(":").map(n=>n.trim());return r.every(n=>/^\d+$/.test(n))?r.length===2?Number(r[0])*60+Number(r[1]):r.length===3?Number(r[0])*3600+Number(r[1])*60+Number(r[2]):-1:-1}function ge(){const e=Array.from(document.querySelectorAll('[data-progress-bar-timecode="true"], [class*="Timecode_module_timecode__"]'));for(const t of e){const r=String((t==null?void 0:t.textContent)||"").trim(),n=We(r);if(n>=0)return n}return-1}function he(){const e=Array.from(document.querySelectorAll(".ytp-time-current, [class*='ytp-time-current']"));for(const t of e){const r=String((t==null?void 0:t.textContent)||"").trim(),n=We(r);if(n>=0)return n}return-1}async function Ue(){try{const e=await X({type:"GET_LINKED_CARD_CONTEXT",url:window.location.href||""});if(!(e!=null&&e.linked)||Number(e.cardId)<=0){R(null);return}const t=await X({type:"LOAD_BROWSER_MEDIA_REF"});if(!(t!=null&&t.ok)||!(t!=null&&t.hasReference)){R(null);return}R(t)}catch{R(null)}}let Ke=-1,$e=0,Re=-1,Ve=0,re=!1,j=!0,ae=null,be=window.location.href||"";function oe(){j=!1,ae!==null&&(clearInterval(ae),ae=null)}function Ye(e){if(!j)return!1;try{const t=H();return t!=null&&t.id?(t.sendMessage(e,()=>{try{const r=t==null?void 0:t.lastError;r&&/context invalidated/i.test(String(r.message||""))&&oe()}catch{oe()}}),!0):(oe(),!1)}catch{return oe(),!1}}function He(){if(!j){D(!1);return}try{const e=H();if(!(e!=null&&e.id)){D(!1);return}e.sendMessage({type:"GET_TRACKING_STATUS",url:window.location.href||""},t=>{try{if(e==null?void 0:e.lastError){D(!1);return}}catch{D(!1);return}D(!!(t!=null&&t.tracked),String((t==null?void 0:t.mode)||""))})}catch{D(!1)}}function I(e=!1,t=!1){if(!j)return;const{provider:r,videoId:n,video:a}=ne();if(!r)return;let o=-1;if(a&&(o=Math.max(0,Math.floor(Number(a.currentTime)||0))),r==="youtube"&&o<=0){const l=he();l>=0&&(o=l)}if(r==="vimeo"&&o<=0){const l=ge();l>=0&&(o=l)}if(o<0)return;const s=Date.now();!e&&o===Ke&&s-$e<4e3||(Ke=o,$e=s,Ye({type:"heartbeat",provider:r,videoId:n,cardId:Oe(window.location.href||""),flush:!!t,seconds:o,url:window.location.href||"",title:document.title||""}))}function z(e=!1,t=!1){if(!j)return;const r=window.location.href||"",{provider:n,videoId:a,video:o,mediaUrl:s,mediaTitle:l}=ne();if(!o&&!n)return;let c=-1;if(o&&(c=Math.max(0,Math.floor(Number(o.currentTime)||0))),n==="youtube"&&c<=0){const m=he();m>=0&&(c=m)}if(n==="vimeo"&&c<=0){const m=ge();m>=0&&(c=m)}if(c<0)return;const u=Date.now();!e&&c===Re&&u-Ve<4e3||(Re=c,Ve=u,Ye({type:"web_media_heartbeat",provider:n,videoId:a,cardId:Oe(r),trackEnabled:St(r),flush:!!t,seconds:c,url:r,mediaUrl:s,mediaTitle:l,title:document.title||""}))}ae=window.setInterval(()=>{I(!1,!1),z(!1,!1)},1e3),window.setInterval(()=>{const e=window.location.href||"";e!==be&&(be=e,re=!1,He(),Ue())},750),window.addEventListener("pagehide",()=>{I(!0,!0),z(!0,!0)},{capture:!0}),window.addEventListener("beforeunload",()=>{I(!0,!0),z(!0,!0)},{capture:!0}),document.addEventListener("visibilitychange",()=>{document.visibilityState==="hidden"&&(I(!0,!0),z(!0,!0))}),document.addEventListener("timeupdate",()=>{I(!1,!1),z(!1,!1)},!0),document.addEventListener("play",()=>{I(!0,!1),z(!0,!1)},!0),document.addEventListener("pause",()=>{I(!0,!0),z(!0,!0)},!0),document.addEventListener("ended",()=>I(!0,!0),!0),window.setTimeout(()=>I(!0,!1),1200),window.setTimeout(Ct,1200),window.setTimeout(He,300),window.setTimeout(()=>{Ue()},320),window.__incrementoContentScriptState={...window.__incrementoContentScriptState||{},version:J,ready:!0}})();
