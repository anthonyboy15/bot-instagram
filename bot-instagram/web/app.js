// ===== Panel de contenido (Fase 1.5) — previews fieles + stickers + musica =====

const PIXEL = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==";
const MESES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];
const EMOJIS = ["😍","😂","😀","🔥","😡","😱","😢","🙌","❤️","👏"];

let plan = null;
let perfil = { usuario: "", foto_url: null };
let catActiva = "publicaciones";
let guardarTimer = null;

const $ = (s) => document.querySelector(s);

// ---------- API ----------
async function api(metodo, ruta, { json, form } = {}) {
  const opt = { method: metodo, headers: {}, credentials: "same-origin" };
  if (json !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(json); }
  if (form !== undefined) { opt.body = form; }
  const r = await fetch(ruta, opt);
  if (r.status === 401) { mostrarLogin(); throw new Error("401"); }
  if (!r.ok) { let d = ""; try { d = (await r.json()).detail; } catch (e) {} throw new Error(d || ("Error " + r.status)); }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r.text();
}

// ---------- Utilidades ----------
function esc(t) { return (t || "").toString().replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function avatar() { return perfil.foto_url || PIXEL; }
function usuario() { return perfil.usuario || "tu_usuario"; }
function fechaTexto(fecha, hora) {
  if (!fecha) return hora || "";
  const p = fecha.split("-");
  if (p.length === 3) return `${parseInt(p[2],10)} ${MESES[parseInt(p[1],10)-1]}` + (hora ? ` · ${hora}` : "");
  return fecha + (hora ? ` · ${hora}` : "");
}
function mostrarAviso(txt) {
  const a = $("#aviso"); a.textContent = txt; a.classList.remove("oculto");
  clearTimeout(a._t); a._t = setTimeout(() => a.classList.add("oculto"), 1600);
}
function autoguardar() {
  clearTimeout(guardarTimer);
  guardarTimer = setTimeout(async () => {
    try { await api("PUT", "/api/plan", { json: plan }); mostrarAviso("Guardado"); }
    catch (e) { mostrarAviso("No se pudo guardar"); }
  }, 800);
}

// ---------- Badges ----------
const badgeAuto = `<span class="badge-pub badge-auto"><span class="dot dot-auto"></span>Automático</span>`;
const badgeIG = `<span class="badge-pub badge-ig"><span class="dot dot-ig"></span>Lo agregas en IG</span>`;

// ---------- Normalizar (rellena campos nuevos / compatibilidad) ----------
function musicaVacia() { return { titulo:"", artista:"", momento:"", por_que:"" }; }
function normalizarPlan(p) {
  if (!p || p.vacio) return p;
  (p.publicaciones || []).forEach(x => {
    if (x.ubicacion == null) x.ubicacion = "";
    if (!x.musica) x.musica = musicaVacia();
  });
  (p.historias || []).forEach(x => {
    if (!x.sticker) {
      const t = x.interaccion || "ninguno";
      x.sticker = {
        tipo: t,
        texto: t === "ninguno" ? "" : (x.idea || ""),
        opciones: t === "encuesta" ? ["Sí","No"] : (t === "cuestionario" ? ["Opción A","Opción B"] : []),
        emoji: t === "control_deslizante" ? "🔥" : ""
      };
    }
    if (!x.musica) x.musica = musicaVacia();
  });
  return p;
}

// ---------- Login ----------
function mostrarLogin() { $("#pantalla-app").classList.add("oculto"); $("#pantalla-login").classList.remove("oculto"); }
async function hacerLogin() {
  const form = new FormData(); form.append("password", $("#clave").value);
  try { await api("POST", "/api/login", { form }); $("#login-error").classList.add("oculto"); await iniciarApp(); }
  catch (e) { const er = $("#login-error"); er.textContent = "Contraseña incorrecta"; er.classList.remove("oculto"); }
}

// ---------- Inicio ----------
async function iniciarApp() {
  perfil = await api("GET", "/api/perfil");
  plan = normalizarPlan(await api("GET", "/api/plan"));
  $("#pantalla-login").classList.add("oculto");
  $("#pantalla-app").classList.remove("oculto");
  renderCabecera(); render();
}
function renderCabecera() {
  $("#perfil-usuario").textContent = usuario();
  $("#perfil-foto").src = avatar();
  let resumen = "Sin plan todavía";
  if (plan && !plan.vacio) {
    const p = (plan.publicaciones||[]).length, h = (plan.historias||[]).length,
          n = (plan.notas||[]).length, i = (plan.instantaneas||[]).length;
    resumen = `${p} publicaciones · ${h} historias · ${n} notas · ${i} instantáneas`;
  }
  $("#plan-resumen").textContent = resumen;
}

// ---------- Render principal ----------
function render() {
  const cont = $("#contenido");
  cont.innerHTML = `<div class="leyenda">
    ${badgeAuto} la app lo publica sola &nbsp; ${badgeIG} la app te lo deja listo
  </div>`;
  if (!plan || plan.vacio) {
    cont.innerHTML += '<div class="vacio">Aún no hay plan.<br>Toca <b>Generar plan</b> para crear el de esta semana.</div>';
    return;
  }
  const lista = plan[catActiva] || [];
  if (!lista.length) { cont.innerHTML += `<div class="vacio">No hay ${catActiva} en el plan.</div>`; return; }
  lista.forEach((pieza, i) => cont.appendChild(crearTarjeta(catActiva, i, pieza)));
}

function crearTarjeta(cat, i, pz) {
  const div = document.createElement("div");
  div.className = "tarjeta";
  if (cat === "publicaciones") div.innerHTML = (pz.tipo === "idea_reel")
      ? vistaVertical("reel", pz) + editorPublicacion(pz)
      : vistaFeed(pz) + editorPublicacion(pz);
  else if (cat === "historias") div.innerHTML = vistaVertical("historia", pz) + editorHistoria(pz);
  else if (cat === "notas") div.innerHTML = vistaNota(pz) + editorNota(pz);
  else if (cat === "instantaneas") div.innerHTML = vistaVertical("instantanea", pz) + editorInstantanea(pz);
  wirePieza(div, cat, i, pz);
  return div;
}

function metaHTML(cat, pz) {
  let badge = cat.slice(0, -1), clase = "badge";
  if (pz.tipo === "idea_reel") { badge = "Reel"; clase += " reel"; }
  else if (pz.tipo) badge = pz.tipo;
  const ia = pz.directiva_imagen && pz.directiva_imagen.tipo === "GENERAR_IA";
  return `<div class="tarjeta-meta"><span class="${clase}">${esc(badge)}${ia ? ' · IA' : ''}</span>
    <span class="cuando">${esc(fechaTexto(pz.fecha, pz.hora))}</span></div>`;
}
function imagenPreview(pz) {
  if (pz.imagen_subida) return `<img src="${esc(pz.imagen_subida)}" alt="" />`;
  const ia = pz.directiva_imagen && pz.directiva_imagen.tipo === "GENERAR_IA";
  return `<div class="ph">${ia ? "Imagen con IA<br>(Fase 2)" : "Sube tu foto<br>desde el editor"}</div>`;
}
function chipMusica(m) {
  if (!m || !m.titulo) return "";
  return `<div class="chip-musica">🎵 <span class="cm-txt">${esc(m.titulo)} · ${esc(m.artista)}</span></div>`;
}

function vistaFeed(pz) {
  const carrusel = pz.tipo === "carrusel" ? `<span class="ig-carrusel">1/2</span>` : "";
  return metaHTML("publicaciones", pz) + `<div class="ig">
    <div class="ig-cab">
      <img class="av" src="${avatar()}" alt="" />
      <div><div class="u">${esc(usuario())}</div><div class="loc ig-loc">${esc(pz.ubicacion || "")}</div></div>
    </div>
    <div class="ig-img">${imagenPreview(pz)}${carrusel}</div>
    <div class="ig-acc"><i>♡</i><i>💬</i><i>🔁</i><i class="der">🔖</i></div>
    <div class="ig-pie">
      <div class="ig-likes">Les gusta a <b>varias personas</b></div>
      <div style="margin-top:3px;"><span class="u">${esc(usuario())}</span> <span class="cap">${esc(pz.caption)}</span></div>
      <div class="ig-hashtags">${esc((pz.hashtags||[]).map(h=>"#"+h).join(" "))}</div>
      ${chipMusica(pz.musica) ? `<div style="margin-top:6px;">${chipMusica(pz.musica)}</div>` : ""}
      <div class="ig-hora">${esc(fechaTexto(pz.fecha, pz.hora))}</div>
    </div>
  </div>`;
}

function stickerPreview(st) {
  if (!st || st.tipo === "ninguno") return "";
  const t = st.tipo, preg = esc(st.texto), ops = st.opciones || [];
  if (t === "encuesta" || t === "cuestionario")
    return `<div class="st-box st-translucida"><div class="preg">${preg}</div>
      <div class="ops">${(ops.length?ops:["",""]).map(o=>`<span>${esc(o)}</span>`).join("")}</div></div>`;
  if (t === "pregunta")
    return `<div class="st-box st-blanca"><div class="preg">${preg||"Hazme una pregunta"}</div>
      <div class="campo">Responder…</div></div>`;
  if (t === "control_deslizante")
    return `<div class="st-box st-blanca st-slider"><div class="preg">${preg}</div>
      <div class="track"><div class="thumb">${esc(st.emoji||"🔥")}</div></div></div>`;
  if (t === "cuenta_regresiva")
    return `<div class="st-box st-cuenta"><div class="preg" style="color:#fff;font-size:11px;text-align:center;">${preg}</div>
      <div class="reloj">02 : 11 : 30</div></div>`;
  return "";
}

function vistaVertical(tipo, pz) {
  const cat = tipo === "historia" ? "historias" : (tipo === "instantanea" ? "instantaneas" : "publicaciones");
  const fondo = pz.imagen_subida ? `<img src="${esc(pz.imagen_subida)}" alt="" />` : (tipo === "reel" ? "▶" : "");
  const overlayTexto = tipo === "reel" ? pz.caption : (pz.texto_en_pantalla || pz.idea || "");
  const marca = tipo === "reel" ? `<div class="reel-marca"><i>♡</i><i>💬</i><i>➤</i></div>` : "";
  const aa = tipo === "instantanea" ? `<div class="instant-aa">Aa</div>` : "";
  const sticker = tipo === "historia" ? stickerPreview(pz.sticker) : "";
  const musica = (tipo === "historia" || tipo === "reel") ? chipMusica(pz.musica) : "";
  return metaHTML(cat, pz) + `<div class="vert ${tipo === "instantanea" ? "instant" : ""}">
    <div class="vert-bg">${fondo}</div>${aa}
    <div class="vert-top">
      <div class="vert-prog"><span class="on"></span><span></span><span></span></div>
      <div class="vert-head"><img class="av" src="${avatar()}" alt="" />
        <span class="u">${esc(usuario())}</span><span class="t">${esc(pz.hora || "")}</span></div>
    </div>
    ${marca}
    <div class="vert-cuerpo">
      ${musica ? `<div style="margin-bottom:8px;">${musica}</div>` : ""}
      <div class="vert-texto">${esc(overlayTexto)}</div>
      ${sticker}
    </div>
  </div>`;
}

function vistaNota(pz) {
  return `<div class="nota-burbuja">${esc(pz.texto)}</div><div class="nota-pie">Nota · ${esc(fechaTexto(pz.fecha))}</div>`;
}

// ---------- Editor de musica ----------
function editorMusica(m) {
  return `<div class="musica">
    <div class="musica-cab">🎵 Música ${badgeIG}</div>
    <input class="m-titulo" placeholder="Canción" value="${esc(m.titulo)}" />
    <input class="m-artista" placeholder="Artista" value="${esc(m.artista)}" />
    <input class="m-momento" placeholder="Desde qué parte (ej: el coro, ~seg 30)" value="${esc(m.momento)}" />
    ${m.por_que ? `<div class="musica-porque">Por qué: ${esc(m.por_que)}</div>` : ""}
    <div class="musica-acc"><button class="btn-borde" disabled>▶ Escuchar (pronto)</button></div>
  </div>`;
}

// ---------- Editor de sticker ----------
function stickerCampos(st) {
  const t = st.tipo, o = st.opciones || [];
  if (t === "encuesta" || t === "cuestionario")
    return `<label>Pregunta</label><input class="s-texto" value="${esc(st.texto)}" />
      <label>Opciones</label><div class="opciones-fila">
        <input class="s-op0" value="${esc(o[0]||"")}" placeholder="Opción 1" />
        <input class="s-op1" value="${esc(o[1]||"")}" placeholder="Opción 2" /></div>`;
  if (t === "pregunta")
    return `<label>Encabezado</label><input class="s-texto" value="${esc(st.texto)}" placeholder="Hazme una pregunta" />`;
  if (t === "control_deslizante")
    return `<label>Pregunta</label><input class="s-texto" value="${esc(st.texto)}" />
      <label>Emoji del slider</label><div class="emoji-fila">
        ${EMOJIS.map(e=>`<button class="s-emoji ${e===st.emoji?"sel":""}" data-e="${e}">${e}</button>`).join("")}</div>`;
  if (t === "cuenta_regresiva")
    return `<label>Título</label><input class="s-texto" value="${esc(st.texto)}" placeholder="Cuenta regresiva" />
      <label>Fecha/hora</label><input class="s-fecha" type="datetime-local" value="${esc((st.opciones||[])[0]||"")}" />`;
  return `<div class="musica-porque">Sin sticker en esta historia.</div>`;
}
function editorSticker(st) {
  const tipos = ["ninguno","encuesta","pregunta","cuestionario","control_deslizante","cuenta_regresiva"];
  return `<div class="editor" style="margin-top:10px;">
    <label>Sticker interactivo ${badgeIG}</label>
    <select class="s-tipo" style="width:100%;padding:10px;background:#000;color:#fff;border:1px solid #262626;border-radius:8px;">
      ${tipos.map(t=>`<option value="${t}" ${st.tipo===t?"selected":""}>${t}</option>`).join("")}
    </select>
    <div class="sticker-campos" style="margin-top:8px;">${stickerCampos(st)}</div>
  </div>`;
}

// ---------- Editores por formato ----------
function editorPublicacion(pz) {
  return `<div class="editor">
    <label>Idea</label><div class="directiva-ia">${esc(pz.idea)}</div>
    <label style="margin-top:8px;">Ubicación ${badgeAuto}</label>
    <input class="f-ubicacion" value="${esc(pz.ubicacion||"")}" placeholder="Ej: Lima, Perú" />
    <label style="margin-top:8px;">Caption ${badgeAuto}</label>
    <textarea class="f-caption">${esc(pz.caption)}</textarea>
    <label style="margin-top:8px;">Hashtags ${badgeAuto}</label>
    <textarea class="f-hashtags" style="min-height:44px;">${esc((pz.hashtags||[]).join(" "))}</textarea>
    ${editorMusica(pz.musica)}
    ${directivaImagen(pz)}
  </div>`;
}
function editorHistoria(pz) {
  return `<div class="editor">
    <label>Idea</label><div class="directiva-ia">${esc(pz.idea)}</div>
    <label style="margin-top:8px;">Texto en pantalla ${badgeIG}</label>
    <textarea class="f-texto" style="min-height:48px;">${esc(pz.texto_en_pantalla)}</textarea>
    ${editorMusica(pz.musica)}
    ${directivaImagen(pz)}
  </div>${editorSticker(pz.sticker)}`;
}
function editorNota(pz) {
  return `<div class="editor"><label>Texto de la nota (máx. 60) ${badgeIG}</label>
    <textarea class="f-nota" maxlength="60" style="min-height:44px;">${esc(pz.texto)}</textarea>
    <div class="contador"><span class="cont">${(pz.texto||"").length}</span>/60</div></div>`;
}
function editorInstantanea(pz) {
  return `<div class="editor">
    <label>Idea del momento</label><textarea class="f-idea" style="min-height:44px;">${esc(pz.idea)}</textarea>
    <label style="margin-top:8px;">Qué captar (foto en vivo, tú la tomas)</label>
    <textarea class="f-desc" style="min-height:44px;">${esc(pz.descripcion_foto)}</textarea>
    ${botonSubir()}</div>`;
}
function directivaImagen(pz) {
  if (!pz.directiva_imagen) return "";
  if (pz.directiva_imagen.tipo === "GENERAR_IA") {
    const yaTiene = !!pz.imagen_subida;
    return `<label style="margin-top:8px;">Prompt de imagen (IA gratis) ${badgeAuto}</label>
      <textarea class="f-prompt" style="min-height:54px;">${esc(pz.directiva_imagen.prompt_ia)}</textarea>
      <div class="editor-fila"><button class="btn-generar-img btn-borde">🎨 ${yaTiene ? "Regenerar imagen" : "Generar imagen"}</button></div>`;
  }
  return `<div class="directiva-ia"><b>Qué fotografiar:</b> ${esc(pz.directiva_imagen.descripcion_foto)}</div>${botonSubir()}`;
}
function botonSubir() {
  return `<div class="editor-fila"><label class="btn-borde">📷 Subir foto
    <input type="file" class="subir" accept="image/*" hidden /></label></div>`;
}

// ---------- Conexión de eventos ----------
function wirePieza(div, cat, i, pz) {
  const on = (sel, ev, fn) => { const el = div.querySelector(sel); if (el) el.addEventListener(ev, fn); };
  const set = (sel, txt) => { const n = div.querySelector(sel); if (n) n.textContent = txt; };

  on(".f-ubicacion", "input", e => { pz.ubicacion = e.target.value; set(".ig-loc", e.target.value); autoguardar(); });
  on(".f-caption", "input", e => { pz.caption = e.target.value; const n = div.querySelector(".cap") || div.querySelector(".vert-texto"); if (n) n.textContent = e.target.value; autoguardar(); });
  on(".f-hashtags", "input", e => { pz.hashtags = e.target.value.split(/\s+/).map(s=>s.replace(/^#/,"")).filter(Boolean); set(".ig-hashtags", pz.hashtags.map(h=>"#"+h).join(" ")); autoguardar(); });
  on(".f-texto", "input", e => { pz.texto_en_pantalla = e.target.value; set(".vert-texto", e.target.value); autoguardar(); });
  on(".f-idea", "input", e => { pz.idea = e.target.value; set(".vert-texto", e.target.value); autoguardar(); });
  on(".f-desc", "input", e => { pz.descripcion_foto = e.target.value; autoguardar(); });
  on(".f-nota", "input", e => { pz.texto = e.target.value; set(".nota-burbuja", e.target.value); set(".cont", e.target.value.length); autoguardar(); });

  // Musica
  on(".m-titulo", "input", e => { pz.musica.titulo = e.target.value; set(".cm-txt", `${e.target.value} · ${pz.musica.artista}`); autoguardar(); });
  on(".m-artista", "input", e => { pz.musica.artista = e.target.value; set(".cm-txt", `${pz.musica.titulo} · ${e.target.value}`); autoguardar(); });
  on(".m-momento", "input", e => { pz.musica.momento = e.target.value; autoguardar(); });

  // Sticker
  on(".s-tipo", "change", e => {
    const t = e.target.value; pz.sticker.tipo = t;
    if (t === "encuesta" && (!pz.sticker.opciones || pz.sticker.opciones.length < 2)) pz.sticker.opciones = ["Sí","No"];
    if (t === "cuestionario" && (!pz.sticker.opciones || pz.sticker.opciones.length < 2)) pz.sticker.opciones = ["Opción A","Opción B"];
    if (t === "control_deslizante" && !pz.sticker.emoji) pz.sticker.emoji = "🔥";
    div.replaceWith(crearTarjeta(cat, i, pz)); autoguardar();
  });
  on(".s-texto", "input", e => { pz.sticker.texto = e.target.value; set(".st-box .preg", e.target.value); autoguardar(); });
  on(".s-op0", "input", e => { pz.sticker.opciones[0] = e.target.value; const sp = div.querySelectorAll(".st-translucida .ops span"); if (sp[0]) sp[0].textContent = e.target.value; autoguardar(); });
  on(".s-op1", "input", e => { pz.sticker.opciones[1] = e.target.value; const sp = div.querySelectorAll(".st-translucida .ops span"); if (sp[1]) sp[1].textContent = e.target.value; autoguardar(); });
  on(".s-fecha", "input", e => { pz.sticker.opciones = [e.target.value]; autoguardar(); });
  div.querySelectorAll(".s-emoji").forEach(b => b.addEventListener("click", () => {
    pz.sticker.emoji = b.dataset.e;
    div.querySelectorAll(".s-emoji").forEach(x => x.classList.remove("sel"));
    b.classList.add("sel");
    const th = div.querySelector(".st-slider .thumb"); if (th) th.textContent = b.dataset.e;
    autoguardar();
  }));

  // Subir foto
  on(".subir", "change", async (e) => {
    if (!e.target.files.length) return;
    const form = new FormData(); form.append("categoria", cat); form.append("indice", i); form.append("foto", e.target.files[0]);
    try { mostrarAviso("Subiendo…"); const r = await api("POST", "/api/subir", { form });
      pz.imagen_subida = r.url; div.replaceWith(crearTarjeta(cat, i, pz)); autoguardar(); mostrarAviso("Foto subida");
    } catch (err) { mostrarAviso("No se pudo subir"); }
  });

  // Prompt de imagen IA (editable)
  on(".f-prompt", "input", e => { pz.directiva_imagen.prompt_ia = e.target.value; autoguardar(); });

  // Generar / regenerar imagen con IA (Pollinations Flux)
  on(".btn-generar-img", "click", async (e) => {
    const btn = e.target;
    const prompt = ((div.querySelector(".f-prompt") || {}).value || pz.directiva_imagen.prompt_ia || "").trim();
    if (!prompt) { mostrarAviso("Escribe un prompt primero"); return; }
    const txt = btn.textContent; btn.disabled = true; btn.textContent = "Generando…";
    try {
      const form = new FormData(); form.append("categoria", cat); form.append("indice", i); form.append("prompt", prompt);
      const r = await api("POST", "/api/generar-imagen", { form });
      pz.imagen_subida = r.url; div.replaceWith(crearTarjeta(cat, i, pz)); autoguardar(); mostrarAviso("Imagen generada");
    } catch (err) { btn.disabled = false; btn.textContent = txt; mostrarAviso("No se pudo generar"); }
  });
}

// ---------- Generar plan ----------
async function generarPlan() {
  const cont = $("#contenido");
  cont.innerHTML = '<div class="cargando"><div class="spinner"></div>Generando tu plan e investigando tendencias…<br>Puede tardar hasta un minuto.</div>';
  $("#btn-generar").disabled = true;
  try { plan = normalizarPlan(await api("POST", "/api/generar")); renderCabecera(); render(); mostrarAviso("Plan generado"); }
  catch (e) { cont.innerHTML = `<div class="vacio">No se pudo generar el plan.<br><small>${esc(e.message)}</small></div>`; }
  finally { $("#btn-generar").disabled = false; }
}

// ---------- Ajustes de perfil ----------
async function guardarPerfil() {
  const form = new FormData(); form.append("usuario", $("#ajuste-usuario").value);
  const f = $("#ajuste-foto").files[0]; if (f) form.append("foto", f);
  try { perfil = await api("POST", "/api/perfil", { form }); renderCabecera(); render();
    $("#panel-ajustes").classList.add("oculto"); mostrarAviso("Perfil actualizado");
  } catch (e) { mostrarAviso("No se pudo guardar el perfil"); }
}

// ---------- Eventos globales ----------
document.addEventListener("DOMContentLoaded", () => {
  $("#btn-login").addEventListener("click", hacerLogin);
  $("#clave").addEventListener("keydown", (e) => { if (e.key === "Enter") hacerLogin(); });
  $("#btn-generar").addEventListener("click", generarPlan);
  $("#tabs").addEventListener("click", (e) => {
    const b = e.target.closest(".tab"); if (!b) return;
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("activa"));
    b.classList.add("activa"); catActiva = b.dataset.cat; render();
  });
  $("#btn-ajustes").addEventListener("click", () => {
    $("#ajuste-usuario").value = perfil.usuario || ""; $("#ajuste-foto-prev").src = avatar();
    $("#panel-ajustes").classList.remove("oculto");
  });
  $("#cerrar-ajustes").addEventListener("click", () => $("#panel-ajustes").classList.add("oculto"));
  $("#ajuste-foto").addEventListener("change", (e) => { if (e.target.files[0]) $("#ajuste-foto-prev").src = URL.createObjectURL(e.target.files[0]); });
  $("#guardar-perfil").addEventListener("click", guardarPerfil);
  iniciarApp().catch(() => mostrarLogin());
});
