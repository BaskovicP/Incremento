import{t as i,aj as Xt,al as jt,ak as Gt,aN as Yt,q as ce,T as Te,e as Jt,R as Oe,aL as Qt,aJ as Zt,aK as ft,aO as gt,aP as en,aQ as tn,ar as Fe,aR as Ce,c as nn,aD as ht,aS as rn,aT as an,aU as on,aV as ln,aW as he,aX as sn,aY as bt,ay as xt,aZ as yt,a_ as cn,aG as _t,aI as dn,a$ as un,b0 as wt,b1 as pn,b2 as mn,n as fn,g as gn,a as hn}from"./assets/extension-shared.js";import"./assets/extension-vendor.js";const Et="incremento-video-time-toast";function vt(q=globalThis.document){var Z;(Z=q.getElementById(Et))==null||Z.remove()}function bn(q,{action:Z="",request:de,document:F=globalThis.document,requestFrame:ee=globalThis.requestAnimationFrame,schedule:R=globalThis.setTimeout}={}){vt(F);const V=Z==="open_shortcut_settings",C=F.createElement("div");if(C.id=Et,C.textContent=String(q||""),C.setAttribute("role",V?"alert":"status"),Object.assign(C.style,{position:"fixed",zIndex:2147483647,top:"10px",right:"10px",maxWidth:V?"360px":"320px",padding:"10px 14px",background:"rgba(0, 0, 0, 0.86)",color:"#fff",fontSize:"13px",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"6px",boxShadow:"0 2px 8px rgba(0, 0, 0, 0.4)",opacity:"0",transition:"opacity 0.2s ease",lineHeight:"1.5"}),V){const te=F.createElement("div");Object.assign(te.style,{display:"flex",flexWrap:"wrap",gap:"8px",marginTop:"10px"});const z=E=>{const M=F.createElement("button");return M.type="button",M.textContent=E,Object.assign(M.style,{padding:"6px 10px",border:"1px solid #a7b1c2",borderRadius:"4px",background:"#fff",color:"#172033",font:"inherit",cursor:"pointer"}),te.appendChild(M),M},I=z(i("open_shortcut_settings")),ne=z(i("snapshot_warning_dismiss")),K=F.createElement("div");K.setAttribute("role","status"),K.hidden=!0,K.style.marginTop="8px",I.addEventListener("click",async E=>{if(E.stopPropagation(),!(!E.isTrusted||I.disabled)){I.disabled=!0,K.hidden=!0;try{const M=await de({type:"OPEN_SHORTCUT_SETTINGS"});if(M!=null&&M.ok){C.remove();return}}catch{}I.disabled=!1,K.textContent=i("open_shortcuts_failed"),K.hidden=!1}}),ne.addEventListener("click",E=>{E.stopPropagation(),C.remove()}),C.appendChild(te),C.appendChild(K)}return F.documentElement.appendChild(C),ee(()=>{C.style.opacity="1"}),V||R(()=>{C.style.opacity="0",R(()=>C.remove(),220)},2400),C}(()=>{var it,lt,st,ct;const q="browser-capture-v13",Z="incremento-browser-capture-root",de=window.__incrementoContentScriptState&&typeof window.__incrementoContentScriptState=="object"?window.__incrementoContentScriptState:{};if(de.version===q&&de.ready)return;window.__incrementoContentScriptState={...de,version:q,ready:!1},window.__incrementoContentScriptVersion=q;const F="incremento_browser_capture_settings",ee=50;let R=Jt,V=null,C=null,te="";const z=e=>{if(!(e!=null&&e.errorCode))return String((e==null?void 0:e.error)||"");const n={...e.errorParams};return n.count!=null&&(n.count=nn(n.count)),i(e.errorCode,n,e.error)};globalThis.__incrementoLastSelectedText=String(globalThis.__incrementoLastSelectedText||"").trim();function I(){var n;const e=String(((n=window.getSelection)==null?void 0:n.call(window).toString())||"").trim();return e?(globalThis.__incrementoLastSelectedText=e,e):String(globalThis.__incrementoLastSelectedText||"").trim()}function ne(){var r;if(be())return;const e=(r=window.getSelection)==null?void 0:r.call(window),n=String((e==null?void 0:e.toString())||"").trim();if(n){globalThis.__incrementoLastSelectedText=n;try{const t=an(e);globalThis.__incrementoLastSelection={...t,url:window.location.href},globalThis.__incrementoSelectionError=""}catch(t){globalThis.__incrementoLastSelection=null,globalThis.__incrementoSelectionError=t.message}}}function K(e){const n=globalThis.__incrementoLastSelection;if(globalThis.__incrementoSelectionError&&!n)throw new Error(i("selected_text_too_large",{count:ft}));return{originalSelectedText:e,selectedHtml:(n==null?void 0:n.selectedText)===e&&(n==null?void 0:n.url)===window.location.href?n.selectedHtml:""}}function E(e,n={}){return bn(e,{...n,request:j})}async function M(){try{const e=await ce.storage.local.get(Te);R=Oe(e==null?void 0:e[Te])}catch{R=Oe(null)}}function We(e){var a,o;const n=e instanceof Element?e:(e==null?void 0:e.parentElement)||null,r=(a=n==null?void 0:n.closest)==null?void 0:a.call(n,"a[href]");if(!r)return null;const t=String(r.href||((o=r.getAttribute)==null?void 0:o.call(r,"href"))||"").trim();return ht(t)?r:null}function ke(e){var a,o,d,l,s,c,u,f,k,A,g,x;if(!e)return null;const n=String(e.href||((a=e.getAttribute)==null?void 0:a.call(e,"href"))||"").trim();if(!ht(n))return null;const t=[...St(e,n),(o=e.getAttribute)==null?void 0:o.call(e,"aria-label"),(d=e.getAttribute)==null?void 0:d.call(e,"title"),(c=(s=(l=e.querySelector)==null?void 0:l.call(e,"img[alt]"))==null?void 0:s.getAttribute)==null?void 0:c.call(s,"alt"),(k=(f=(u=e.querySelector)==null?void 0:u.call(e,"[aria-label]"))==null?void 0:f.getAttribute)==null?void 0:k.call(f,"aria-label"),(x=(g=(A=e.querySelector)==null?void 0:A.call(e,"[title]"))==null?void 0:g.getAttribute)==null?void 0:x.call(g,"title"),e.textContent];return{url:n,title:rn(t,n)}}function Ue(e,n){var r,t,a;n&&e.push((r=n.getAttribute)==null?void 0:r.call(n,"title"),(t=n.getAttribute)==null?void 0:t.call(n,"data-title-no-tooltip"),n.textContent,(a=n.getAttribute)==null?void 0:a.call(n,"aria-label"))}function St(e,n){var d,l,s,c;const r=wt(n);if(!r)return[];const t=[],a=((d=e.closest)==null?void 0:d.call(e,["ytd-rich-item-renderer","ytd-video-renderer","ytd-grid-video-renderer","ytd-compact-video-renderer","ytd-playlist-video-renderer","ytd-playlist-panel-video-renderer","ytd-reel-item-renderer","yt-lockup-view-model","ytm-shorts-lockup-view-model","[data-video-id]"].join(", ")))||null,o=a?[a,document]:[document];for(const u of o){const f=u===document?document.links||[]:((l=u.querySelectorAll)==null?void 0:l.call(u,"a[href]"))||[],k=Math.min(Number(f.length)||0,u===document?2e3:200);for(let A=0;A<k;A+=1){const g=f[A];if(g===e)continue;const x=String((g==null?void 0:g.href)||((s=g==null?void 0:g.getAttribute)==null?void 0:s.call(g,"href"))||"").trim();wt(x)===r&&(Ue(t,g),Ue(t,(c=g.querySelector)==null?void 0:c.call(g,"#video-title, #video-title-link, [data-title-no-tooltip]")))}}return t}function Tt(){let e=document.getElementById("incremento-tracking-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-tracking-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483646,top:"52px",right:"10px",display:"none",alignItems:"center",gap:"8px",padding:"8px 12px",background:"linear-gradient(135deg, rgba(10, 34, 64, 0.94), rgba(17, 83, 126, 0.94))",color:"#fff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",letterSpacing:"0.08em",textTransform:"uppercase",borderRadius:"999px",boxShadow:"0 4px 14px rgba(0, 0, 0, 0.28)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"none"});const n=document.createElement("span");n.textContent="●",Object.assign(n.style,{color:"#53f2a5",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(83, 242, 165, 0.85)"}),e.appendChild(n);const r=document.createElement("span");r.textContent="⚠",Object.assign(r.style,{color:"#ffd166",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(255, 209, 102, 0.55)"}),e.appendChild(r);const t=document.createElement("span");return t.id="incremento-tracking-badge-label",t.textContent=i("tracking"),e.appendChild(t),document.documentElement.appendChild(e),e}function X(e,n=""){te=e?n:"";const r=Tt(),t=document.getElementById("incremento-tracking-badge-label");if(!(!r||!t)){if(!e){r.style.display="none";return}t.textContent=n==="web"?i("tracking_web_card"):i("tracking"),r.style.display="inline-flex"}}function Re(e){const n=Math.max(0,Math.floor(Number(e)||0)),r=Math.floor(n/3600),t=Math.floor(n%3600/60),a=n%60;return r>0?`${r}:${String(t).padStart(2,"0")}:${String(a).padStart(2,"0")}`:`${t}:${String(a).padStart(2,"0")}`}function Ct(){let e=document.getElementById("incremento-browser-media-ref-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-browser-media-ref-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483645,top:"96px",right:"10px",display:"none",alignItems:"center",gap:"8px",maxWidth:"320px",padding:"9px 12px",background:"linear-gradient(135deg, rgba(28, 32, 48, 0.96), rgba(34, 62, 96, 0.96))",color:"#eef5ff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"14px",boxShadow:"0 5px 18px rgba(0, 0, 0, 0.30)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"auto"});const n=document.createElement("span");n.textContent="▶",Object.assign(n.style,{color:"#8fd3ff",fontSize:"11px",lineHeight:"1"}),e.appendChild(n);const r=document.createElement("span");r.id="incremento-browser-media-ref-badge-label",r.textContent="",Object.assign(r.style,{flex:"1 1 auto",minWidth:"0"}),e.appendChild(r);const t=document.createElement("button");return t.type="button",t.textContent="×",t.setAttribute("aria-label",i("saved_time_badge_dismiss")),Object.assign(t.style,{appearance:"none",border:"0",background:"transparent",color:"#a9bfdc",cursor:"pointer",fontSize:"16px",fontWeight:"700",lineHeight:"1",padding:"0 0 0 4px",margin:"0",pointerEvents:"auto"}),t.addEventListener("click",a=>{a.preventDefault(),a.stopPropagation(),we=!0,e.style.display="none"}),e.appendChild(t),document.documentElement.appendChild(e),e}function re(e){C=e;const n=Ct(),r=document.getElementById("incremento-browser-media-ref-badge-label");if(!n||!r)return;if(!!!(e!=null&&e.hasReference)){n.style.display="none";return}if(we)return;const a=String((e==null?void 0:e.timeText)||Re(e==null?void 0:e.seconds));r.textContent=a?i("last_saved_time",{time:a}):i("last_saved"),n.style.display="inline-flex"}function ue(){var e;try{return((e=ce)==null?void 0:e.runtime)||null}catch{return null}}Xt(),jt(),Gt(()=>{var r;const e=document.getElementById("incremento-tracking-badge");Yt(e,()=>X(!0,te)),C&&re(C);const n=document.querySelector("#incremento-browser-media-ref-badge button");n==null||n.setAttribute("aria-label",i("saved_time_badge_dismiss")),(r=b==null?void 0:b.refreshLanguage)==null||r.call(b)}),M();try{(st=(lt=(it=ce)==null?void 0:it.storage)==null?void 0:lt.onChanged)==null||st.addListener((e,n)=>{var r;n!=="local"||!e||!Object.prototype.hasOwnProperty.call(e,Te)||(R=Oe((r=e[Te])==null?void 0:r.newValue))})}catch{}try{const e=ue();(ct=e==null?void 0:e.onMessage)==null||ct.addListener((n,r,t)=>{var a;if(!n||!n.type)return!1;if(n.type==="SHOW_TOAST")return E(n.text||"",{action:n.action}),t==null||t({ok:!0}),!1;if(n.type==="TRIGGER_BROWSER_CAPTURE"){if(String(n.mode||"").trim().toLowerCase()==="snapshot")return Le(),t==null||t({ok:!0}),!1;const d=I();return d?(ye({mode:"selection",selectedText:d,snapshots:[]}).then(()=>t==null?void 0:t({ok:!0}),l=>{E((l==null?void 0:l.message)||i("open_capture_failed")),W(),t==null||t({ok:!1,error:String((l==null?void 0:l.message)||"")})}),!0):(E(i("select_page_text")),t==null||t({ok:!1}),!1)}if(n.type==="GET_PAGE_CONTEXT"){const o=Qt(Zt,ft,{includeHtml:n.includeHtml!==!1,htmlScope:n.htmlScope,preserveStyles:n.preserveStyles===!0});return o.ok?(t==null||t(o),!1):(t==null||t({...o,error:z(o)}),!1)}if(n.type==="GET_CONTEXT_LINK_INFO"){const o=String(n.url||"").trim();let d=V;if(o&&String((d==null?void 0:d.url)||"")!==o){let l=null;const s=document.links||[],c=Math.min(Number(s.length)||0,2e3);for(let u=0;u<c;u+=1){const f=s[u];if(String((f==null?void 0:f.href)||((a=f==null?void 0:f.getAttribute)==null?void 0:a.call(f,"href"))||"").trim()===o){l=f;break}}d=ke(l||null)}return t==null||t({ok:!0,url:String((d==null?void 0:d.url)||""),title:String((d==null?void 0:d.title)||"")}),!1}if(n.type==="GET_CURRENT_MEDIA_CONTEXT")return t==null||t(Vt()),!1;if(n.type==="APPLY_MEDIA_RESUME"){const o=Me(n.seconds);return t==null||t({ok:o}),!1}return n.type==="UPDATE_BROWSER_MEDIA_REF_BADGE"&&(we=!1,re(n.reference||null),t==null||t({ok:!0})),!1})}catch{}let b=null,h=null;function j(e){return mn(e,ue())}async function ze(){const e=await j({type:"LOAD_BROWSER_CAPTURE_META"});if(!(e!=null&&e.ok))throw new Error(String((e==null?void 0:e.error)||i("load_capture_meta_failed")));return e}async function Ke(e){const n=await j({type:"SUBMIT_BROWSER_CAPTURE",payload:e});if(!(n!=null&&n.ok))throw new Error(String((n==null?void 0:n.error)||i("failed_submit_capture")));return n}async function kt(){const e=await j({type:"CAPTURE_VISIBLE_TAB"});if(!(e!=null&&e.ok)||!(e!=null&&e.dataUrl)){const n=new Error(String((e==null?void 0:e.error)||i("failed_capture_tab")));throw n.code=(e==null?void 0:e.errorCode)||"",n}return e.dataUrl}async function $e(e){let n={};try{const r=await ce.storage.local.get(F);n=(r==null?void 0:r[F])||{}}catch{n={}}return on(n,e)}async function qe(e){try{await ce.storage.local.set({[F]:{noteTypeName:String((e==null?void 0:e.noteTypeName)||""),deckName:String((e==null?void 0:e.deckName)||""),priority:Number((e==null?void 0:e.priority)??ee),tagsText:String((e==null?void 0:e.tagsText)||""),mappingsByNoteType:(e==null?void 0:e.mappingsByNoteType)||{},linkToPassage:(e==null?void 0:e.linkToPassage)!==!1}})}catch{}}async function He(e="",n=[]){const r=(h==null?void 0:h.meta)||await ze();if(!Array.isArray(r==null?void 0:r.noteTypes)||r.noteTypes.length===0)throw new Error(i("no_note_types"));if(!Array.isArray(r==null?void 0:r.deckNames)||r.deckNames.length===0)throw new Error(i("no_decks"));const t=(h==null?void 0:h.form)||await $e(r);return h={mode:"snapshot",meta:r,form:t,context:{url:window.location.href||"",title:document.title||"",selectedText:gt("snapshot",e,I()),profileToken:r.profileToken||""},snapshots:Array.isArray(n)?n:[],statusKind:"",statusText:"",submitting:!1},h}async function At(e="",n=[]){const r=await He(e,n),t=bt({...r.context,snapshots:r.snapshots.map(d=>({filename:d.filename,base64:d.base64}))},r.form),a=xt(t);if(!a.ok)throw new Error(i("continue_choose_fields",{error:z(a)}));const o=await Ke(t);if(yt(o)==="duplicate")throw new Error(i("capture_duplicate_found"));return await qe(r.form),o}function Ve(e){const n=e instanceof Element?e:(e==null?void 0:e.parentElement)||null;return n?n.closest("input, textarea, select")?!0:!!n.closest('[contenteditable=""], [contenteditable="true"]'):!1}function be(){return!!b}function Nt(e){return String((e==null?void 0:e.code)||"").toLowerCase()==="keyx"}function Ae(e){var t;const n=b==null?void 0:b.shell,r=e==null?void 0:e.target;if(!(!n||!(r instanceof Node)||!n.contains(r))){if(e.type==="keydown"&&((t=b==null?void 0:b.handleTagAutocompleteKeyDown)!=null&&t.call(b,e))){e.stopPropagation();return}if(e.type==="keydown"&&e.key==="Escape"){e.preventDefault(),e.stopPropagation(),W();return}if(e.type==="keydown"&&pn(e,{form:b.form,submitting:h==null?void 0:h.submitting})){e.stopPropagation();return}e.stopPropagation()}}function xe(){if(b)return b;const e=document.createElement("div");e.id=Z,e.style.all="initial";const n=e.attachShadow({mode:"open"});document.documentElement.appendChild(e),n.addEventListener("keydown",Ae,!0),n.addEventListener("keypress",Ae,!0),n.addEventListener("keyup",Ae,!0);const r=document.createElement("style");r.textContent=`
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
    `,n.appendChild(r);const t=document.createElement("div");return t.className="shell",n.appendChild(t),b={host:e,shadow:n,shell:t},b}function W(){var e;(e=b==null?void 0:b.host)!=null&&e.isConnected&&b.host.remove(),b=null,h=null}function Xe(){const e=xe();e.handleTagAutocompleteKeyDown=null,e.form=null,e.shell.textContent=""}function Lt(e,n,r){const t=document.createElement("div");t.className="tag-autocomplete";const a=document.createElement("input");a.id="incremento-browser-capture-tags",a.type="text",a.value=String(e||""),a.placeholder="tag-one tag-two",a.autocomplete="off",a.spellcheck=!1,a.setAttribute("role","combobox"),a.setAttribute("aria-autocomplete","list");const o=document.createElement("div");o.id="incremento-browser-capture-tag-suggestions",o.className="tag-suggestions",o.setAttribute("role","listbox"),o.hidden=!0,a.setAttribute("aria-controls",o.id),a.setAttribute("aria-expanded","false");const d=fn(n);let l=!1,s=0,c=[];const u=()=>{var g;Array.from(o.children).forEach((x,v)=>{x.classList.toggle("is-active",v===s),x.setAttribute("aria-selected",v===s?"true":"false")}),!o.hidden&&c.length>0?(a.setAttribute("aria-activedescendant",`${o.id}-${s}`),(g=o.children[s])==null||g.scrollIntoView({block:"nearest"})):a.removeAttribute("aria-activedescendant")},f=()=>{const g=a.selectionStart??a.value.length;if(c=gn(d,a.value,g),s=c.length>0?Math.min(s,c.length-1):0,o.textContent="",o.hidden=!l||c.length===0,a.setAttribute("aria-expanded",o.hidden?"false":"true"),o.hidden){u();return}c.forEach((x,v)=>{const p=document.createElement("button");p.id=`${o.id}-${v}`,p.type="button",p.setAttribute("role","option"),p.setAttribute("aria-selected",v===s?"true":"false"),p.className=v===s?"is-active":"",p.textContent=x,p.addEventListener("mouseenter",()=>{s=v,u()}),p.addEventListener("mousedown",S=>{S.preventDefault(),k(x)}),o.appendChild(p)}),u()},k=g=>{const x=hn(a.value,g,a.selectionStart??a.value.length,a.selectionEnd??a.value.length);a.value=x.value,r(x.value),l=!1,s=0,a.focus(),a.setSelectionRange(x.cursor,x.cursor),f()},A=g=>{if(g.target!==a)return!1;if(g.key==="Escape"&&l)return g.preventDefault(),l=!1,f(),!0;if(!c.length)return!1;if(g.key==="ArrowDown"||g.key==="ArrowUp"){g.preventDefault();const x=g.key==="ArrowDown"?1:-1;if(!l)l=!0,s=x>0?0:c.length-1;else return s=(s+x+c.length)%c.length,u(),!0;return f(),!0}return l&&(g.key==="Enter"||g.key==="Tab")?(g.preventDefault(),k(c[s]),!0):!1};return a.addEventListener("input",()=>{r(a.value),s=0,l=!0,f()}),a.addEventListener("focus",()=>{l=!0,f()}),a.addEventListener("click",()=>{s=0,l=!0,f()}),a.addEventListener("select",f),a.addEventListener("blur",()=>{l=!1,f()}),t.appendChild(a),t.appendChild(o),{element:t,handleKeyDown:A}}function Mt(e,n){const r=document.createElement("div");r.className="snapshots";for(const t of n){const a=document.createElement("div");a.className="snapshot-card";const o=document.createElement("img");o.src=t.dataUrl,o.alt=t.filename,a.appendChild(o);const d=document.createElement("div");d.className="snapshot-footer";const l=document.createElement("span");l.textContent=t.filename,d.appendChild(l);const s=document.createElement("button");s.type="button",s.textContent=i("remove"),s.addEventListener("click",()=>{h.snapshots=h.snapshots.filter(c=>c.id!==t.id),H()}),d.appendChild(s),a.appendChild(d),r.appendChild(a)}return r}async function H(){var pt;const e=xe(),{shell:n,shadow:r}=e;e.refreshLanguage=()=>{H()};const t=h;Xe();const a=document.createElement("div");a.className="backdrop",a.addEventListener("click",()=>W()),n.appendChild(a);const o=document.createElement("section");o.className="panel",o.setAttribute("role","dialog"),o.setAttribute("aria-modal","true"),o.setAttribute("aria-labelledby","incremento-capture-title"),n.appendChild(o);const d=document.createElement("p");d.className="eyebrow",d.textContent=t.mode==="snapshot"?i("browser_snapshot"):i("browser_selection"),o.appendChild(d);const l=document.createElement("h2");l.id="incremento-capture-title",l.textContent=i("send_capture_anki"),o.appendChild(l);const s=document.createElement("p");s.className="lead",s.textContent=t.mode==="snapshot"?Fe("snapshots_ready",t.snapshots.length,{url:t.context.url}):i("selected_text_from",{url:t.context.url}),o.appendChild(s);const c=document.createElement("form");c.noValidate=!0,e.form=c;const u=document.createElement("div");u.className="grid",c.appendChild(u);const f=(m,y,w=!1,N="")=>{const _=document.createElement("div");_.className=`field${w?" full":""}`;const O=document.createElement("label");O.textContent=m;const se=y.matches("input,textarea,select,button")?y:y.querySelector("input,textarea,select,button")||y,mt=se.id||`incremento-capture-field-${u.children.length}`;if(se.id=mt,O.htmlFor=mt,_.appendChild(O),_.appendChild(y),N){const De=document.createElement("p");De.className="field-note",De.textContent=N,_.appendChild(De)}return _},k=document.createElement("select");for(const m of t.meta.noteTypes){const y=document.createElement("option");y.value=m.name,y.textContent=m.name,k.appendChild(y)}k.value=t.form.noteTypeName,k.addEventListener("change",()=>{var w;const m=t.meta.noteTypes.find(N=>N.name===k.value),y=ln((w=t.form.mappingsByNoteType)==null?void 0:w[k.value],(m==null?void 0:m.fields)||[]);t.form=he(t.form,k.value,y),H()}),u.appendChild(f(i("note_type"),k));const A=document.createElement("select");for(const m of t.meta.deckNames){const y=document.createElement("option");y.value=m,y.textContent=m,A.appendChild(y)}A.value=t.form.deckName,A.addEventListener("change",()=>{t.form.deckName=A.value}),u.appendChild(f(i("deck"),A));const g=Lt(t.form.tagsText,t.meta.tagNames,m=>{t.form.tagsText=m});b.handleTagAutocompleteKeyDown=g.handleKeyDown,u.appendChild(f(i("tags"),g.element,!0,i("tag_hint")));const x=document.createElement("div");x.style.display="grid",x.style.gridTemplateColumns="1fr auto",x.style.gap="10px",x.style.alignItems="center";const v=document.createElement("input");v.type="range",v.min="0",v.max="100",v.step="0.1",v.value=String(t.form.priority??ee);const p=document.createElement("input");p.type="number",p.setAttribute("aria-label",i("priority")),p.min="0",p.max="100",p.step="0.1",p.style.width="92px",p.value=String(t.form.priority??ee);const S=m=>{const y=Number(m),w=Number.isFinite(y)?Math.min(100,Math.max(0,y)):ee;t.form.priority=Number(w.toFixed(4)),v.value=String(t.form.priority),p.value=String(t.form.priority)};v.addEventListener("input",()=>S(v.value)),p.addEventListener("change",()=>S(p.value)),x.appendChild(v),x.appendChild(p),u.appendChild(f(i("priority"),x));const P=["",...((pt=t.meta.noteTypes.find(m=>m.name===t.form.noteTypeName))==null?void 0:pt.fields)||[]],D=(m,y)=>{const w=document.createElement("select");for(const N of P){const _=document.createElement("option");_.value=N,_.textContent=N||i("do_not_insert"),w.appendChild(_)}return w.value=P.includes(m)?m:"",w.addEventListener("change",()=>{y(w.value)}),w},Y=!!t.context.selectedText;u.appendChild(f(i("page_title_field"),D(t.form.fieldMappings.titleField,m=>{t.form=he(t.form,t.form.noteTypeName,{...t.form.fieldMappings,titleField:m})}),!1,i("page_title_field_note"))),u.appendChild(f(i("selected_text_field"),D(t.form.fieldMappings.selectedTextField,m=>{t.form=he(t.form,t.form.noteTypeName,{...t.form.fieldMappings,selectedTextField:m})}),!1,Y?i("chars_ready",{count:t.context.selectedText.length}):i("no_text_added"))),u.appendChild(f(i("source_url_field"),D(t.form.fieldMappings.urlField,m=>{t.form=he(t.form,t.form.noteTypeName,{...t.form.fieldMappings,urlField:m})}),!1,i("source_url_note"))),u.appendChild(f(i("snapshot_field"),D(t.form.fieldMappings.snapshotField,m=>{t.form=he(t.form,t.form.noteTypeName,{...t.form.fieldMappings,snapshotField:m})}),!0,t.snapshots.length>0?Fe("snapshots_selected",t.snapshots.length):i("no_snapshots")));const B=document.createElement("input");B.type="text",B.maxLength=1e3,B.value=t.context.title,B.addEventListener("input",()=>{t.context.title=B.value}),u.appendChild(f(i("capture_edit_title"),B,!0));const L=document.createElement("input");L.type="checkbox",L.checked=t.form.linkToPassage!==!1,L.style.width="auto",L.addEventListener("change",()=>{t.form.linkToPassage=L.checked}),u.appendChild(f(i("capture_link_passage"),L,!0,i("capture_passage_hint")));const me=document.createElement("textarea");if(me.value=t.context.selectedText,me.placeholder=t.mode==="snapshot"?i("add_text_snapshots"):i("selected_text_edit"),me.addEventListener("input",()=>{t.context.selectedText=me.value}),u.appendChild(f(t.mode==="snapshot"?i("text_to_add"):i("selected_text"),me,!0,i("inserted_text_note"))),t.snapshots.length>0){const m=document.createElement("div");m.className="field full";const y=document.createElement("label");y.textContent=i("snapshots"),m.appendChild(y),m.appendChild(Mt(r,t.snapshots)),u.appendChild(m)}const U=document.createElement("section");if(U.dataset.capturePreview="true",U.tabIndex=-1,U.setAttribute("aria-label",i("capture_field_preview")),U.hidden=!t.preview,t.preview){const m=document.createElement("h3");m.textContent=i("capture_field_preview"),U.appendChild(m);const y=document.createElement("p");y.className="field-note",y.textContent=i(t.preview.uniqueTitle?"capture_preview_unique_title":"capture_preview_hint"),U.appendChild(y);const w=document.createElement("iframe");w.title=i("capture_field_preview"),w.setAttribute("sandbox",""),w.setAttribute("referrerpolicy","no-referrer"),w.srcdoc=sn(t.preview.fields),w.style.cssText="width:100%;height:300px;border:1px solid #d6cbb9;border-radius:12px;background:white",U.appendChild(w);const N=document.createElement("a");try{const _=new URL(t.preview.sourceLink);if(!/^https?:$/.test(_.protocol)||_.username||_.password)throw new Error;N.href=_.href,N.target="_blank",N.rel="noopener noreferrer",N.textContent=i("capture_source_link",{title:t.preview.sourceTitle}),U.appendChild(N)}catch{}}c.appendChild(U);const J=document.createElement("div");J.hidden=!t.duplicate,J.setAttribute("role","status");const dt=document.createElement("p");dt.textContent=i("capture_duplicate_found"),J.appendChild(dt);const ae=document.createElement("button");ae.dataset.captureOpenExisting="true",ae.type="button",ae.className="secondary-btn",ae.textContent=i("capture_open_existing"),ae.addEventListener("click",()=>void Se("open_existing")),J.appendChild(ae);const fe=document.createElement("button");fe.type="button",fe.className="secondary-btn",fe.textContent=i("capture_create_another"),fe.addEventListener("click",()=>void Se("create",!0)),J.appendChild(fe),c.appendChild(J);const ut=()=>{t.preview=null,t.duplicate=null,U.hidden=!0,J.hidden=!0};c.addEventListener("input",ut),c.addEventListener("change",ut);const ge=document.createElement("p");ge.setAttribute("role","status"),ge.setAttribute("aria-live","polite"),ge.className=`status${t.statusKind?` ${t.statusKind}`:""}`,ge.textContent=t.statusValidation?z(t.statusValidation):t.statusCode?i(t.statusCode):t.statusText,c.appendChild(ge);const oe=document.createElement("div");if(oe.className="actions",t.snapshots.length>0){const m=document.createElement("button");m.type="button",m.className="ghost-btn",m.textContent=i("capture_more"),m.addEventListener("click",()=>Le(t.snapshots)),oe.appendChild(m)}const ie=document.createElement("button");ie.type="button",ie.className="secondary-btn",ie.textContent=i("capture_preview"),ie.disabled=!!t.submitting,ie.addEventListener("click",()=>void Se("preview")),oe.appendChild(ie);const le=document.createElement("button");le.type="button",le.className="secondary-btn",le.textContent=i("language_cancel"),le.addEventListener("click",()=>W()),oe.appendChild(le);const Q=document.createElement("button");Q.type="submit",Q.setAttribute("aria-keyshortcuts","Enter"),Q.className="primary-btn",Q.textContent=t.submitting?i("saving"):i("create_note"),Q.disabled=!!t.submitting,oe.appendChild(Q),c.appendChild(oe);async function Se(m="create",y=!1){if(t.submitting)return;S(p.value);const w=bt({...t.context,snapshots:t.snapshots.map(_=>({filename:_.filename,base64:_.base64}))},t.form);w.action=m,w.allowDuplicate=y;const N=xt(w);if(!N.ok){t.statusKind="error",t.statusCode="",t.statusValidation=N,t.statusText=z(N),H();return}t.submitting=!0,t.statusKind="",t.statusValidation=null,t.statusCode=m==="preview"?"capture_preview_loading":m==="open_existing"?"capture_opening_existing":"creating_note",t.statusText=i(t.statusCode),H();try{const _=await Ke(w);if(h!==t||!b)return;const O=yt(_);if(O==="preview"||O==="duplicate"){t.submitting=!1,t.statusCode="",t.statusText="",t.preview=O==="preview"?_:null,t.duplicate=O==="preview"?_.duplicate:_,await H();const se=b==null?void 0:b.shadow.querySelector(O==="preview"?"[data-capture-preview]":"[data-capture-open-existing]");se==null||se.focus();return}if(O==="error")throw new Error(i("create_note_failed"));if(await qe(t.form),h!==t||!b)return;E(O==="opened"?i("capture_existing_opened"):i("created_note",{type:_.noteTypeName,deck:_.deckName})),W()}catch(_){if(h!==t||!b)return;t.submitting=!1,t.statusKind="error",t.statusValidation=null,t.statusCode="",t.statusText=(_==null?void 0:_.message)||i("create_note_failed"),H()}}if(c.addEventListener("submit",m=>{m.preventDefault(),Se()}),t.submitting){for(const m of c.querySelectorAll("input,select,textarea,button"))m.disabled=!0;le.disabled=!1}o.appendChild(c),cn(e,Q)}function Bt(e){return new Promise((n,r)=>{const t=new Image;t.onload=()=>n(t),t.onerror=()=>r(new Error(i("failed_decode_screenshot"))),t.src=e})}async function It(e,n){const r=await Bt(e),t=r.width/window.innerWidth,a=r.height/window.innerHeight,o=Math.max(0,Math.round(n.x*t)),d=Math.max(0,Math.round(n.y*a)),l=Math.max(1,Math.round(n.width*t)),s=Math.max(1,Math.round(n.height*a)),c=document.createElement("canvas");return c.width=l,c.height=s,c.getContext("2d").drawImage(r,o,d,l,s,0,0,l,s),c.toDataURL("image/png")}function Pt(e){const n=String(e||""),r=n.indexOf(",");return r>=0?n.slice(r+1):n}function Ne(e){const n=Math.abs(e.width),r=Math.abs(e.height);return{x:e.width>=0?e.x:e.x-n,y:e.height>=0?e.y:e.y-r,width:n,height:r}}function je(e=2){return new Promise(n=>{const r=Math.max(1,Number(e)||1);let t=0;const a=()=>{if(t+=1,t>=r){n();return}requestAnimationFrame(a)};requestAnimationFrame(a)})}function Dt(e,n){if(!(e instanceof Element))return!1;const r=window.getComputedStyle(e),t=n==="x"?r.overflowX:r.overflowY;return/(auto|scroll|overlay)/.test(String(t||""))?n==="x"?e.scrollWidth>e.clientWidth:e.scrollHeight>e.clientHeight:!1}function Ge(e,n){let r=e instanceof Element?e:null;for(;r;){if(Dt(r,n))return r;r=r.parentElement}const t=document.scrollingElement;return t instanceof Element?t:document.documentElement}function Ot(e,n){var c;if(!e)return;const r=((c=n==null?void 0:n.style)==null?void 0:c.pointerEvents)||"";n!=null&&n.style&&(n.style.pointerEvents="none");let t=null;try{t=document.elementFromPoint(e.clientX,e.clientY)}finally{n!=null&&n.style&&(n.style.pointerEvents=r)}const a=Number(e.deltaX)||0,o=Number(e.deltaY)||0,d=a?Ge(t,"x"):null,l=o?Ge(t,"y"):null,s=document.scrollingElement instanceof Element?document.scrollingElement:document.documentElement;a&&(d||s).scrollBy({left:a,top:0,behavior:"auto"}),o&&(l||s).scrollBy({left:0,top:o,behavior:"auto"})}async function Ft(e,n=[]){if(n.length>=Ce)throw new Error(i("too_many_snapshots",{count:Ce}));const r=xe();vt(),r.shell.style.display="none";try{await je(2);const t=await kt(),a=_t(t,{maxBytes:dn});if(!a.ok)throw new Error(z(a));const o=Ne(e),d=await It(t,o),l=_t(d,{maxBytes:un});if(!l.ok)throw new Error(z(l));return{id:`${Date.now()}-${n.length}-${Math.random().toString(16).slice(2,8)}`,filename:`browser-capture-${n.length+1}.png`,dataUrl:d,base64:Pt(d)}}finally{b!=null&&b.shell&&(b.shell.style.display="",await je(1))}}function Le(e=[]){var v;const n=xe();Xe();const r=e.length>0&&((v=h==null?void 0:h.context)==null?void 0:v.selectedText)||"";h={mode:"snapshot",meta:(h==null?void 0:h.meta)||null,form:(h==null?void 0:h.form)||null,context:{url:window.location.href||"",title:document.title||"",selectedText:r},snapshots:[...e],statusKind:"",statusText:"",submitting:!1};const t=n.shell,a=document.createElement("div");a.className="capture-shell",t.appendChild(a);const o=document.createElement("div");o.className="capture-toolbar";const d=p=>{o.replaceChildren();const S=document.createElement("strong");S.textContent=i("snapshot_mode"),o.appendChild(S);const T=document.createElement("span");T.textContent=i(p),o.appendChild(T);const P=document.createElement("span");P.className="spacer",o.appendChild(P)};d("snapshot_mode_intro"),t.appendChild(o);const l=[...e];let s=null,c=null,u=!1;const f=()=>{d("snapshot_mode_hint");const p=document.createElement("span");p.textContent=u?i("capturing"):Fe("snapshot_ready",l.length),o.appendChild(p);const S=document.createElement("button");S.type="button",S.className="toolbar-btn",S.textContent=i("undo"),S.disabled=u||l.length===0,S.addEventListener("click",()=>{l.pop(),f()}),o.appendChild(S);const T=document.createElement("button");T.type="button",T.className="toolbar-btn",T.textContent=i("clear"),T.disabled=u||l.length===0,T.addEventListener("click",()=>{l.splice(0,l.length),f()}),o.appendChild(T);const P=document.createElement("button");P.type="button",P.className="toolbar-btn",P.textContent=i("language_cancel"),P.addEventListener("click",()=>W()),o.appendChild(P);const D=document.createElement("button");D.type="button",D.className="toolbar-btn",D.textContent=i("extract_now"),D.disabled=u||l.length===0,D.addEventListener("click",async()=>{var B;if(!u){if(!l.length){E(i("draw_region_first"));return}u=!0,f();try{const L=await At(((B=h==null?void 0:h.context)==null?void 0:B.selectedText)||"",[...l]);E(i("created_note",{type:L.noteTypeName,deck:L.deckName})),W()}catch(L){u=!1,f(),E((L==null?void 0:L.message)||i("create_note_failed"))}}}),o.appendChild(D);const Y=document.createElement("button");Y.type="button",Y.className="toolbar-btn primary",Y.textContent=i("continue"),Y.addEventListener("click",()=>{var B;if(!u){if(!l.length){E(i("draw_region_first"));return}ye({mode:"snapshot",selectedText:((B=h==null?void 0:h.context)==null?void 0:B.selectedText)||"",snapshots:[...l]})}}),o.appendChild(Y)};n.refreshLanguage=f;const k=(p,S)=>{if(l.length>=Ce){E(i("too_many_snapshots",{count:Ce}));return}c={x:p,y:S,width:0,height:0},s=document.createElement("div"),s.className="selection-rect",s.dataset.label=i("capture_label",{count:l.length+1}),a.appendChild(s)},A=()=>{if(!s||!c)return;const p=Ne(c);Object.assign(s.style,{left:`${p.x}px`,top:`${p.y}px`,width:`${p.width}px`,height:`${p.height}px`})};a.addEventListener("pointerdown",p=>{u||p.button!==0||p.target!==a||(p.preventDefault(),k(p.clientX,p.clientY),A())}),a.addEventListener("pointermove",p=>{c&&(p.preventDefault(),c.width=p.clientX-c.x,c.height=p.clientY-c.y,A())});const g=p=>{c||u||(p.preventDefault(),Ot(p,n.host))};a.addEventListener("wheel",g,{passive:!1}),o.addEventListener("wheel",g,{passive:!1});const x=async()=>{if(!s||!c)return;const p=Ne(c),S=s;if(p.width>=24&&p.height>=24){u=!0,f();try{const T=await Ft(p,l);l.push(T)}catch(T){E((T==null?void 0:T.message)||i("failed_capture_tab"),{action:(T==null?void 0:T.code)==="snapshot_permission_required"?"open_shortcut_settings":""})}}else S.remove();S.remove(),s=null,c=null,u=!1,f()};a.addEventListener("pointerup",()=>{x()}),a.addEventListener("pointercancel",()=>{x()}),f()}async function ye({mode:e,selectedText:n="",snapshots:r=[]}){ne();const t=e==="snapshot"?{}:K(n||I());if(e==="snapshot")await He(n,r);else{const a=(h==null?void 0:h.meta)||await ze();if(!Array.isArray(a==null?void 0:a.noteTypes)||a.noteTypes.length===0)throw new Error(i("no_note_types"));if(!Array.isArray(a==null?void 0:a.deckNames)||a.deckNames.length===0)throw new Error(i("no_decks"));const o=(h==null?void 0:h.form)||await $e(a);h={mode:e,meta:a,form:o,context:{url:window.location.href||"",title:document.title||"",selectedText:gt(e,n,I()),...t,profileToken:a.profileToken||""},snapshots:Array.isArray(r)?r:[],statusKind:"",statusText:"",submitting:!1}}await H()}globalThis.__incrementoTriggerBrowserCapture=e=>{if(String(e||"").trim().toLowerCase()==="snapshot")return Le(),{ok:!0};const r=I();return r?(ye({mode:"selection",selectedText:r,snapshots:[]}).catch(t=>{E((t==null?void 0:t.message)||i("open_capture_failed")),W()}),{ok:!0}):(E(i("select_page_text")),{ok:!1,error:i("select_page_text")})},document.addEventListener("keydown",e=>{if(!e.altKey||!Nt(e)||be()||Ve(e.target))return;if(e.metaKey){e.preventDefault(),e.stopPropagation(),en(j,E).catch(()=>{E(i("snapshot_shortcut_unassigned"),{action:"open_shortcut_settings"})});return}if(e.ctrlKey||e.shiftKey)return;const n=I();n&&(e.preventDefault(),e.stopPropagation(),ye({mode:"selection",selectedText:n,snapshots:[]}).catch(r=>{E((r==null?void 0:r.message)||i("open_capture_failed")),W()}))},!0),document.addEventListener("contextmenu",e=>{const n=We(e.target);V=ke(n)},!0),document.addEventListener("click",e=>{if(!R.modifierClickEnabled||e.defaultPrevented||Number(e.button)!==0||be()||Ve(e.target))return;const n=We(e.target);if(!n||!tn(e,R))return;const r=ke(n);if(!r)return;R.navigateAfterSave||e.preventDefault();const t=ue();t==null||t.sendMessage({type:"SAVE_CLICKED_LINK_AS_WEBPAGE",url:r.url,title:r.title,sourcePageUrl:window.location.href||"",sourcePageTitle:document.title||""},a=>{var o,d;(d=(o=ce)==null?void 0:o.runtime)==null||d.lastError})},!0),document.addEventListener("selectionchange",ne,!0),document.addEventListener("mouseup",ne,!0),document.addEventListener("keyup",ne,!0),document.addEventListener("keydown",e=>{e.key==="Escape"&&be()&&(e.preventDefault(),e.stopPropagation(),W())},!0);function Wt(e){try{const n=new URL(e),r=n.searchParams.get("v");if(r)return r;const t=n.pathname.split("/").filter(Boolean);if(n.hostname==="youtu.be"&&t[0])return t[0];if((t[0]==="shorts"||t[0]==="live"||t[0]==="embed")&&t[1])return t[1]}catch{}return""}function Ut(e){const n=String(e||"").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);return n?n[1]:""}function Rt(){const e=window.location.href||"",n=window.location.hostname||"";return n.includes("youtube.com")||n==="youtu.be"?{provider:"youtube",videoId:Wt(e)}:n.includes("vimeo.com")?{provider:"vimeo",videoId:Ut(e)}:{provider:"",videoId:""}}function Ye(e){try{const r=new URL(e).searchParams.get("inc_card_id")||"",t=Number(r);if(Number.isFinite(t)&&t>0)return Math.floor(t)}catch{}return 0}function zt(e){const n=String(e||"").replace(/^#/,"").trim();if(!n)return"";const t=n.indexOf("__incremento_resume__=1");return t<0?n:n.slice(0,t).replace(/[&?]+$/,"")}function Kt(e){try{const n=new URL(e);n.searchParams.delete("inc_card_id"),n.searchParams.delete("inc_track_web"),n.searchParams.delete("inc_resume_sec"),n.searchParams.delete("inc_resume_media");const r=zt(n.hash);return n.hash=r?`#${r}`:"",n.toString()}catch{return String(e||"")}}function $t(e){try{const n=new URL(e),r=String(n.searchParams.get("inc_track_web")||"").trim().toLowerCase();return r==="1"||r==="true"||r==="yes"||r==="on"}catch{return!1}}function qt(){if(window.top!==window)return;const e=window.location.href||"";if(!e||!/inc_(card_id|track_web|resume_sec|resume_media)|__incremento_resume__=1/.test(e))return;const n=Kt(e);if(!(!n||n===e))try{history.replaceState(history.state,document.title||"",n),Pe=n}catch{}}function Je(){const e=Array.from(document.querySelectorAll("video"));return e.length===0?null:(e.sort((n,r)=>{const t=(n.videoWidth||0)*(n.videoHeight||0);return(r.videoWidth||0)*(r.videoHeight||0)-t}),e[0])}function Me(e,n=12){const r=Math.max(0,Math.floor(Number(e)||0));if(r<=0)return!1;const t=Je();if(!t)return n>0&&window.setTimeout(()=>Me(r,n-1),500),!1;try{return t.currentTime=r,E(i("resumed_to",{seconds:r})),!0}catch{return n>0&&window.setTimeout(()=>Me(r,n-1),500),!1}}function _e(){var d,l;const e=window.location.href||"",{provider:n,videoId:r}=Rt(),t=Je(),a=n?e:String((t==null?void 0:t.currentSrc)||(t==null?void 0:t.src)||"").trim(),o=String(((d=t==null?void 0:t.getAttribute)==null?void 0:d.call(t,"title"))||((l=t==null?void 0:t.getAttribute)==null?void 0:l.call(t,"aria-label"))||document.title||"").trim();return{provider:n,videoId:r,video:t,mediaUrl:a,mediaTitle:o}}function Ht(){const{provider:e,video:n}=_e();let r=-1,t=!1;if(n&&(r=Math.max(0,Math.floor(Number(n.currentTime)||0)),t=!0),e==="youtube"&&r<=0){const a=Ie();a>=0&&(r=a,t=!0)}if(e==="vimeo"&&r<=0){const a=Be();a>=0&&(r=a,t=!0)}return{found:t,seconds:t?Math.max(0,r):0}}function Vt(){const e=window.location.href||"",{provider:n,videoId:r,mediaUrl:t,mediaTitle:a}=_e(),o=Ht();return{ok:!0,pageUrl:e,pageTitle:document.title||"",provider:n,videoId:r,mediaUrl:t,mediaTitle:a,hasDetectedTime:!!o.found,seconds:Math.max(0,Math.floor(Number(o.seconds)||0)),timeText:o.found?Re(o.seconds):""}}function Qe(e){const n=String(e||"").trim();if(!n)return-1;const r=n.split(":").map(t=>t.trim());return r.every(t=>/^\d+$/.test(t))?r.length===2?Number(r[0])*60+Number(r[1]):r.length===3?Number(r[0])*3600+Number(r[1])*60+Number(r[2]):-1:-1}function Be(){const e=Array.from(document.querySelectorAll('[data-progress-bar-timecode="true"], [class*="Timecode_module_timecode__"]'));for(const n of e){const r=String((n==null?void 0:n.textContent)||"").trim(),t=Qe(r);if(t>=0)return t}return-1}function Ie(){const e=Array.from(document.querySelectorAll(".ytp-time-current, [class*='ytp-time-current']"));for(const n of e){const r=String((n==null?void 0:n.textContent)||"").trim(),t=Qe(r);if(t>=0)return t}return-1}async function Ze(){try{const e=await j({type:"GET_LINKED_CARD_CONTEXT",url:window.location.href||""});if(!(e!=null&&e.linked)||Number(e.cardId)<=0){re(null);return}const n=await j({type:"LOAD_BROWSER_MEDIA_REF"});if(!(n!=null&&n.ok)||!(n!=null&&n.hasReference)){re(null);return}re(n)}catch{re(null)}}let et=-1,tt=0,nt=-1,rt=0,we=!1,pe=!0,Ee=null,Pe=window.location.href||"";function ve(){pe=!1,Ee!==null&&(clearInterval(Ee),Ee=null)}function at(e){if(!pe)return!1;try{const n=ue();return n!=null&&n.id?(n.sendMessage(e,()=>{try{const r=n==null?void 0:n.lastError;r&&/context invalidated/i.test(String(r.message||""))&&ve()}catch{ve()}}),!0):(ve(),!1)}catch{return ve(),!1}}function ot(){if(!pe){X(!1);return}try{const e=ue();if(!(e!=null&&e.id)){X(!1);return}e.sendMessage({type:"GET_TRACKING_STATUS",url:window.location.href||""},n=>{try{if(e==null?void 0:e.lastError){X(!1);return}}catch{X(!1);return}X(!!(n!=null&&n.tracked),String((n==null?void 0:n.mode)||""))})}catch{X(!1)}}function $(e=!1,n=!1){if(!pe)return;const{provider:r,videoId:t,video:a}=_e();if(!r)return;let o=-1;if(a&&(o=Math.max(0,Math.floor(Number(a.currentTime)||0))),r==="youtube"&&o<=0){const l=Ie();l>=0&&(o=l)}if(r==="vimeo"&&o<=0){const l=Be();l>=0&&(o=l)}if(o<0)return;const d=Date.now();!e&&o===et&&d-tt<4e3||(et=o,tt=d,at({type:"heartbeat",provider:r,videoId:t,cardId:Ye(window.location.href||""),flush:!!n,seconds:o,url:window.location.href||"",title:document.title||""}))}function G(e=!1,n=!1){if(!pe)return;const r=window.location.href||"",{provider:t,videoId:a,video:o,mediaUrl:d,mediaTitle:l}=_e();if(!o&&!t)return;let s=-1;if(o&&(s=Math.max(0,Math.floor(Number(o.currentTime)||0))),t==="youtube"&&s<=0){const u=Ie();u>=0&&(s=u)}if(t==="vimeo"&&s<=0){const u=Be();u>=0&&(s=u)}if(s<0)return;const c=Date.now();!e&&s===nt&&c-rt<4e3||(nt=s,rt=c,at({type:"web_media_heartbeat",provider:t,videoId:a,cardId:Ye(r),trackEnabled:$t(r),flush:!!n,seconds:s,url:r,mediaUrl:d,mediaTitle:l,title:document.title||""}))}Ee=window.setInterval(()=>{$(!1,!1),G(!1,!1)},1e3),window.setInterval(()=>{const e=window.location.href||"";e!==Pe&&(Pe=e,we=!1,ot(),Ze())},750),window.addEventListener("pagehide",()=>{$(!0,!0),G(!0,!0)},{capture:!0}),window.addEventListener("beforeunload",()=>{$(!0,!0),G(!0,!0)},{capture:!0}),document.addEventListener("visibilitychange",()=>{document.visibilityState==="hidden"&&($(!0,!0),G(!0,!0))}),document.addEventListener("timeupdate",()=>{$(!1,!1),G(!1,!1)},!0),document.addEventListener("play",()=>{$(!0,!1),G(!0,!1)},!0),document.addEventListener("pause",()=>{$(!0,!0),G(!0,!0)},!0),document.addEventListener("ended",()=>$(!0,!0),!0),window.setTimeout(()=>$(!0,!1),1200),window.setTimeout(qt,1200),window.setTimeout(ot,300),window.setTimeout(()=>{Ze()},320),window.__incrementoContentScriptState={...window.__incrementoContentScriptState||{},version:q,ready:!0}})();
