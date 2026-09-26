import{$ as Bt,a1 as Lt,a0 as Mt,am as It,t as i,L as oe,D as Ft,B as xe,ak as Pt,ai as Dt,aj as Ot,an as Qe,ao as Ut,a4 as _e,ap as ie,f as Wt,ad as Ze,ae as zt,a8 as et,af as tt,ah as Rt,aq as Kt,n as $t,g as Ht,a as Vt}from"./assets/extension-shared.js";import"./assets/extension-vendor.js";(()=>{var Ye,je,qe;const J="browser-capture-v9",nt="incremento-browser-capture-root",le=window.__incrementoContentScriptState&&typeof window.__incrementoContentScriptState=="object"?window.__incrementoContentScriptState:{};if(le.version===J&&le.ready)return;window.__incrementoContentScriptState={...le,version:J,ready:!1},window.__incrementoContentScriptVersion=J;const ce="incremento_browser_capture_settings",K=50,rt=0,at=100;let W=Ft,Ee=null,se=null,we="";const z=e=>{if(!(e!=null&&e.errorCode))return String((e==null?void 0:e.error)||"");const t={...e.errorParams};return t.count!=null&&(t.count=Wt(t.count)),i(e.errorCode,t,e.error)};globalThis.__incrementoLastSelectedText=String(globalThis.__incrementoLastSelectedText||"").trim();function $(){var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();return e?(globalThis.__incrementoLastSelectedText=e,e):String(globalThis.__incrementoLastSelectedText||"").trim()}function Te(e){const t=Number(e);return Number.isFinite(t)?Math.min(at,Math.max(rt,Number(t.toFixed(4)))):K}function ot(e){return Array.from(new Set(String(e||"").replaceAll(","," ").split(/\s+/).map(t=>t.trim()).filter(Boolean)))}function ve(e,t){const r=Array.isArray(t)?t.filter(Boolean):[],n=r[0]||"",a=o=>o===""?"":r.includes(o)?o:n;return{titleField:a(String((e==null?void 0:e.titleField)||"")),selectedTextField:a(String((e==null?void 0:e.selectedTextField)||"")),urlField:a(String((e==null?void 0:e.urlField)||"")),snapshotField:a(String((e==null?void 0:e.snapshotField)||""))}}function it(e,t){const r=Array.isArray(t==null?void 0:t.noteTypes)?t.noteTypes:[],n=Array.isArray(t==null?void 0:t.deckNames)?t.deckNames.filter(Boolean):[],a=String((e==null?void 0:e.noteTypeName)||""),o=r.find(T=>(T==null?void 0:T.name)===a)||r[0]||null,c=(o==null?void 0:o.name)||"",l=Array.isArray(o==null?void 0:o.fields)?o.fields:[],s=e!=null&&e.mappingsByNoteType&&typeof e.mappingsByNoteType=="object"?e.mappingsByNoteType:{},d=ve(s[c],l),u=String((e==null?void 0:e.deckName)||""),m=n.includes(u)?u:n[0]||"Default";return{noteTypeName:c,deckName:m,priority:Te(e==null?void 0:e.priority),tagsText:String((e==null?void 0:e.tagsText)||""),fieldMappings:d,mappingsByNoteType:s}}function H(e,t,r){return{...e,noteTypeName:t,fieldMappings:{...r},mappingsByNoteType:{...(e==null?void 0:e.mappingsByNoteType)||{},[t]:{...r}}}}function Se(e,t){var r,n,a,o;return{url:String((e==null?void 0:e.url)||"").trim(),title:String((e==null?void 0:e.title)||"").trim()||String((e==null?void 0:e.url)||"").trim()||"Untitled",selectedText:String((e==null?void 0:e.selectedText)||"").trim(),noteTypeName:String((t==null?void 0:t.noteTypeName)||"").trim(),deckName:String((t==null?void 0:t.deckName)||"").trim(),tags:ot(t==null?void 0:t.tagsText),priority:Te(t==null?void 0:t.priority),fieldMappings:{titleField:String(((r=t==null?void 0:t.fieldMappings)==null?void 0:r.titleField)||"").trim(),selectedTextField:String(((n=t==null?void 0:t.fieldMappings)==null?void 0:n.selectedTextField)||"").trim(),urlField:String(((a=t==null?void 0:t.fieldMappings)==null?void 0:a.urlField)||"").trim(),snapshotField:String(((o=t==null?void 0:t.fieldMappings)==null?void 0:o.snapshotField)||"").trim()},snapshots:Array.isArray(e==null?void 0:e.snapshots)?e.snapshots.map((c,l)=>({mimeType:"image/png",filename:String((c==null?void 0:c.filename)||`browser-capture-${l+1}.png`),base64:String((c==null?void 0:c.base64)||"").trim()})).filter(c=>c.base64):[]}}function C(e){const t=document.getElementById("incremento-video-time-toast");t&&t.remove();const r=document.createElement("div");r.id="incremento-video-time-toast",r.textContent=String(e||""),Object.assign(r.style,{position:"fixed",zIndex:2147483647,top:"10px",right:"10px",maxWidth:"320px",padding:"10px 14px",background:"rgba(0, 0, 0, 0.86)",color:"#fff",fontSize:"13px",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"6px",boxShadow:"0 2px 8px rgba(0, 0, 0, 0.4)",opacity:"0",transition:"opacity 0.2s ease"}),document.documentElement.appendChild(r),requestAnimationFrame(()=>{r.style.opacity="1"}),setTimeout(()=>{r.style.opacity="0",setTimeout(()=>r.remove(),220)},2400)}async function lt(){try{const e=await chrome.storage.local.get(oe);W=xe(e==null?void 0:e[oe])}catch{W=xe(null)}}function Ce(e){var a,o;const t=e instanceof Element?e:(e==null?void 0:e.parentElement)||null,r=(a=t==null?void 0:t.closest)==null?void 0:a.call(t,"a[href]");if(!r)return null;const n=String(r.href||((o=r.getAttribute)==null?void 0:o.call(r,"href"))||"").trim();return Ze(n)?r:null}function de(e){var n,a,o,c,l,s,d,u,m;if(!e)return null;const t=String(e.href||((n=e.getAttribute)==null?void 0:n.call(e,"href"))||"").trim();if(!Ze(t))return null;const r=String(((a=e.getAttribute)==null?void 0:a.call(e,"aria-label"))||((o=e.getAttribute)==null?void 0:o.call(e,"title"))||((s=(l=(c=e.querySelector)==null?void 0:c.call(e,"[aria-label]"))==null?void 0:l.getAttribute)==null?void 0:s.call(l,"aria-label"))||((m=(u=(d=e.querySelector)==null?void 0:d.call(e,"[title]"))==null?void 0:u.getAttribute)==null?void 0:m.call(u,"title"))||e.textContent||"");return{url:t,title:zt(r,t)}}function ct(){let e=document.getElementById("incremento-tracking-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-tracking-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483646,top:"52px",right:"10px",display:"none",alignItems:"center",gap:"8px",padding:"8px 12px",background:"linear-gradient(135deg, rgba(10, 34, 64, 0.94), rgba(17, 83, 126, 0.94))",color:"#fff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",letterSpacing:"0.08em",textTransform:"uppercase",borderRadius:"999px",boxShadow:"0 4px 14px rgba(0, 0, 0, 0.28)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"none"});const t=document.createElement("span");t.textContent="●",Object.assign(t.style,{color:"#53f2a5",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(83, 242, 165, 0.85)"}),e.appendChild(t);const r=document.createElement("span");r.textContent="⚠",Object.assign(r.style,{color:"#ffd166",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(255, 209, 102, 0.55)"}),e.appendChild(r);const n=document.createElement("span");return n.id="incremento-tracking-badge-label",n.textContent=i("tracking"),e.appendChild(n),document.documentElement.appendChild(e),e}function P(e,t=""){we=e?t:"";const r=ct(),n=document.getElementById("incremento-tracking-badge-label");if(!(!r||!n)){if(!e){r.style.display="none";return}n.textContent=t==="web"?i("tracking_web_card"):i("tracking"),r.style.display="inline-flex"}}function ke(e){const t=Math.max(0,Math.floor(Number(e)||0)),r=Math.floor(t/3600),n=Math.floor(t%3600/60),a=t%60;return r>0?`${r}:${String(n).padStart(2,"0")}:${String(a).padStart(2,"0")}`:`${n}:${String(a).padStart(2,"0")}`}function st(){let e=document.getElementById("incremento-browser-media-ref-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-browser-media-ref-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483645,top:"96px",right:"10px",display:"none",alignItems:"center",gap:"8px",maxWidth:"320px",padding:"9px 12px",background:"linear-gradient(135deg, rgba(28, 32, 48, 0.96), rgba(34, 62, 96, 0.96))",color:"#eef5ff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"14px",boxShadow:"0 5px 18px rgba(0, 0, 0, 0.30)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"auto"});const t=document.createElement("span");t.textContent="▶",Object.assign(t.style,{color:"#8fd3ff",fontSize:"11px",lineHeight:"1"}),e.appendChild(t);const r=document.createElement("span");r.id="incremento-browser-media-ref-badge-label",r.textContent="",Object.assign(r.style,{flex:"1 1 auto",minWidth:"0"}),e.appendChild(r);const n=document.createElement("button");return n.type="button",n.textContent="×",n.setAttribute("aria-label",i("saved_time_badge_dismiss")),Object.assign(n.style,{appearance:"none",border:"0",background:"transparent",color:"#a9bfdc",cursor:"pointer",fontSize:"16px",fontWeight:"700",lineHeight:"1",padding:"0 0 0 4px",margin:"0",pointerEvents:"auto"}),n.addEventListener("click",a=>{a.preventDefault(),a.stopPropagation(),ne=!0,e.style.display="none"}),e.appendChild(n),document.documentElement.appendChild(e),e}function R(e){se=e;const t=st(),r=document.getElementById("incremento-browser-media-ref-badge-label");if(!t||!r)return;if(!!!(e!=null&&e.hasReference)){t.style.display="none";return}if(ne)return;const a=String((e==null?void 0:e.timeText)||ke(e==null?void 0:e.seconds));r.textContent=a?i("last_saved_time",{time:a}):i("last_saved"),t.style.display="inline-flex"}function V(){try{return(chrome==null?void 0:chrome.runtime)||null}catch{return null}}Bt(),Lt(),Mt(()=>{var r;const e=document.getElementById("incremento-tracking-badge");It(e,()=>P(!0,we)),se&&R(se);const t=document.querySelector("#incremento-browser-media-ref-badge button");t==null||t.setAttribute("aria-label",i("saved_time_badge_dismiss")),(r=h==null?void 0:h.refreshLanguage)==null||r.call(h)}),lt();try{(je=(Ye=chrome==null?void 0:chrome.storage)==null?void 0:Ye.onChanged)==null||je.addListener((e,t)=>{var r;t!=="local"||!e||!Object.prototype.hasOwnProperty.call(e,oe)||(W=xe((r=e[oe])==null?void 0:r.newValue))})}catch{}try{const e=V();(qe=e==null?void 0:e.onMessage)==null||qe.addListener((t,r,n)=>{var a;if(!t||!t.type)return!1;if(t.type==="SHOW_TOAST")return C(t.text||""),n==null||n({ok:!0}),!1;if(t.type==="TRIGGER_BROWSER_CAPTURE"){if(String(t.mode||"").trim().toLowerCase()==="snapshot")return Z(),n==null||n({ok:!0}),!1;const c=$();return c?(ee({mode:"selection",selectedText:c,snapshots:[]}).then(()=>n==null?void 0:n({ok:!0}),l=>{C((l==null?void 0:l.message)||i("open_capture_failed")),B(),n==null||n({ok:!1,error:String((l==null?void 0:l.message)||"")})}),!0):(C(i("select_page_text")),n==null||n({ok:!1}),!1)}if(t.type==="GET_PAGE_CONTEXT"){const o=Pt(Dt,Ot,{includeHtml:t.includeHtml!==!1,htmlScope:t.htmlScope});return o.ok?(n==null||n(o),!1):(n==null||n({...o,error:z(o)}),!1)}if(t.type==="GET_CONTEXT_LINK_INFO"){const o=String(t.url||"").trim();let c=Ee;if(o&&String((c==null?void 0:c.url)||"")!==o){let l=null;const s=document.links||[],d=Math.min(Number(s.length)||0,2e3);for(let u=0;u<d;u+=1){const m=s[u];if(String((m==null?void 0:m.href)||((a=m==null?void 0:m.getAttribute)==null?void 0:a.call(m,"href"))||"").trim()===o){l=m;break}}c=de(l||null)}return n==null||n({ok:!0,url:String((c==null?void 0:c.url)||""),title:String((c==null?void 0:c.title)||"")}),!1}if(t.type==="GET_CURRENT_MEDIA_CONTEXT")return n==null||n(At()),!1;if(t.type==="APPLY_MEDIA_RESUME"){const o=fe(t.seconds);return n==null||n({ok:o}),!1}return t.type==="UPDATE_BROWSER_MEDIA_REF_BADGE"&&(ne=!1,R(t.reference||null),n==null||n({ok:!0})),!1})}catch{}let h=null,g=null;function X(e){return new Promise((t,r)=>{const n=V();if(!(n!=null&&n.sendMessage)){r(new Error(i("extension_runtime_unavailable")));return}n.sendMessage(e,a=>{const o=chrome.runtime.lastError;if(o){r(new Error(o.message||i("extension_request_failed")));return}t(a||null)})})}async function Ne(){const e=await X({type:"LOAD_BROWSER_CAPTURE_META"});if(!(e!=null&&e.ok))throw new Error(String((e==null?void 0:e.error)||i("load_capture_meta_failed")));return e}async function Ae(e){const t=await X({type:"SUBMIT_BROWSER_CAPTURE",payload:e});if(!(t!=null&&t.ok))throw new Error(String((t==null?void 0:t.error)||i("failed_submit_capture")));return t}async function dt(){const e=await X({type:"CAPTURE_VISIBLE_TAB"});if(!(e!=null&&e.ok)||!(e!=null&&e.dataUrl))throw new Error(String((e==null?void 0:e.error)||i("failed_capture_tab")));return e.dataUrl}async function Be(e){let t={};try{const r=await chrome.storage.local.get(ce);t=(r==null?void 0:r[ce])||{}}catch{t={}}return it(t,e)}async function Le(e){try{await chrome.storage.local.set({[ce]:{noteTypeName:String((e==null?void 0:e.noteTypeName)||""),deckName:String((e==null?void 0:e.deckName)||""),priority:Number((e==null?void 0:e.priority)??K),tagsText:String((e==null?void 0:e.tagsText)||""),mappingsByNoteType:(e==null?void 0:e.mappingsByNoteType)||{}}})}catch{}}async function Me(e="",t=[]){const r=(g==null?void 0:g.meta)||await Ne();if(!Array.isArray(r==null?void 0:r.noteTypes)||r.noteTypes.length===0)throw new Error(i("no_note_types"));if(!Array.isArray(r==null?void 0:r.deckNames)||r.deckNames.length===0)throw new Error(i("no_decks"));const n=(g==null?void 0:g.form)||await Be(r);return g={mode:"snapshot",meta:r,form:n,context:{url:window.location.href||"",title:document.title||"",selectedText:Qe("snapshot",e,$())},snapshots:Array.isArray(t)?t:[],statusKind:"",statusText:"",submitting:!1},g}async function ut(e="",t=[]){const r=await Me(e,t),n=Se({...r.context,snapshots:r.snapshots.map(c=>({filename:c.filename,base64:c.base64}))},r.form),a=et(n);if(!a.ok)throw new Error(i("continue_choose_fields",{error:z(a)}));const o=await Ae(n);return await Le(r.form),o}function Ie(e){const t=e instanceof Element?e:(e==null?void 0:e.parentElement)||null;return t?t.closest("input, textarea, select")?!0:!!t.closest('[contenteditable=""], [contenteditable="true"]'):!1}function ue(){return!!h}function pt(e){return String((e==null?void 0:e.code)||"").toLowerCase()==="keyx"}function pe(e){var n;const t=h==null?void 0:h.shell,r=e==null?void 0:e.target;if(!(!t||!(r instanceof Node)||!t.contains(r))){if(e.type==="keydown"&&((n=h==null?void 0:h.handleTagAutocompleteKeyDown)!=null&&n.call(h,e))){e.stopPropagation();return}if(e.type==="keydown"&&e.key==="Escape"){e.preventDefault(),e.stopPropagation(),B();return}e.stopPropagation()}}function Q(){if(h)return h;const e=document.createElement("div");e.id=nt,e.style.all="initial";const t=e.attachShadow({mode:"open"});document.documentElement.appendChild(e),t.addEventListener("keydown",pe,!0),t.addEventListener("keypress",pe,!0),t.addEventListener("keyup",pe,!0);const r=document.createElement("style");r.textContent=`
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
    `,t.appendChild(r);const n=document.createElement("div");return n.className="shell",t.appendChild(n),h={host:e,shadow:t,shell:n},h}function B(){var e;(e=h==null?void 0:h.host)!=null&&e.isConnected&&h.host.remove(),h=null,g=null}function Fe(){const e=Q();e.handleTagAutocompleteKeyDown=null,e.shell.textContent=""}function mt(e,t,r){const n=document.createElement("div");n.className="tag-autocomplete";const a=document.createElement("input");a.id="incremento-browser-capture-tags",a.type="text",a.value=String(e||""),a.placeholder="tag-one tag-two",a.autocomplete="off",a.spellcheck=!1,a.setAttribute("role","combobox"),a.setAttribute("aria-autocomplete","list");const o=document.createElement("div");o.id="incremento-browser-capture-tag-suggestions",o.className="tag-suggestions",o.setAttribute("role","listbox"),o.hidden=!0,a.setAttribute("aria-controls",o.id),a.setAttribute("aria-expanded","false");const c=$t(t);let l=!1,s=0,d=[];const u=()=>{var y;Array.from(o.children).forEach((b,_)=>{b.classList.toggle("is-active",_===s),b.setAttribute("aria-selected",_===s?"true":"false")}),!o.hidden&&d.length>0?(a.setAttribute("aria-activedescendant",`${o.id}-${s}`),(y=o.children[s])==null||y.scrollIntoView({block:"nearest"})):a.removeAttribute("aria-activedescendant")},m=()=>{const y=a.selectionStart??a.value.length;if(d=Ht(c,a.value,y),s=d.length>0?Math.min(s,d.length-1):0,o.textContent="",o.hidden=!l||d.length===0,a.setAttribute("aria-expanded",o.hidden?"false":"true"),o.hidden){u();return}d.forEach((b,_)=>{const p=document.createElement("button");p.id=`${o.id}-${_}`,p.type="button",p.setAttribute("role","option"),p.setAttribute("aria-selected",_===s?"true":"false"),p.className=_===s?"is-active":"",p.textContent=b,p.addEventListener("mouseenter",()=>{s=_,u()}),p.addEventListener("mousedown",E=>{E.preventDefault(),T(b)}),o.appendChild(p)}),u()},T=y=>{const b=Vt(a.value,y,a.selectionStart??a.value.length,a.selectionEnd??a.value.length);a.value=b.value,r(b.value),l=!1,s=0,a.focus(),a.setSelectionRange(b.cursor,b.cursor),m()},L=y=>{if(y.target!==a)return!1;if(y.key==="Escape"&&l)return y.preventDefault(),l=!1,m(),!0;if(!d.length)return!1;if(y.key==="ArrowDown"||y.key==="ArrowUp"){y.preventDefault();const b=y.key==="ArrowDown"?1:-1;if(!l)l=!0,s=b>0?0:d.length-1;else return s=(s+b+d.length)%d.length,u(),!0;return m(),!0}return l&&(y.key==="Enter"||y.key==="Tab")?(y.preventDefault(),T(d[s]),!0):!1};return a.addEventListener("input",()=>{r(a.value),s=0,l=!0,m()}),a.addEventListener("focus",()=>{l=!0,m()}),a.addEventListener("click",()=>{s=0,l=!0,m()}),a.addEventListener("select",m),a.addEventListener("blur",()=>{l=!1,m()}),n.appendChild(a),n.appendChild(o),{element:n,handleKeyDown:L}}function ft(e,t){const r=document.createElement("div");r.className="snapshots";for(const n of t){const a=document.createElement("div");a.className="snapshot-card";const o=document.createElement("img");o.src=n.dataUrl,o.alt=n.filename,a.appendChild(o);const c=document.createElement("div");c.className="snapshot-footer";const l=document.createElement("span");l.textContent=n.filename,c.appendChild(l);const s=document.createElement("button");s.type="button",s.textContent=i("remove"),s.addEventListener("click",()=>{g.snapshots=g.snapshots.filter(d=>d.id!==n.id),D()}),c.appendChild(s),a.appendChild(c),r.appendChild(a)}return r}async function D(){var Ge;const e=Q(),{shell:t,shadow:r}=e;e.refreshLanguage=()=>{D()};const n=g;Fe();const a=document.createElement("div");a.className="backdrop",a.addEventListener("click",()=>B()),t.appendChild(a);const o=document.createElement("section");o.className="panel",t.appendChild(o);const c=document.createElement("p");c.className="eyebrow",c.textContent=n.mode==="snapshot"?i("browser_snapshot"):i("browser_selection"),o.appendChild(c);const l=document.createElement("h2");l.textContent=i("send_capture_anki"),o.appendChild(l);const s=document.createElement("p");s.className="lead",s.textContent=n.mode==="snapshot"?_e("snapshots_ready",n.snapshots.length,{url:n.context.url}):i("selected_text_from",{url:n.context.url}),o.appendChild(s);const d=document.createElement("form");d.noValidate=!0;const u=document.createElement("div");u.className="grid",d.appendChild(u);const m=(f,x,S=!1,w="")=>{const F=document.createElement("div");F.className=`field${S?" full":""}`;const Je=document.createElement("label");if(Je.textContent=f,F.appendChild(Je),F.appendChild(x),w){const ye=document.createElement("p");ye.className="field-note",ye.textContent=w,F.appendChild(ye)}return F},T=document.createElement("select");for(const f of n.meta.noteTypes){const x=document.createElement("option");x.value=f.name,x.textContent=f.name,T.appendChild(x)}T.value=n.form.noteTypeName,T.addEventListener("change",()=>{var S;const f=n.meta.noteTypes.find(w=>w.name===T.value),x=ve((S=n.form.mappingsByNoteType)==null?void 0:S[T.value],(f==null?void 0:f.fields)||[]);n.form=H(n.form,T.value,x),D()}),u.appendChild(m(i("note_type"),T));const L=document.createElement("select");for(const f of n.meta.deckNames){const x=document.createElement("option");x.value=f,x.textContent=f,L.appendChild(x)}L.value=n.form.deckName,L.addEventListener("change",()=>{n.form.deckName=L.value}),u.appendChild(m(i("deck"),L));const y=mt(n.form.tagsText,n.meta.tagNames,f=>{n.form.tagsText=f});h.handleTagAutocompleteKeyDown=y.handleKeyDown,u.appendChild(m(i("tags"),y.element,!0,i("tag_hint")));const b=document.createElement("div");b.style.display="grid",b.style.gridTemplateColumns="1fr auto",b.style.gap="10px",b.style.alignItems="center";const _=document.createElement("input");_.type="range",_.min="0",_.max="100",_.step="0.1",_.value=String(n.form.priority??K);const p=document.createElement("input");p.type="number",p.min="0",p.max="100",p.step="0.1",p.style.width="92px",p.value=String(n.form.priority??K);const E=f=>{const x=Number(f),S=Number.isFinite(x)?Math.min(100,Math.max(0,x)):K;n.form.priority=Number(S.toFixed(4)),_.value=String(n.form.priority),p.value=String(n.form.priority)};_.addEventListener("input",()=>E(_.value)),p.addEventListener("change",()=>E(p.value)),b.appendChild(_),b.appendChild(p),u.appendChild(m(i("priority"),b));const k=["",...((Ge=n.meta.noteTypes.find(f=>f.name===n.form.noteTypeName))==null?void 0:Ge.fields)||[]],N=(f,x)=>{const S=document.createElement("select");for(const w of k){const F=document.createElement("option");F.value=w,F.textContent=w||i("do_not_insert"),S.appendChild(F)}return S.value=k.includes(f)?f:"",S.addEventListener("change",()=>{x(S.value)}),S},U=!!n.context.selectedText;u.appendChild(m(i("page_title_field"),N(n.form.fieldMappings.titleField,f=>{n.form=H(n.form,n.form.noteTypeName,{...n.form.fieldMappings,titleField:f})}),!1,i("page_title_field_note"))),u.appendChild(m(i("selected_text_field"),N(n.form.fieldMappings.selectedTextField,f=>{n.form=H(n.form,n.form.noteTypeName,{...n.form.fieldMappings,selectedTextField:f})}),!1,U?i("chars_ready",{count:n.context.selectedText.length}):i("no_text_added"))),u.appendChild(m(i("source_url_field"),N(n.form.fieldMappings.urlField,f=>{n.form=H(n.form,n.form.noteTypeName,{...n.form.fieldMappings,urlField:f})}),!1,i("source_url_note"))),u.appendChild(m(i("snapshot_field"),N(n.form.fieldMappings.snapshotField,f=>{n.form=H(n.form,n.form.noteTypeName,{...n.form.fieldMappings,snapshotField:f})}),!0,n.snapshots.length>0?_e("snapshots_selected",n.snapshots.length):i("no_snapshots")));const A=document.createElement("textarea");if(A.value=n.context.selectedText,A.placeholder=n.mode==="snapshot"?i("add_text_snapshots"):i("selected_text_edit"),A.addEventListener("input",()=>{n.context.selectedText=A.value}),u.appendChild(m(n.mode==="snapshot"?i("text_to_add"):i("selected_text"),A,!0,i("inserted_text_note"))),n.snapshots.length>0){const f=document.createElement("div");f.className="field full";const x=document.createElement("label");x.textContent=i("snapshots"),f.appendChild(x),f.appendChild(ft(r,n.snapshots)),u.appendChild(f)}const M=document.createElement("p");M.className=`status${n.statusKind?` ${n.statusKind}`:""}`,M.textContent=n.statusValidation?z(n.statusValidation):n.statusCode?i(n.statusCode):n.statusText,d.appendChild(M);const j=document.createElement("div");if(j.className="actions",n.snapshots.length>0){const f=document.createElement("button");f.type="button",f.className="ghost-btn",f.textContent=i("capture_more"),f.addEventListener("click",()=>Z(n.snapshots)),j.appendChild(f)}const q=document.createElement("button");q.type="button",q.className="secondary-btn",q.textContent=i("language_cancel"),q.addEventListener("click",()=>B()),j.appendChild(q);const G=document.createElement("button");G.type="submit",G.className="primary-btn",G.textContent=n.submitting?i("saving"):i("create_note"),G.disabled=!!n.submitting,j.appendChild(G),d.appendChild(j),d.addEventListener("submit",async f=>{if(f.preventDefault(),n.submitting)return;const x=Se({...n.context,snapshots:n.snapshots.map(w=>({filename:w.filename,base64:w.base64}))},n.form),S=et(x);if(!S.ok){n.statusKind="error",n.statusCode="",n.statusValidation=S,n.statusText=z(S),D();return}n.submitting=!0,n.statusKind="",n.statusValidation=null,n.statusCode="creating_note",n.statusText=i("creating_note"),D();try{const w=await Ae(x);await Le(n.form),C(i("created_note",{type:w.noteTypeName,deck:w.deckName})),B()}catch(w){n.submitting=!1,n.statusKind="error",n.statusValidation=null,n.statusCode="",n.statusText=(w==null?void 0:w.message)||i("create_note_failed"),D()}}),o.appendChild(d)}function gt(e){return new Promise((t,r)=>{const n=new Image;n.onload=()=>t(n),n.onerror=()=>r(new Error(i("failed_decode_screenshot"))),n.src=e})}async function ht(e,t){const r=await gt(e),n=r.width/window.innerWidth,a=r.height/window.innerHeight,o=Math.max(0,Math.round(t.x*n)),c=Math.max(0,Math.round(t.y*a)),l=Math.max(1,Math.round(t.width*n)),s=Math.max(1,Math.round(t.height*a)),d=document.createElement("canvas");return d.width=l,d.height=s,d.getContext("2d").drawImage(r,o,c,l,s,0,0,l,s),d.toDataURL("image/png")}function bt(e){const t=String(e||""),r=t.indexOf(",");return r>=0?t.slice(r+1):t}function me(e){const t=Math.abs(e.width),r=Math.abs(e.height);return{x:e.width>=0?e.x:e.x-t,y:e.height>=0?e.y:e.y-r,width:t,height:r}}function Pe(e=2){return new Promise(t=>{const r=Math.max(1,Number(e)||1);let n=0;const a=()=>{if(n+=1,n>=r){t();return}requestAnimationFrame(a)};requestAnimationFrame(a)})}function yt(e,t){if(!(e instanceof Element))return!1;const r=window.getComputedStyle(e),n=t==="x"?r.overflowX:r.overflowY;return/(auto|scroll|overlay)/.test(String(n||""))?t==="x"?e.scrollWidth>e.clientWidth:e.scrollHeight>e.clientHeight:!1}function De(e,t){let r=e instanceof Element?e:null;for(;r;){if(yt(r,t))return r;r=r.parentElement}const n=document.scrollingElement;return n instanceof Element?n:document.documentElement}function xt(e,t){var d;if(!e)return;const r=((d=t==null?void 0:t.style)==null?void 0:d.pointerEvents)||"";t!=null&&t.style&&(t.style.pointerEvents="none");let n=null;try{n=document.elementFromPoint(e.clientX,e.clientY)}finally{t!=null&&t.style&&(t.style.pointerEvents=r)}const a=Number(e.deltaX)||0,o=Number(e.deltaY)||0,c=a?De(n,"x"):null,l=o?De(n,"y"):null,s=document.scrollingElement instanceof Element?document.scrollingElement:document.documentElement;a&&(c||s).scrollBy({left:a,top:0,behavior:"auto"}),o&&(l||s).scrollBy({left:0,top:o,behavior:"auto"})}async function _t(e,t=[]){if(t.length>=ie)throw new Error(i("too_many_snapshots",{count:ie}));const r=Q();r.shell.style.display="none";try{await Pe(2);const n=await dt(),a=tt(n,{maxBytes:Rt});if(!a.ok)throw new Error(z(a));const o=me(e),c=await ht(n,o),l=tt(c,{maxBytes:Kt});if(!l.ok)throw new Error(z(l));return{id:`${Date.now()}-${t.length}-${Math.random().toString(16).slice(2,8)}`,filename:`browser-capture-${t.length+1}.png`,dataUrl:c,base64:bt(c)}}catch(n){throw new Error((n==null?void 0:n.message)||i("failed_capture_tab"))}finally{h!=null&&h.shell&&(h.shell.style.display="",await Pe(1))}}function Z(e=[]){var _;const t=Q();Fe();const r=e.length>0&&((_=g==null?void 0:g.context)==null?void 0:_.selectedText)||"";g={mode:"snapshot",meta:(g==null?void 0:g.meta)||null,form:(g==null?void 0:g.form)||null,context:{url:window.location.href||"",title:document.title||"",selectedText:r},snapshots:[...e],statusKind:"",statusText:"",submitting:!1};const n=t.shell,a=document.createElement("div");a.className="capture-shell",n.appendChild(a);const o=document.createElement("div");o.className="capture-toolbar";const c=p=>{o.replaceChildren();const E=document.createElement("strong");E.textContent=i("snapshot_mode"),o.appendChild(E);const v=document.createElement("span");v.textContent=i(p),o.appendChild(v);const k=document.createElement("span");k.className="spacer",o.appendChild(k)};c("snapshot_mode_intro"),n.appendChild(o);const l=[...e];let s=null,d=null,u=!1;const m=()=>{c("snapshot_mode_hint");const p=document.createElement("span");p.textContent=u?i("capturing"):_e("snapshot_ready",l.length),o.appendChild(p);const E=document.createElement("button");E.type="button",E.className="toolbar-btn",E.textContent=i("undo"),E.disabled=u||l.length===0,E.addEventListener("click",()=>{l.pop(),m()}),o.appendChild(E);const v=document.createElement("button");v.type="button",v.className="toolbar-btn",v.textContent=i("clear"),v.disabled=u||l.length===0,v.addEventListener("click",()=>{l.splice(0,l.length),m()}),o.appendChild(v);const k=document.createElement("button");k.type="button",k.className="toolbar-btn",k.textContent=i("language_cancel"),k.addEventListener("click",()=>B()),o.appendChild(k);const N=document.createElement("button");N.type="button",N.className="toolbar-btn",N.textContent=i("extract_now"),N.disabled=u||l.length===0,N.addEventListener("click",async()=>{var A;if(!u){if(!l.length){C(i("draw_region_first"));return}u=!0,m();try{const M=await ut(((A=g==null?void 0:g.context)==null?void 0:A.selectedText)||"",[...l]);C(i("created_note",{type:M.noteTypeName,deck:M.deckName})),B()}catch(M){u=!1,m(),C((M==null?void 0:M.message)||i("create_note_failed"))}}}),o.appendChild(N);const U=document.createElement("button");U.type="button",U.className="toolbar-btn primary",U.textContent=i("continue"),U.addEventListener("click",()=>{var A;if(!u){if(!l.length){C(i("draw_region_first"));return}ee({mode:"snapshot",selectedText:((A=g==null?void 0:g.context)==null?void 0:A.selectedText)||"",snapshots:[...l]})}}),o.appendChild(U)};t.refreshLanguage=m;const T=(p,E)=>{if(l.length>=ie){C(i("too_many_snapshots",{count:ie}));return}d={x:p,y:E,width:0,height:0},s=document.createElement("div"),s.className="selection-rect",s.dataset.label=i("capture_label",{count:l.length+1}),a.appendChild(s)},L=()=>{if(!s||!d)return;const p=me(d);Object.assign(s.style,{left:`${p.x}px`,top:`${p.y}px`,width:`${p.width}px`,height:`${p.height}px`})};a.addEventListener("pointerdown",p=>{u||p.button!==0||p.target!==a||(p.preventDefault(),T(p.clientX,p.clientY),L())}),a.addEventListener("pointermove",p=>{d&&(p.preventDefault(),d.width=p.clientX-d.x,d.height=p.clientY-d.y,L())});const y=p=>{d||u||(p.preventDefault(),xt(p,t.host))};a.addEventListener("wheel",y,{passive:!1}),o.addEventListener("wheel",y,{passive:!1});const b=async()=>{if(!s||!d)return;const p=me(d),E=s;if(p.width>=24&&p.height>=24){u=!0,m();try{const v=await _t(p,l);l.push(v)}catch(v){C((v==null?void 0:v.message)||i("failed_capture_tab"))}}else E.remove();E.remove(),s=null,d=null,u=!1,m()};a.addEventListener("pointerup",()=>{b()}),a.addEventListener("pointercancel",()=>{b()}),m()}async function ee({mode:e,selectedText:t="",snapshots:r=[]}){if(e==="snapshot")await Me(t,r);else{const n=(g==null?void 0:g.meta)||await Ne();if(!Array.isArray(n==null?void 0:n.noteTypes)||n.noteTypes.length===0)throw new Error(i("no_note_types"));if(!Array.isArray(n==null?void 0:n.deckNames)||n.deckNames.length===0)throw new Error(i("no_decks"));const a=(g==null?void 0:g.form)||await Be(n);g={mode:e,meta:n,form:a,context:{url:window.location.href||"",title:document.title||"",selectedText:Qe(e,t,$())},snapshots:Array.isArray(r)?r:[],statusKind:"",statusText:"",submitting:!1}}await D()}globalThis.__incrementoTriggerBrowserCapture=e=>{if(String(e||"").trim().toLowerCase()==="snapshot")return Z(),{ok:!0};const r=$();return r?(ee({mode:"selection",selectedText:r,snapshots:[]}).catch(n=>{C((n==null?void 0:n.message)||i("open_capture_failed")),B()}),{ok:!0}):(C(i("select_page_text")),{ok:!1,error:i("select_page_text")})},document.addEventListener("keydown",e=>{if(!e.altKey||!pt(e)||ue()||Ie(e.target))return;if(e.metaKey){e.preventDefault(),e.stopPropagation(),Z();return}if(e.ctrlKey||e.shiftKey)return;const t=$();t&&(e.preventDefault(),e.stopPropagation(),ee({mode:"selection",selectedText:t,snapshots:[]}).catch(r=>{C((r==null?void 0:r.message)||i("open_capture_failed")),B()}))},!0),document.addEventListener("contextmenu",e=>{const t=Ce(e.target);Ee=de(t)},!0),document.addEventListener("click",e=>{if(!W.modifierClickEnabled||e.defaultPrevented||Number(e.button)!==0||ue()||Ie(e.target))return;const t=Ce(e.target);if(!t||!Ut(e,W))return;const r=de(t);if(!r)return;W.navigateAfterSave||e.preventDefault();const n=V();n==null||n.sendMessage({type:"SAVE_CLICKED_LINK_AS_WEBPAGE",url:r.url,title:r.title,sourcePageUrl:window.location.href||"",sourcePageTitle:document.title||""},a=>{var o;(o=chrome==null?void 0:chrome.runtime)==null||o.lastError})},!0),document.addEventListener("selectionchange",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("mouseup",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keyup",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keydown",e=>{e.key==="Escape"&&ue()&&(e.preventDefault(),e.stopPropagation(),B())},!0);function Et(e){try{const t=new URL(e),r=t.searchParams.get("v");if(r)return r;const n=t.pathname.split("/").filter(Boolean);if(t.hostname==="youtu.be"&&n[0])return n[0];if((n[0]==="shorts"||n[0]==="live"||n[0]==="embed")&&n[1])return n[1]}catch{}return""}function wt(e){const t=String(e||"").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);return t?t[1]:""}function Tt(){const e=window.location.href||"",t=window.location.hostname||"";return t.includes("youtube.com")||t==="youtu.be"?{provider:"youtube",videoId:Et(e)}:t.includes("vimeo.com")?{provider:"vimeo",videoId:wt(e)}:{provider:"",videoId:""}}function Oe(e){try{const r=new URL(e).searchParams.get("inc_card_id")||"",n=Number(r);if(Number.isFinite(n)&&n>0)return Math.floor(n)}catch{}return 0}function vt(e){const t=String(e||"").replace(/^#/,"").trim();if(!t)return"";const n=t.indexOf("__incremento_resume__=1");return n<0?t:t.slice(0,n).replace(/[&?]+$/,"")}function St(e){try{const t=new URL(e);t.searchParams.delete("inc_card_id"),t.searchParams.delete("inc_track_web"),t.searchParams.delete("inc_resume_sec"),t.searchParams.delete("inc_resume_media");const r=vt(t.hash);return t.hash=r?`#${r}`:"",t.toString()}catch{return String(e||"")}}function Ct(e){try{const t=new URL(e),r=String(t.searchParams.get("inc_track_web")||"").trim().toLowerCase();return r==="1"||r==="true"||r==="yes"||r==="on"}catch{return!1}}function kt(){if(window.top!==window)return;const e=window.location.href||"";if(!e||!/inc_(card_id|track_web|resume_sec|resume_media)|__incremento_resume__=1/.test(e))return;const t=St(e);if(!(!t||t===e))try{history.replaceState(history.state,document.title||"",t),be=t}catch{}}function Ue(){const e=Array.from(document.querySelectorAll("video"));return e.length===0?null:(e.sort((t,r)=>{const n=(t.videoWidth||0)*(t.videoHeight||0);return(r.videoWidth||0)*(r.videoHeight||0)-n}),e[0])}function fe(e,t=12){const r=Math.max(0,Math.floor(Number(e)||0));if(r<=0)return!1;const n=Ue();if(!n)return t>0&&window.setTimeout(()=>fe(r,t-1),500),!1;try{return n.currentTime=r,C(i("resumed_to",{seconds:r})),!0}catch{return t>0&&window.setTimeout(()=>fe(r,t-1),500),!1}}function te(){var c,l;const e=window.location.href||"",{provider:t,videoId:r}=Tt(),n=Ue(),a=t?e:String((n==null?void 0:n.currentSrc)||(n==null?void 0:n.src)||"").trim(),o=String(((c=n==null?void 0:n.getAttribute)==null?void 0:c.call(n,"title"))||((l=n==null?void 0:n.getAttribute)==null?void 0:l.call(n,"aria-label"))||document.title||"").trim();return{provider:t,videoId:r,video:n,mediaUrl:a,mediaTitle:o}}function Nt(){const{provider:e,video:t}=te();let r=-1,n=!1;if(t&&(r=Math.max(0,Math.floor(Number(t.currentTime)||0)),n=!0),e==="youtube"&&r<=0){const a=he();a>=0&&(r=a,n=!0)}if(e==="vimeo"&&r<=0){const a=ge();a>=0&&(r=a,n=!0)}return{found:n,seconds:n?Math.max(0,r):0}}function At(){const e=window.location.href||"",{provider:t,videoId:r,mediaUrl:n,mediaTitle:a}=te(),o=Nt();return{ok:!0,pageUrl:e,pageTitle:document.title||"",provider:t,videoId:r,mediaUrl:n,mediaTitle:a,hasDetectedTime:!!o.found,seconds:Math.max(0,Math.floor(Number(o.seconds)||0)),timeText:o.found?ke(o.seconds):""}}function We(e){const t=String(e||"").trim();if(!t)return-1;const r=t.split(":").map(n=>n.trim());return r.every(n=>/^\d+$/.test(n))?r.length===2?Number(r[0])*60+Number(r[1]):r.length===3?Number(r[0])*3600+Number(r[1])*60+Number(r[2]):-1:-1}function ge(){const e=Array.from(document.querySelectorAll('[data-progress-bar-timecode="true"], [class*="Timecode_module_timecode__"]'));for(const t of e){const r=String((t==null?void 0:t.textContent)||"").trim(),n=We(r);if(n>=0)return n}return-1}function he(){const e=Array.from(document.querySelectorAll(".ytp-time-current, [class*='ytp-time-current']"));for(const t of e){const r=String((t==null?void 0:t.textContent)||"").trim(),n=We(r);if(n>=0)return n}return-1}async function ze(){try{const e=await X({type:"GET_LINKED_CARD_CONTEXT",url:window.location.href||""});if(!(e!=null&&e.linked)||Number(e.cardId)<=0){R(null);return}const t=await X({type:"LOAD_BROWSER_MEDIA_REF"});if(!(t!=null&&t.ok)||!(t!=null&&t.hasReference)){R(null);return}R(t)}catch{R(null)}}let Re=-1,Ke=0,$e=-1,He=0,ne=!1,Y=!0,re=null,be=window.location.href||"";function ae(){Y=!1,re!==null&&(clearInterval(re),re=null)}function Ve(e){if(!Y)return!1;try{const t=V();return t!=null&&t.id?(t.sendMessage(e,()=>{try{const r=t==null?void 0:t.lastError;r&&/context invalidated/i.test(String(r.message||""))&&ae()}catch{ae()}}),!0):(ae(),!1)}catch{return ae(),!1}}function Xe(){if(!Y){P(!1);return}try{const e=V();if(!(e!=null&&e.id)){P(!1);return}e.sendMessage({type:"GET_TRACKING_STATUS",url:window.location.href||""},t=>{try{if(e==null?void 0:e.lastError){P(!1);return}}catch{P(!1);return}P(!!(t!=null&&t.tracked),String((t==null?void 0:t.mode)||""))})}catch{P(!1)}}function I(e=!1,t=!1){if(!Y)return;const{provider:r,videoId:n,video:a}=te();if(!r)return;let o=-1;if(a&&(o=Math.max(0,Math.floor(Number(a.currentTime)||0))),r==="youtube"&&o<=0){const l=he();l>=0&&(o=l)}if(r==="vimeo"&&o<=0){const l=ge();l>=0&&(o=l)}if(o<0)return;const c=Date.now();!e&&o===Re&&c-Ke<4e3||(Re=o,Ke=c,Ve({type:"heartbeat",provider:r,videoId:n,cardId:Oe(window.location.href||""),flush:!!t,seconds:o,url:window.location.href||"",title:document.title||""}))}function O(e=!1,t=!1){if(!Y)return;const r=window.location.href||"",{provider:n,videoId:a,video:o,mediaUrl:c,mediaTitle:l}=te();if(!o&&!n)return;let s=-1;if(o&&(s=Math.max(0,Math.floor(Number(o.currentTime)||0))),n==="youtube"&&s<=0){const u=he();u>=0&&(s=u)}if(n==="vimeo"&&s<=0){const u=ge();u>=0&&(s=u)}if(s<0)return;const d=Date.now();!e&&s===$e&&d-He<4e3||($e=s,He=d,Ve({type:"web_media_heartbeat",provider:n,videoId:a,cardId:Oe(r),trackEnabled:Ct(r),flush:!!t,seconds:s,url:r,mediaUrl:c,mediaTitle:l,title:document.title||""}))}re=window.setInterval(()=>{I(!1,!1),O(!1,!1)},1e3),window.setInterval(()=>{const e=window.location.href||"";e!==be&&(be=e,ne=!1,Xe(),ze())},750),window.addEventListener("pagehide",()=>{I(!0,!0),O(!0,!0)},{capture:!0}),window.addEventListener("beforeunload",()=>{I(!0,!0),O(!0,!0)},{capture:!0}),document.addEventListener("visibilitychange",()=>{document.visibilityState==="hidden"&&(I(!0,!0),O(!0,!0))}),document.addEventListener("timeupdate",()=>{I(!1,!1),O(!1,!1)},!0),document.addEventListener("play",()=>{I(!0,!1),O(!0,!1)},!0),document.addEventListener("pause",()=>{I(!0,!0),O(!0,!0)},!0),document.addEventListener("ended",()=>I(!0,!0),!0),window.setTimeout(()=>I(!0,!1),1200),window.setTimeout(kt,1200),window.setTimeout(Xe,300),window.setTimeout(()=>{ze()},320),window.__incrementoContentScriptState={...window.__incrementoContentScriptState||{},version:J,ready:!0}})();
