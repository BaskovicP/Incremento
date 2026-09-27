import{$ as It,a1 as Ft,a0 as Pt,am as Dt,t as i,L as ae,D as Ot,B as xe,ak as Ut,ai as Wt,aj as zt,an as Ze,ao as Rt,a4 as _e,ap as ie,f as Kt,ad as et,aq as $t,a8 as tt,af as nt,ah as Vt,ar as Ht,as as rt,n as Xt,g as qt,a as Yt}from"./assets/extension-shared.js";import"./assets/extension-vendor.js";(()=>{var Ye,je,Ge;const J="browser-capture-v10",ot="incremento-browser-capture-root",le=window.__incrementoContentScriptState&&typeof window.__incrementoContentScriptState=="object"?window.__incrementoContentScriptState:{};if(le.version===J&&le.ready)return;window.__incrementoContentScriptState={...le,version:J,ready:!1},window.__incrementoContentScriptVersion=J;const ce="incremento_browser_capture_settings",K=50,at=0,it=100;let W=Ot,Ee=null,se=null,we="";const z=e=>{if(!(e!=null&&e.errorCode))return String((e==null?void 0:e.error)||"");const t={...e.errorParams};return t.count!=null&&(t.count=Kt(t.count)),i(e.errorCode,t,e.error)};globalThis.__incrementoLastSelectedText=String(globalThis.__incrementoLastSelectedText||"").trim();function $(){var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();return e?(globalThis.__incrementoLastSelectedText=e,e):String(globalThis.__incrementoLastSelectedText||"").trim()}function Te(e){const t=Number(e);return Number.isFinite(t)?Math.min(it,Math.max(at,Number(t.toFixed(4)))):K}function lt(e){return Array.from(new Set(String(e||"").replaceAll(","," ").split(/\s+/).map(t=>t.trim()).filter(Boolean)))}function ve(e,t){const r=Array.isArray(t)?t.filter(Boolean):[],n=r[0]||"",o=a=>a===""?"":r.includes(a)?a:n;return{titleField:o(String((e==null?void 0:e.titleField)||"")),selectedTextField:o(String((e==null?void 0:e.selectedTextField)||"")),urlField:o(String((e==null?void 0:e.urlField)||"")),snapshotField:o(String((e==null?void 0:e.snapshotField)||""))}}function ct(e,t){const r=Array.isArray(t==null?void 0:t.noteTypes)?t.noteTypes:[],n=Array.isArray(t==null?void 0:t.deckNames)?t.deckNames.filter(Boolean):[],o=String((e==null?void 0:e.noteTypeName)||""),a=r.find(_=>(_==null?void 0:_.name)===o)||r[0]||null,s=(a==null?void 0:a.name)||"",l=Array.isArray(a==null?void 0:a.fields)?a.fields:[],c=e!=null&&e.mappingsByNoteType&&typeof e.mappingsByNoteType=="object"?e.mappingsByNoteType:{},d=ve(c[s],l),u=String((e==null?void 0:e.deckName)||""),m=n.includes(u)?u:n[0]||"Default";return{noteTypeName:s,deckName:m,priority:Te(e==null?void 0:e.priority),tagsText:String((e==null?void 0:e.tagsText)||""),fieldMappings:d,mappingsByNoteType:c}}function V(e,t,r){return{...e,noteTypeName:t,fieldMappings:{...r},mappingsByNoteType:{...(e==null?void 0:e.mappingsByNoteType)||{},[t]:{...r}}}}function Se(e,t){var r,n,o,a;return{url:String((e==null?void 0:e.url)||"").trim(),title:String((e==null?void 0:e.title)||"").trim()||String((e==null?void 0:e.url)||"").trim()||"Untitled",selectedText:String((e==null?void 0:e.selectedText)||"").trim(),noteTypeName:String((t==null?void 0:t.noteTypeName)||"").trim(),deckName:String((t==null?void 0:t.deckName)||"").trim(),tags:lt(t==null?void 0:t.tagsText),priority:Te(t==null?void 0:t.priority),fieldMappings:{titleField:String(((r=t==null?void 0:t.fieldMappings)==null?void 0:r.titleField)||"").trim(),selectedTextField:String(((n=t==null?void 0:t.fieldMappings)==null?void 0:n.selectedTextField)||"").trim(),urlField:String(((o=t==null?void 0:t.fieldMappings)==null?void 0:o.urlField)||"").trim(),snapshotField:String(((a=t==null?void 0:t.fieldMappings)==null?void 0:a.snapshotField)||"").trim()},snapshots:Array.isArray(e==null?void 0:e.snapshots)?e.snapshots.map((s,l)=>({mimeType:"image/png",filename:String((s==null?void 0:s.filename)||`browser-capture-${l+1}.png`),base64:String((s==null?void 0:s.base64)||"").trim()})).filter(s=>s.base64):[]}}function k(e){const t=document.getElementById("incremento-video-time-toast");t&&t.remove();const r=document.createElement("div");r.id="incremento-video-time-toast",r.textContent=String(e||""),Object.assign(r.style,{position:"fixed",zIndex:2147483647,top:"10px",right:"10px",maxWidth:"320px",padding:"10px 14px",background:"rgba(0, 0, 0, 0.86)",color:"#fff",fontSize:"13px",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"6px",boxShadow:"0 2px 8px rgba(0, 0, 0, 0.4)",opacity:"0",transition:"opacity 0.2s ease"}),document.documentElement.appendChild(r),requestAnimationFrame(()=>{r.style.opacity="1"}),setTimeout(()=>{r.style.opacity="0",setTimeout(()=>r.remove(),220)},2400)}async function st(){try{const e=await chrome.storage.local.get(ae);W=xe(e==null?void 0:e[ae])}catch{W=xe(null)}}function Ce(e){var o,a;const t=e instanceof Element?e:(e==null?void 0:e.parentElement)||null,r=(o=t==null?void 0:t.closest)==null?void 0:o.call(t,"a[href]");if(!r)return null;const n=String(r.href||((a=r.getAttribute)==null?void 0:a.call(r,"href"))||"").trim();return et(n)?r:null}function de(e){var o,a,s,l,c,d,u,m,_,T,f,b;if(!e)return null;const t=String(e.href||((o=e.getAttribute)==null?void 0:o.call(e,"href"))||"").trim();if(!et(t))return null;const n=[...dt(e,t),(a=e.getAttribute)==null?void 0:a.call(e,"aria-label"),(s=e.getAttribute)==null?void 0:s.call(e,"title"),(d=(c=(l=e.querySelector)==null?void 0:l.call(e,"img[alt]"))==null?void 0:c.getAttribute)==null?void 0:d.call(c,"alt"),(_=(m=(u=e.querySelector)==null?void 0:u.call(e,"[aria-label]"))==null?void 0:m.getAttribute)==null?void 0:_.call(m,"aria-label"),(b=(f=(T=e.querySelector)==null?void 0:T.call(e,"[title]"))==null?void 0:f.getAttribute)==null?void 0:b.call(f,"title"),e.textContent];return{url:t,title:$t(n,t)}}function ke(e,t){var r,n,o;t&&e.push((r=t.getAttribute)==null?void 0:r.call(t,"title"),(n=t.getAttribute)==null?void 0:n.call(t,"data-title-no-tooltip"),t.textContent,(o=t.getAttribute)==null?void 0:o.call(t,"aria-label"))}function dt(e,t){var s,l,c,d;const r=rt(t);if(!r)return[];const n=[],o=((s=e.closest)==null?void 0:s.call(e,["ytd-rich-item-renderer","ytd-video-renderer","ytd-grid-video-renderer","ytd-compact-video-renderer","ytd-playlist-video-renderer","ytd-playlist-panel-video-renderer","ytd-reel-item-renderer","yt-lockup-view-model","ytm-shorts-lockup-view-model","[data-video-id]"].join(", ")))||null,a=o?[o,document]:[document];for(const u of a){const m=u===document?document.links||[]:((l=u.querySelectorAll)==null?void 0:l.call(u,"a[href]"))||[],_=Math.min(Number(m.length)||0,u===document?2e3:200);for(let T=0;T<_;T+=1){const f=m[T];if(f===e)continue;const b=String((f==null?void 0:f.href)||((c=f==null?void 0:f.getAttribute)==null?void 0:c.call(f,"href"))||"").trim();rt(b)===r&&(ke(n,f),ke(n,(d=f.querySelector)==null?void 0:d.call(f,"#video-title, #video-title-link, [data-title-no-tooltip]")))}}return n}function ut(){let e=document.getElementById("incremento-tracking-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-tracking-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483646,top:"52px",right:"10px",display:"none",alignItems:"center",gap:"8px",padding:"8px 12px",background:"linear-gradient(135deg, rgba(10, 34, 64, 0.94), rgba(17, 83, 126, 0.94))",color:"#fff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",letterSpacing:"0.08em",textTransform:"uppercase",borderRadius:"999px",boxShadow:"0 4px 14px rgba(0, 0, 0, 0.28)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"none"});const t=document.createElement("span");t.textContent="●",Object.assign(t.style,{color:"#53f2a5",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(83, 242, 165, 0.85)"}),e.appendChild(t);const r=document.createElement("span");r.textContent="⚠",Object.assign(r.style,{color:"#ffd166",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(255, 209, 102, 0.55)"}),e.appendChild(r);const n=document.createElement("span");return n.id="incremento-tracking-badge-label",n.textContent=i("tracking"),e.appendChild(n),document.documentElement.appendChild(e),e}function P(e,t=""){we=e?t:"";const r=ut(),n=document.getElementById("incremento-tracking-badge-label");if(!(!r||!n)){if(!e){r.style.display="none";return}n.textContent=t==="web"?i("tracking_web_card"):i("tracking"),r.style.display="inline-flex"}}function Ae(e){const t=Math.max(0,Math.floor(Number(e)||0)),r=Math.floor(t/3600),n=Math.floor(t%3600/60),o=t%60;return r>0?`${r}:${String(n).padStart(2,"0")}:${String(o).padStart(2,"0")}`:`${n}:${String(o).padStart(2,"0")}`}function pt(){let e=document.getElementById("incremento-browser-media-ref-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-browser-media-ref-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483645,top:"96px",right:"10px",display:"none",alignItems:"center",gap:"8px",maxWidth:"320px",padding:"9px 12px",background:"linear-gradient(135deg, rgba(28, 32, 48, 0.96), rgba(34, 62, 96, 0.96))",color:"#eef5ff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"14px",boxShadow:"0 5px 18px rgba(0, 0, 0, 0.30)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"auto"});const t=document.createElement("span");t.textContent="▶",Object.assign(t.style,{color:"#8fd3ff",fontSize:"11px",lineHeight:"1"}),e.appendChild(t);const r=document.createElement("span");r.id="incremento-browser-media-ref-badge-label",r.textContent="",Object.assign(r.style,{flex:"1 1 auto",minWidth:"0"}),e.appendChild(r);const n=document.createElement("button");return n.type="button",n.textContent="×",n.setAttribute("aria-label",i("saved_time_badge_dismiss")),Object.assign(n.style,{appearance:"none",border:"0",background:"transparent",color:"#a9bfdc",cursor:"pointer",fontSize:"16px",fontWeight:"700",lineHeight:"1",padding:"0 0 0 4px",margin:"0",pointerEvents:"auto"}),n.addEventListener("click",o=>{o.preventDefault(),o.stopPropagation(),ne=!0,e.style.display="none"}),e.appendChild(n),document.documentElement.appendChild(e),e}function R(e){se=e;const t=pt(),r=document.getElementById("incremento-browser-media-ref-badge-label");if(!t||!r)return;if(!!!(e!=null&&e.hasReference)){t.style.display="none";return}if(ne)return;const o=String((e==null?void 0:e.timeText)||Ae(e==null?void 0:e.seconds));r.textContent=o?i("last_saved_time",{time:o}):i("last_saved"),t.style.display="inline-flex"}function H(){try{return(chrome==null?void 0:chrome.runtime)||null}catch{return null}}It(),Ft(),Pt(()=>{var r;const e=document.getElementById("incremento-tracking-badge");Dt(e,()=>P(!0,we)),se&&R(se);const t=document.querySelector("#incremento-browser-media-ref-badge button");t==null||t.setAttribute("aria-label",i("saved_time_badge_dismiss")),(r=y==null?void 0:y.refreshLanguage)==null||r.call(y)}),st();try{(je=(Ye=chrome==null?void 0:chrome.storage)==null?void 0:Ye.onChanged)==null||je.addListener((e,t)=>{var r;t!=="local"||!e||!Object.prototype.hasOwnProperty.call(e,ae)||(W=xe((r=e[ae])==null?void 0:r.newValue))})}catch{}try{const e=H();(Ge=e==null?void 0:e.onMessage)==null||Ge.addListener((t,r,n)=>{var o;if(!t||!t.type)return!1;if(t.type==="SHOW_TOAST")return k(t.text||""),n==null||n({ok:!0}),!1;if(t.type==="TRIGGER_BROWSER_CAPTURE"){if(String(t.mode||"").trim().toLowerCase()==="snapshot")return Z(),n==null||n({ok:!0}),!1;const s=$();return s?(ee({mode:"selection",selectedText:s,snapshots:[]}).then(()=>n==null?void 0:n({ok:!0}),l=>{k((l==null?void 0:l.message)||i("open_capture_failed")),L(),n==null||n({ok:!1,error:String((l==null?void 0:l.message)||"")})}),!0):(k(i("select_page_text")),n==null||n({ok:!1}),!1)}if(t.type==="GET_PAGE_CONTEXT"){const a=Ut(Wt,zt,{includeHtml:t.includeHtml!==!1,htmlScope:t.htmlScope});return a.ok?(n==null||n(a),!1):(n==null||n({...a,error:z(a)}),!1)}if(t.type==="GET_CONTEXT_LINK_INFO"){const a=String(t.url||"").trim();let s=Ee;if(a&&String((s==null?void 0:s.url)||"")!==a){let l=null;const c=document.links||[],d=Math.min(Number(c.length)||0,2e3);for(let u=0;u<d;u+=1){const m=c[u];if(String((m==null?void 0:m.href)||((o=m==null?void 0:m.getAttribute)==null?void 0:o.call(m,"href"))||"").trim()===a){l=m;break}}s=de(l||null)}return n==null||n({ok:!0,url:String((s==null?void 0:s.url)||""),title:String((s==null?void 0:s.title)||"")}),!1}if(t.type==="GET_CURRENT_MEDIA_CONTEXT")return n==null||n(Mt()),!1;if(t.type==="APPLY_MEDIA_RESUME"){const a=fe(t.seconds);return n==null||n({ok:a}),!1}return t.type==="UPDATE_BROWSER_MEDIA_REF_BADGE"&&(ne=!1,R(t.reference||null),n==null||n({ok:!0})),!1})}catch{}let y=null,h=null;function X(e){return new Promise((t,r)=>{const n=H();if(!(n!=null&&n.sendMessage)){r(new Error(i("extension_runtime_unavailable")));return}n.sendMessage(e,o=>{const a=chrome.runtime.lastError;if(a){r(new Error(a.message||i("extension_request_failed")));return}t(o||null)})})}async function Ne(){const e=await X({type:"LOAD_BROWSER_CAPTURE_META"});if(!(e!=null&&e.ok))throw new Error(String((e==null?void 0:e.error)||i("load_capture_meta_failed")));return e}async function Be(e){const t=await X({type:"SUBMIT_BROWSER_CAPTURE",payload:e});if(!(t!=null&&t.ok))throw new Error(String((t==null?void 0:t.error)||i("failed_submit_capture")));return t}async function mt(){const e=await X({type:"CAPTURE_VISIBLE_TAB"});if(!(e!=null&&e.ok)||!(e!=null&&e.dataUrl))throw new Error(String((e==null?void 0:e.error)||i("failed_capture_tab")));return e.dataUrl}async function Le(e){let t={};try{const r=await chrome.storage.local.get(ce);t=(r==null?void 0:r[ce])||{}}catch{t={}}return ct(t,e)}async function Me(e){try{await chrome.storage.local.set({[ce]:{noteTypeName:String((e==null?void 0:e.noteTypeName)||""),deckName:String((e==null?void 0:e.deckName)||""),priority:Number((e==null?void 0:e.priority)??K),tagsText:String((e==null?void 0:e.tagsText)||""),mappingsByNoteType:(e==null?void 0:e.mappingsByNoteType)||{}}})}catch{}}async function Ie(e="",t=[]){const r=(h==null?void 0:h.meta)||await Ne();if(!Array.isArray(r==null?void 0:r.noteTypes)||r.noteTypes.length===0)throw new Error(i("no_note_types"));if(!Array.isArray(r==null?void 0:r.deckNames)||r.deckNames.length===0)throw new Error(i("no_decks"));const n=(h==null?void 0:h.form)||await Le(r);return h={mode:"snapshot",meta:r,form:n,context:{url:window.location.href||"",title:document.title||"",selectedText:Ze("snapshot",e,$())},snapshots:Array.isArray(t)?t:[],statusKind:"",statusText:"",submitting:!1},h}async function ft(e="",t=[]){const r=await Ie(e,t),n=Se({...r.context,snapshots:r.snapshots.map(s=>({filename:s.filename,base64:s.base64}))},r.form),o=tt(n);if(!o.ok)throw new Error(i("continue_choose_fields",{error:z(o)}));const a=await Be(n);return await Me(r.form),a}function Fe(e){const t=e instanceof Element?e:(e==null?void 0:e.parentElement)||null;return t?t.closest("input, textarea, select")?!0:!!t.closest('[contenteditable=""], [contenteditable="true"]'):!1}function ue(){return!!y}function gt(e){return String((e==null?void 0:e.code)||"").toLowerCase()==="keyx"}function pe(e){var n;const t=y==null?void 0:y.shell,r=e==null?void 0:e.target;if(!(!t||!(r instanceof Node)||!t.contains(r))){if(e.type==="keydown"&&((n=y==null?void 0:y.handleTagAutocompleteKeyDown)!=null&&n.call(y,e))){e.stopPropagation();return}if(e.type==="keydown"&&e.key==="Escape"){e.preventDefault(),e.stopPropagation(),L();return}e.stopPropagation()}}function Q(){if(y)return y;const e=document.createElement("div");e.id=ot,e.style.all="initial";const t=e.attachShadow({mode:"open"});document.documentElement.appendChild(e),t.addEventListener("keydown",pe,!0),t.addEventListener("keypress",pe,!0),t.addEventListener("keyup",pe,!0);const r=document.createElement("style");r.textContent=`
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
    `,t.appendChild(r);const n=document.createElement("div");return n.className="shell",t.appendChild(n),y={host:e,shadow:t,shell:n},y}function L(){var e;(e=y==null?void 0:y.host)!=null&&e.isConnected&&y.host.remove(),y=null,h=null}function Pe(){const e=Q();e.handleTagAutocompleteKeyDown=null,e.shell.textContent=""}function ht(e,t,r){const n=document.createElement("div");n.className="tag-autocomplete";const o=document.createElement("input");o.id="incremento-browser-capture-tags",o.type="text",o.value=String(e||""),o.placeholder="tag-one tag-two",o.autocomplete="off",o.spellcheck=!1,o.setAttribute("role","combobox"),o.setAttribute("aria-autocomplete","list");const a=document.createElement("div");a.id="incremento-browser-capture-tag-suggestions",a.className="tag-suggestions",a.setAttribute("role","listbox"),a.hidden=!0,o.setAttribute("aria-controls",a.id),o.setAttribute("aria-expanded","false");const s=Xt(t);let l=!1,c=0,d=[];const u=()=>{var f;Array.from(a.children).forEach((b,E)=>{b.classList.toggle("is-active",E===c),b.setAttribute("aria-selected",E===c?"true":"false")}),!a.hidden&&d.length>0?(o.setAttribute("aria-activedescendant",`${a.id}-${c}`),(f=a.children[c])==null||f.scrollIntoView({block:"nearest"})):o.removeAttribute("aria-activedescendant")},m=()=>{const f=o.selectionStart??o.value.length;if(d=qt(s,o.value,f),c=d.length>0?Math.min(c,d.length-1):0,a.textContent="",a.hidden=!l||d.length===0,o.setAttribute("aria-expanded",a.hidden?"false":"true"),a.hidden){u();return}d.forEach((b,E)=>{const p=document.createElement("button");p.id=`${a.id}-${E}`,p.type="button",p.setAttribute("role","option"),p.setAttribute("aria-selected",E===c?"true":"false"),p.className=E===c?"is-active":"",p.textContent=b,p.addEventListener("mouseenter",()=>{c=E,u()}),p.addEventListener("mousedown",w=>{w.preventDefault(),_(b)}),a.appendChild(p)}),u()},_=f=>{const b=Yt(o.value,f,o.selectionStart??o.value.length,o.selectionEnd??o.value.length);o.value=b.value,r(b.value),l=!1,c=0,o.focus(),o.setSelectionRange(b.cursor,b.cursor),m()},T=f=>{if(f.target!==o)return!1;if(f.key==="Escape"&&l)return f.preventDefault(),l=!1,m(),!0;if(!d.length)return!1;if(f.key==="ArrowDown"||f.key==="ArrowUp"){f.preventDefault();const b=f.key==="ArrowDown"?1:-1;if(!l)l=!0,c=b>0?0:d.length-1;else return c=(c+b+d.length)%d.length,u(),!0;return m(),!0}return l&&(f.key==="Enter"||f.key==="Tab")?(f.preventDefault(),_(d[c]),!0):!1};return o.addEventListener("input",()=>{r(o.value),c=0,l=!0,m()}),o.addEventListener("focus",()=>{l=!0,m()}),o.addEventListener("click",()=>{c=0,l=!0,m()}),o.addEventListener("select",m),o.addEventListener("blur",()=>{l=!1,m()}),n.appendChild(o),n.appendChild(a),{element:n,handleKeyDown:T}}function bt(e,t){const r=document.createElement("div");r.className="snapshots";for(const n of t){const o=document.createElement("div");o.className="snapshot-card";const a=document.createElement("img");a.src=n.dataUrl,a.alt=n.filename,o.appendChild(a);const s=document.createElement("div");s.className="snapshot-footer";const l=document.createElement("span");l.textContent=n.filename,s.appendChild(l);const c=document.createElement("button");c.type="button",c.textContent=i("remove"),c.addEventListener("click",()=>{h.snapshots=h.snapshots.filter(d=>d.id!==n.id),D()}),s.appendChild(c),o.appendChild(s),r.appendChild(o)}return r}async function D(){var Je;const e=Q(),{shell:t,shadow:r}=e;e.refreshLanguage=()=>{D()};const n=h;Pe();const o=document.createElement("div");o.className="backdrop",o.addEventListener("click",()=>L()),t.appendChild(o);const a=document.createElement("section");a.className="panel",t.appendChild(a);const s=document.createElement("p");s.className="eyebrow",s.textContent=n.mode==="snapshot"?i("browser_snapshot"):i("browser_selection"),a.appendChild(s);const l=document.createElement("h2");l.textContent=i("send_capture_anki"),a.appendChild(l);const c=document.createElement("p");c.className="lead",c.textContent=n.mode==="snapshot"?_e("snapshots_ready",n.snapshots.length,{url:n.context.url}):i("selected_text_from",{url:n.context.url}),a.appendChild(c);const d=document.createElement("form");d.noValidate=!0;const u=document.createElement("div");u.className="grid",d.appendChild(u);const m=(g,x,C=!1,v="")=>{const F=document.createElement("div");F.className=`field${C?" full":""}`;const Qe=document.createElement("label");if(Qe.textContent=g,F.appendChild(Qe),F.appendChild(x),v){const ye=document.createElement("p");ye.className="field-note",ye.textContent=v,F.appendChild(ye)}return F},_=document.createElement("select");for(const g of n.meta.noteTypes){const x=document.createElement("option");x.value=g.name,x.textContent=g.name,_.appendChild(x)}_.value=n.form.noteTypeName,_.addEventListener("change",()=>{var C;const g=n.meta.noteTypes.find(v=>v.name===_.value),x=ve((C=n.form.mappingsByNoteType)==null?void 0:C[_.value],(g==null?void 0:g.fields)||[]);n.form=V(n.form,_.value,x),D()}),u.appendChild(m(i("note_type"),_));const T=document.createElement("select");for(const g of n.meta.deckNames){const x=document.createElement("option");x.value=g,x.textContent=g,T.appendChild(x)}T.value=n.form.deckName,T.addEventListener("change",()=>{n.form.deckName=T.value}),u.appendChild(m(i("deck"),T));const f=ht(n.form.tagsText,n.meta.tagNames,g=>{n.form.tagsText=g});y.handleTagAutocompleteKeyDown=f.handleKeyDown,u.appendChild(m(i("tags"),f.element,!0,i("tag_hint")));const b=document.createElement("div");b.style.display="grid",b.style.gridTemplateColumns="1fr auto",b.style.gap="10px",b.style.alignItems="center";const E=document.createElement("input");E.type="range",E.min="0",E.max="100",E.step="0.1",E.value=String(n.form.priority??K);const p=document.createElement("input");p.type="number",p.min="0",p.max="100",p.step="0.1",p.style.width="92px",p.value=String(n.form.priority??K);const w=g=>{const x=Number(g),C=Number.isFinite(x)?Math.min(100,Math.max(0,x)):K;n.form.priority=Number(C.toFixed(4)),E.value=String(n.form.priority),p.value=String(n.form.priority)};E.addEventListener("input",()=>w(E.value)),p.addEventListener("change",()=>w(p.value)),b.appendChild(E),b.appendChild(p),u.appendChild(m(i("priority"),b));const A=["",...((Je=n.meta.noteTypes.find(g=>g.name===n.form.noteTypeName))==null?void 0:Je.fields)||[]],N=(g,x)=>{const C=document.createElement("select");for(const v of A){const F=document.createElement("option");F.value=v,F.textContent=v||i("do_not_insert"),C.appendChild(F)}return C.value=A.includes(g)?g:"",C.addEventListener("change",()=>{x(C.value)}),C},U=!!n.context.selectedText;u.appendChild(m(i("page_title_field"),N(n.form.fieldMappings.titleField,g=>{n.form=V(n.form,n.form.noteTypeName,{...n.form.fieldMappings,titleField:g})}),!1,i("page_title_field_note"))),u.appendChild(m(i("selected_text_field"),N(n.form.fieldMappings.selectedTextField,g=>{n.form=V(n.form,n.form.noteTypeName,{...n.form.fieldMappings,selectedTextField:g})}),!1,U?i("chars_ready",{count:n.context.selectedText.length}):i("no_text_added"))),u.appendChild(m(i("source_url_field"),N(n.form.fieldMappings.urlField,g=>{n.form=V(n.form,n.form.noteTypeName,{...n.form.fieldMappings,urlField:g})}),!1,i("source_url_note"))),u.appendChild(m(i("snapshot_field"),N(n.form.fieldMappings.snapshotField,g=>{n.form=V(n.form,n.form.noteTypeName,{...n.form.fieldMappings,snapshotField:g})}),!0,n.snapshots.length>0?_e("snapshots_selected",n.snapshots.length):i("no_snapshots")));const B=document.createElement("textarea");if(B.value=n.context.selectedText,B.placeholder=n.mode==="snapshot"?i("add_text_snapshots"):i("selected_text_edit"),B.addEventListener("input",()=>{n.context.selectedText=B.value}),u.appendChild(m(n.mode==="snapshot"?i("text_to_add"):i("selected_text"),B,!0,i("inserted_text_note"))),n.snapshots.length>0){const g=document.createElement("div");g.className="field full";const x=document.createElement("label");x.textContent=i("snapshots"),g.appendChild(x),g.appendChild(bt(r,n.snapshots)),u.appendChild(g)}const M=document.createElement("p");M.className=`status${n.statusKind?` ${n.statusKind}`:""}`,M.textContent=n.statusValidation?z(n.statusValidation):n.statusCode?i(n.statusCode):n.statusText,d.appendChild(M);const Y=document.createElement("div");if(Y.className="actions",n.snapshots.length>0){const g=document.createElement("button");g.type="button",g.className="ghost-btn",g.textContent=i("capture_more"),g.addEventListener("click",()=>Z(n.snapshots)),Y.appendChild(g)}const j=document.createElement("button");j.type="button",j.className="secondary-btn",j.textContent=i("language_cancel"),j.addEventListener("click",()=>L()),Y.appendChild(j);const G=document.createElement("button");G.type="submit",G.className="primary-btn",G.textContent=n.submitting?i("saving"):i("create_note"),G.disabled=!!n.submitting,Y.appendChild(G),d.appendChild(Y),d.addEventListener("submit",async g=>{if(g.preventDefault(),n.submitting)return;const x=Se({...n.context,snapshots:n.snapshots.map(v=>({filename:v.filename,base64:v.base64}))},n.form),C=tt(x);if(!C.ok){n.statusKind="error",n.statusCode="",n.statusValidation=C,n.statusText=z(C),D();return}n.submitting=!0,n.statusKind="",n.statusValidation=null,n.statusCode="creating_note",n.statusText=i("creating_note"),D();try{const v=await Be(x);await Me(n.form),k(i("created_note",{type:v.noteTypeName,deck:v.deckName})),L()}catch(v){n.submitting=!1,n.statusKind="error",n.statusValidation=null,n.statusCode="",n.statusText=(v==null?void 0:v.message)||i("create_note_failed"),D()}}),a.appendChild(d)}function yt(e){return new Promise((t,r)=>{const n=new Image;n.onload=()=>t(n),n.onerror=()=>r(new Error(i("failed_decode_screenshot"))),n.src=e})}async function xt(e,t){const r=await yt(e),n=r.width/window.innerWidth,o=r.height/window.innerHeight,a=Math.max(0,Math.round(t.x*n)),s=Math.max(0,Math.round(t.y*o)),l=Math.max(1,Math.round(t.width*n)),c=Math.max(1,Math.round(t.height*o)),d=document.createElement("canvas");return d.width=l,d.height=c,d.getContext("2d").drawImage(r,a,s,l,c,0,0,l,c),d.toDataURL("image/png")}function _t(e){const t=String(e||""),r=t.indexOf(",");return r>=0?t.slice(r+1):t}function me(e){const t=Math.abs(e.width),r=Math.abs(e.height);return{x:e.width>=0?e.x:e.x-t,y:e.height>=0?e.y:e.y-r,width:t,height:r}}function De(e=2){return new Promise(t=>{const r=Math.max(1,Number(e)||1);let n=0;const o=()=>{if(n+=1,n>=r){t();return}requestAnimationFrame(o)};requestAnimationFrame(o)})}function Et(e,t){if(!(e instanceof Element))return!1;const r=window.getComputedStyle(e),n=t==="x"?r.overflowX:r.overflowY;return/(auto|scroll|overlay)/.test(String(n||""))?t==="x"?e.scrollWidth>e.clientWidth:e.scrollHeight>e.clientHeight:!1}function Oe(e,t){let r=e instanceof Element?e:null;for(;r;){if(Et(r,t))return r;r=r.parentElement}const n=document.scrollingElement;return n instanceof Element?n:document.documentElement}function wt(e,t){var d;if(!e)return;const r=((d=t==null?void 0:t.style)==null?void 0:d.pointerEvents)||"";t!=null&&t.style&&(t.style.pointerEvents="none");let n=null;try{n=document.elementFromPoint(e.clientX,e.clientY)}finally{t!=null&&t.style&&(t.style.pointerEvents=r)}const o=Number(e.deltaX)||0,a=Number(e.deltaY)||0,s=o?Oe(n,"x"):null,l=a?Oe(n,"y"):null,c=document.scrollingElement instanceof Element?document.scrollingElement:document.documentElement;o&&(s||c).scrollBy({left:o,top:0,behavior:"auto"}),a&&(l||c).scrollBy({left:0,top:a,behavior:"auto"})}async function Tt(e,t=[]){if(t.length>=ie)throw new Error(i("too_many_snapshots",{count:ie}));const r=Q();r.shell.style.display="none";try{await De(2);const n=await mt(),o=nt(n,{maxBytes:Vt});if(!o.ok)throw new Error(z(o));const a=me(e),s=await xt(n,a),l=nt(s,{maxBytes:Ht});if(!l.ok)throw new Error(z(l));return{id:`${Date.now()}-${t.length}-${Math.random().toString(16).slice(2,8)}`,filename:`browser-capture-${t.length+1}.png`,dataUrl:s,base64:_t(s)}}catch(n){throw new Error((n==null?void 0:n.message)||i("failed_capture_tab"))}finally{y!=null&&y.shell&&(y.shell.style.display="",await De(1))}}function Z(e=[]){var E;const t=Q();Pe();const r=e.length>0&&((E=h==null?void 0:h.context)==null?void 0:E.selectedText)||"";h={mode:"snapshot",meta:(h==null?void 0:h.meta)||null,form:(h==null?void 0:h.form)||null,context:{url:window.location.href||"",title:document.title||"",selectedText:r},snapshots:[...e],statusKind:"",statusText:"",submitting:!1};const n=t.shell,o=document.createElement("div");o.className="capture-shell",n.appendChild(o);const a=document.createElement("div");a.className="capture-toolbar";const s=p=>{a.replaceChildren();const w=document.createElement("strong");w.textContent=i("snapshot_mode"),a.appendChild(w);const S=document.createElement("span");S.textContent=i(p),a.appendChild(S);const A=document.createElement("span");A.className="spacer",a.appendChild(A)};s("snapshot_mode_intro"),n.appendChild(a);const l=[...e];let c=null,d=null,u=!1;const m=()=>{s("snapshot_mode_hint");const p=document.createElement("span");p.textContent=u?i("capturing"):_e("snapshot_ready",l.length),a.appendChild(p);const w=document.createElement("button");w.type="button",w.className="toolbar-btn",w.textContent=i("undo"),w.disabled=u||l.length===0,w.addEventListener("click",()=>{l.pop(),m()}),a.appendChild(w);const S=document.createElement("button");S.type="button",S.className="toolbar-btn",S.textContent=i("clear"),S.disabled=u||l.length===0,S.addEventListener("click",()=>{l.splice(0,l.length),m()}),a.appendChild(S);const A=document.createElement("button");A.type="button",A.className="toolbar-btn",A.textContent=i("language_cancel"),A.addEventListener("click",()=>L()),a.appendChild(A);const N=document.createElement("button");N.type="button",N.className="toolbar-btn",N.textContent=i("extract_now"),N.disabled=u||l.length===0,N.addEventListener("click",async()=>{var B;if(!u){if(!l.length){k(i("draw_region_first"));return}u=!0,m();try{const M=await ft(((B=h==null?void 0:h.context)==null?void 0:B.selectedText)||"",[...l]);k(i("created_note",{type:M.noteTypeName,deck:M.deckName})),L()}catch(M){u=!1,m(),k((M==null?void 0:M.message)||i("create_note_failed"))}}}),a.appendChild(N);const U=document.createElement("button");U.type="button",U.className="toolbar-btn primary",U.textContent=i("continue"),U.addEventListener("click",()=>{var B;if(!u){if(!l.length){k(i("draw_region_first"));return}ee({mode:"snapshot",selectedText:((B=h==null?void 0:h.context)==null?void 0:B.selectedText)||"",snapshots:[...l]})}}),a.appendChild(U)};t.refreshLanguage=m;const _=(p,w)=>{if(l.length>=ie){k(i("too_many_snapshots",{count:ie}));return}d={x:p,y:w,width:0,height:0},c=document.createElement("div"),c.className="selection-rect",c.dataset.label=i("capture_label",{count:l.length+1}),o.appendChild(c)},T=()=>{if(!c||!d)return;const p=me(d);Object.assign(c.style,{left:`${p.x}px`,top:`${p.y}px`,width:`${p.width}px`,height:`${p.height}px`})};o.addEventListener("pointerdown",p=>{u||p.button!==0||p.target!==o||(p.preventDefault(),_(p.clientX,p.clientY),T())}),o.addEventListener("pointermove",p=>{d&&(p.preventDefault(),d.width=p.clientX-d.x,d.height=p.clientY-d.y,T())});const f=p=>{d||u||(p.preventDefault(),wt(p,t.host))};o.addEventListener("wheel",f,{passive:!1}),a.addEventListener("wheel",f,{passive:!1});const b=async()=>{if(!c||!d)return;const p=me(d),w=c;if(p.width>=24&&p.height>=24){u=!0,m();try{const S=await Tt(p,l);l.push(S)}catch(S){k((S==null?void 0:S.message)||i("failed_capture_tab"))}}else w.remove();w.remove(),c=null,d=null,u=!1,m()};o.addEventListener("pointerup",()=>{b()}),o.addEventListener("pointercancel",()=>{b()}),m()}async function ee({mode:e,selectedText:t="",snapshots:r=[]}){if(e==="snapshot")await Ie(t,r);else{const n=(h==null?void 0:h.meta)||await Ne();if(!Array.isArray(n==null?void 0:n.noteTypes)||n.noteTypes.length===0)throw new Error(i("no_note_types"));if(!Array.isArray(n==null?void 0:n.deckNames)||n.deckNames.length===0)throw new Error(i("no_decks"));const o=(h==null?void 0:h.form)||await Le(n);h={mode:e,meta:n,form:o,context:{url:window.location.href||"",title:document.title||"",selectedText:Ze(e,t,$())},snapshots:Array.isArray(r)?r:[],statusKind:"",statusText:"",submitting:!1}}await D()}globalThis.__incrementoTriggerBrowserCapture=e=>{if(String(e||"").trim().toLowerCase()==="snapshot")return Z(),{ok:!0};const r=$();return r?(ee({mode:"selection",selectedText:r,snapshots:[]}).catch(n=>{k((n==null?void 0:n.message)||i("open_capture_failed")),L()}),{ok:!0}):(k(i("select_page_text")),{ok:!1,error:i("select_page_text")})},document.addEventListener("keydown",e=>{if(!e.altKey||!gt(e)||ue()||Fe(e.target))return;if(e.metaKey){e.preventDefault(),e.stopPropagation(),Z();return}if(e.ctrlKey||e.shiftKey)return;const t=$();t&&(e.preventDefault(),e.stopPropagation(),ee({mode:"selection",selectedText:t,snapshots:[]}).catch(r=>{k((r==null?void 0:r.message)||i("open_capture_failed")),L()}))},!0),document.addEventListener("contextmenu",e=>{const t=Ce(e.target);Ee=de(t)},!0),document.addEventListener("click",e=>{if(!W.modifierClickEnabled||e.defaultPrevented||Number(e.button)!==0||ue()||Fe(e.target))return;const t=Ce(e.target);if(!t||!Rt(e,W))return;const r=de(t);if(!r)return;W.navigateAfterSave||e.preventDefault();const n=H();n==null||n.sendMessage({type:"SAVE_CLICKED_LINK_AS_WEBPAGE",url:r.url,title:r.title,sourcePageUrl:window.location.href||"",sourcePageTitle:document.title||""},o=>{var a;(a=chrome==null?void 0:chrome.runtime)==null||a.lastError})},!0),document.addEventListener("selectionchange",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("mouseup",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keyup",()=>{var t;const e=String(((t=window.getSelection)==null?void 0:t.call(window).toString())||"").trim();e&&(globalThis.__incrementoLastSelectedText=e)},!0),document.addEventListener("keydown",e=>{e.key==="Escape"&&ue()&&(e.preventDefault(),e.stopPropagation(),L())},!0);function vt(e){try{const t=new URL(e),r=t.searchParams.get("v");if(r)return r;const n=t.pathname.split("/").filter(Boolean);if(t.hostname==="youtu.be"&&n[0])return n[0];if((n[0]==="shorts"||n[0]==="live"||n[0]==="embed")&&n[1])return n[1]}catch{}return""}function St(e){const t=String(e||"").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);return t?t[1]:""}function Ct(){const e=window.location.href||"",t=window.location.hostname||"";return t.includes("youtube.com")||t==="youtu.be"?{provider:"youtube",videoId:vt(e)}:t.includes("vimeo.com")?{provider:"vimeo",videoId:St(e)}:{provider:"",videoId:""}}function Ue(e){try{const r=new URL(e).searchParams.get("inc_card_id")||"",n=Number(r);if(Number.isFinite(n)&&n>0)return Math.floor(n)}catch{}return 0}function kt(e){const t=String(e||"").replace(/^#/,"").trim();if(!t)return"";const n=t.indexOf("__incremento_resume__=1");return n<0?t:t.slice(0,n).replace(/[&?]+$/,"")}function At(e){try{const t=new URL(e);t.searchParams.delete("inc_card_id"),t.searchParams.delete("inc_track_web"),t.searchParams.delete("inc_resume_sec"),t.searchParams.delete("inc_resume_media");const r=kt(t.hash);return t.hash=r?`#${r}`:"",t.toString()}catch{return String(e||"")}}function Nt(e){try{const t=new URL(e),r=String(t.searchParams.get("inc_track_web")||"").trim().toLowerCase();return r==="1"||r==="true"||r==="yes"||r==="on"}catch{return!1}}function Bt(){if(window.top!==window)return;const e=window.location.href||"";if(!e||!/inc_(card_id|track_web|resume_sec|resume_media)|__incremento_resume__=1/.test(e))return;const t=At(e);if(!(!t||t===e))try{history.replaceState(history.state,document.title||"",t),be=t}catch{}}function We(){const e=Array.from(document.querySelectorAll("video"));return e.length===0?null:(e.sort((t,r)=>{const n=(t.videoWidth||0)*(t.videoHeight||0);return(r.videoWidth||0)*(r.videoHeight||0)-n}),e[0])}function fe(e,t=12){const r=Math.max(0,Math.floor(Number(e)||0));if(r<=0)return!1;const n=We();if(!n)return t>0&&window.setTimeout(()=>fe(r,t-1),500),!1;try{return n.currentTime=r,k(i("resumed_to",{seconds:r})),!0}catch{return t>0&&window.setTimeout(()=>fe(r,t-1),500),!1}}function te(){var s,l;const e=window.location.href||"",{provider:t,videoId:r}=Ct(),n=We(),o=t?e:String((n==null?void 0:n.currentSrc)||(n==null?void 0:n.src)||"").trim(),a=String(((s=n==null?void 0:n.getAttribute)==null?void 0:s.call(n,"title"))||((l=n==null?void 0:n.getAttribute)==null?void 0:l.call(n,"aria-label"))||document.title||"").trim();return{provider:t,videoId:r,video:n,mediaUrl:o,mediaTitle:a}}function Lt(){const{provider:e,video:t}=te();let r=-1,n=!1;if(t&&(r=Math.max(0,Math.floor(Number(t.currentTime)||0)),n=!0),e==="youtube"&&r<=0){const o=he();o>=0&&(r=o,n=!0)}if(e==="vimeo"&&r<=0){const o=ge();o>=0&&(r=o,n=!0)}return{found:n,seconds:n?Math.max(0,r):0}}function Mt(){const e=window.location.href||"",{provider:t,videoId:r,mediaUrl:n,mediaTitle:o}=te(),a=Lt();return{ok:!0,pageUrl:e,pageTitle:document.title||"",provider:t,videoId:r,mediaUrl:n,mediaTitle:o,hasDetectedTime:!!a.found,seconds:Math.max(0,Math.floor(Number(a.seconds)||0)),timeText:a.found?Ae(a.seconds):""}}function ze(e){const t=String(e||"").trim();if(!t)return-1;const r=t.split(":").map(n=>n.trim());return r.every(n=>/^\d+$/.test(n))?r.length===2?Number(r[0])*60+Number(r[1]):r.length===3?Number(r[0])*3600+Number(r[1])*60+Number(r[2]):-1:-1}function ge(){const e=Array.from(document.querySelectorAll('[data-progress-bar-timecode="true"], [class*="Timecode_module_timecode__"]'));for(const t of e){const r=String((t==null?void 0:t.textContent)||"").trim(),n=ze(r);if(n>=0)return n}return-1}function he(){const e=Array.from(document.querySelectorAll(".ytp-time-current, [class*='ytp-time-current']"));for(const t of e){const r=String((t==null?void 0:t.textContent)||"").trim(),n=ze(r);if(n>=0)return n}return-1}async function Re(){try{const e=await X({type:"GET_LINKED_CARD_CONTEXT",url:window.location.href||""});if(!(e!=null&&e.linked)||Number(e.cardId)<=0){R(null);return}const t=await X({type:"LOAD_BROWSER_MEDIA_REF"});if(!(t!=null&&t.ok)||!(t!=null&&t.hasReference)){R(null);return}R(t)}catch{R(null)}}let Ke=-1,$e=0,Ve=-1,He=0,ne=!1,q=!0,re=null,be=window.location.href||"";function oe(){q=!1,re!==null&&(clearInterval(re),re=null)}function Xe(e){if(!q)return!1;try{const t=H();return t!=null&&t.id?(t.sendMessage(e,()=>{try{const r=t==null?void 0:t.lastError;r&&/context invalidated/i.test(String(r.message||""))&&oe()}catch{oe()}}),!0):(oe(),!1)}catch{return oe(),!1}}function qe(){if(!q){P(!1);return}try{const e=H();if(!(e!=null&&e.id)){P(!1);return}e.sendMessage({type:"GET_TRACKING_STATUS",url:window.location.href||""},t=>{try{if(e==null?void 0:e.lastError){P(!1);return}}catch{P(!1);return}P(!!(t!=null&&t.tracked),String((t==null?void 0:t.mode)||""))})}catch{P(!1)}}function I(e=!1,t=!1){if(!q)return;const{provider:r,videoId:n,video:o}=te();if(!r)return;let a=-1;if(o&&(a=Math.max(0,Math.floor(Number(o.currentTime)||0))),r==="youtube"&&a<=0){const l=he();l>=0&&(a=l)}if(r==="vimeo"&&a<=0){const l=ge();l>=0&&(a=l)}if(a<0)return;const s=Date.now();!e&&a===Ke&&s-$e<4e3||(Ke=a,$e=s,Xe({type:"heartbeat",provider:r,videoId:n,cardId:Ue(window.location.href||""),flush:!!t,seconds:a,url:window.location.href||"",title:document.title||""}))}function O(e=!1,t=!1){if(!q)return;const r=window.location.href||"",{provider:n,videoId:o,video:a,mediaUrl:s,mediaTitle:l}=te();if(!a&&!n)return;let c=-1;if(a&&(c=Math.max(0,Math.floor(Number(a.currentTime)||0))),n==="youtube"&&c<=0){const u=he();u>=0&&(c=u)}if(n==="vimeo"&&c<=0){const u=ge();u>=0&&(c=u)}if(c<0)return;const d=Date.now();!e&&c===Ve&&d-He<4e3||(Ve=c,He=d,Xe({type:"web_media_heartbeat",provider:n,videoId:o,cardId:Ue(r),trackEnabled:Nt(r),flush:!!t,seconds:c,url:r,mediaUrl:s,mediaTitle:l,title:document.title||""}))}re=window.setInterval(()=>{I(!1,!1),O(!1,!1)},1e3),window.setInterval(()=>{const e=window.location.href||"";e!==be&&(be=e,ne=!1,qe(),Re())},750),window.addEventListener("pagehide",()=>{I(!0,!0),O(!0,!0)},{capture:!0}),window.addEventListener("beforeunload",()=>{I(!0,!0),O(!0,!0)},{capture:!0}),document.addEventListener("visibilitychange",()=>{document.visibilityState==="hidden"&&(I(!0,!0),O(!0,!0))}),document.addEventListener("timeupdate",()=>{I(!1,!1),O(!1,!1)},!0),document.addEventListener("play",()=>{I(!0,!1),O(!0,!1)},!0),document.addEventListener("pause",()=>{I(!0,!0),O(!0,!0)},!0),document.addEventListener("ended",()=>I(!0,!0),!0),window.setTimeout(()=>I(!0,!1),1200),window.setTimeout(Bt,1200),window.setTimeout(qe,300),window.setTimeout(()=>{Re()},320),window.__incrementoContentScriptState={...window.__incrementoContentScriptState||{},version:J,ready:!0}})();
