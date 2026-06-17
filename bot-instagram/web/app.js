// ===== Panel de contenido (Fase 1) — lógica del frontend =====

const PIXEL = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==";
const MESES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];

let plan = null;        // el plan completo (de plan.json)
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
  if (!r.ok) {
    let d = "";
    try { d = (await r.json()).detail; } catch (e) {}
    throw new Error(d || ("Error " + r.status));
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r.text();
}

// ---------- Utilidades ----------
function esc(t) { return (t || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function avatar() { return perfil.foto_url || PIXEL; }
function usuario() { return perfil.usuario || "tu_usuario"; }

function fechaTexto(fecha, hora) {
  if (!fecha) return hora || "";
  const p = fecha.split("-");
  if (p.length === 3) return `${parseInt(p[2], 10)} ${MESES[parseInt(p[1], 10) - 1]}` + (hora ? ` · ${hora}` : "");
  return fecha + (hora ? ` · ${hora}` : "");
}

function mostrarAviso(txt) {
  const a = $("#aviso");
  a.textContent = txt;
  a.classList.remove("oculto");
  clearTimeout(a._t);
  a._t = setTimeout(() => a.classList.add("oculto"), 1600);
}

// ---------- Guardado ----------
function autoguardar() {
  clearTimeout(guardarTimer);
  guardarTimer = setTimeout(async () => {
    try { await api("PUT", "/api/plan", { json: plan }); mostrarAviso("Guardado"); }
    catch (e) { mostrarAviso("No se pudo guardar"); }
  }, 800);
}

// ---------- Login ----------
function mostrarLogin() {
  $("#pantalla-app").classList.add("oculto");
  $("#pantalla-login").classList.remove("oculto");
}

async function hacerLogin() {
  const form = new FormData();
  form.append("password", $("#clave").value);
  try {
    await api("POST", "/api/login", { form });
    $("#login-error").classList.add("oculto");
    await iniciarApp();
  } catch (e) {
    const er = $("#login-error");
    er.textContent = "Contraseña incorrecta";
    er.classList.remove("oculto");
  }
}

// ---------- Inicio ----------
async function iniciarApp() {
  perfil = await api("GET", "/api/perfil");
  plan = await api("GET", "/api/plan");
  $("#pantalla-login").classList.add("oculto");
  $("#pantalla-app").classList.remove("oculto");
  renderCabecera();
  render();
}

function renderCabecera() {
  $("#perfil-usuario").textContent = usuario();
  $("#perfil-foto").src = avatar();
  let resumen = "Sin plan todavía";
  if (plan && !plan.vacio) {
    const p = (plan.publicaciones || []).length, h = (plan.historias || []).length,
          n = (plan.notas || []).length, i = (plan.instantaneas || []).length;
    resumen = `${p} publicaciones · ${h} historias · ${n} notas · ${i} instantáneas`;
  }
  $("#plan-resumen").textContent = resumen;
}

// ---------- Render principal ----------
function render() {
  const cont = $("#contenido");
  cont.innerHTML = "";
  if (!plan || plan.vacio) {
    cont.innerHTML = '<div class="vacio">Aún no hay plan.<br>Toca <b>Generar plan</b> para crear el de esta semana.</div>';
    return;
  }
  const lista = plan[catActiva] || [];
  if (!lista.length) {
    cont.innerHTML = `<div class="vacio">No hay ${catActiva} en el plan.</div>`;
    return;
  }
  lista.forEach((pieza, i) => cont.appendChild(crearTarjeta(catActiva, i, pieza)));
}

// ---------- Construcción de tarjetas ----------
function crearTarjeta(cat, i, pz) {
  const div = document.createElement("div");
  div.className = "tarjeta";
  if (cat === "publicaciones") div.innerHTML = (pz.tipo === "idea_reel")
      ? vistaVertical("reel", pz) + editorPublicacion(pz, i)
      : vistaFeed(pz) + editorPublicacion(pz, i);
  else if (cat === "historias") div.innerHTML = vistaVertical("historia", pz) + editorHistoria(pz, i);
  else if (cat === "notas") div.innerHTML = vistaNota(pz) + editorNota(pz, i);
  else if (cat === "instantaneas") div.innerHTML = vistaVertical("instantanea", pz) + editorInstantanea(pz, i);
  wirePieza(div, cat, i, pz);
  return div;
}

function metaHTML(cat, pz) {
  let badge = cat.slice(0, -1);
  let clase = "badge";
  if (pz.tipo === "idea_reel") { badge = "Reel"; clase += " reel"; }
  else if (pz.tipo) badge = pz.tipo;
  const ia = pz.directiva_imagen && pz.directiva_imagen.tipo === "GENERAR_IA";
  return `<div class="tarjeta-meta">
    <span class="${clase}">${esc(badge)}${ia ? ' · IA' : ''}</span>
    <span class="cuando">${esc(fechaTexto(pz.fecha, pz.hora))}</span>
  </div>`;
}

function imagenPreview(pz) {
  if (pz.imagen_subida) return `<img src="${esc(pz.imagen_subida)}" alt="" />`;
  const ia = pz.directiva_imagen && pz.directiva_imagen.tipo === "GENERAR_IA";
  return `<div class="ph">${ia ? "Imagen con IA<br>(se generará en la Fase 2)" : "Sube tu foto desde el editor"}</div>`;
}

function vistaFeed(pz) {
  return metaHTML("publicaciones", pz) + `<div class="ig">
    <div class="ig-cab">
      <img class="av" src="${avatar()}" alt="" />
      <div><div class="u">${esc(usuario())}</div><div class="loc">Lima, Perú</div></div>
    </div>
    <div class="ig-img">${imagenPreview(pz)}</div>
    <div class="ig-acc"><i>♡</i><i>💬</i><i>➤</i><i class="der">🔖</i></div>
    <div class="ig-pie">
      <span class="u">${esc(usuario())}</span> <span class="cap">${esc(pz.caption)}</span>
      <div class="ig-hashtags">${esc((pz.hashtags || []).map(h => "#" + h).join(" "))}</div>
      <div class="ig-hora">${esc(fechaTexto(pz.fecha, pz.hora))}</div>
    </div>
  </div>`;
}

function vistaVertical(tipo, pz) {
  const cat = tipo === "historia" ? "historias" : (tipo === "instantanea" ? "instantaneas" : "publicaciones");
  const fondo = pz.imagen_subida ? `<img src="${esc(pz.imagen_subida)}" alt="" />` : (tipo === "reel" ? "▶" : "");
  const textoOverlay = tipo === "reel" ? pz.caption : (pz.texto_en_pantalla || pz.idea || "");
  let sticker = "";
  if (tipo === "historia" && pz.interaccion && pz.interaccion !== "ninguno") {
    const ops = (pz.interaccion === "encuesta") ? `<div class="ops"><span>Sí</span><span>No</span></div>`
      : (pz.interaccion === "cuestionario") ? `<div class="ops"><span>A</span><span>B</span></div>` : "";
    sticker = `<div class="sticker"><div class="preg">${esc(pz.idea || "")}</div>${ops}</div>`;
  }
  const marca = tipo === "reel" ? `<div class="reel-marca"><i>♡</i><i>💬</i><i>➤</i></div>` : "";
  return metaHTML(cat, pz) + `<div class="vert">
    <div class="vert-bg">${fondo}</div>
    <div class="vert-top">
      <div class="vert-prog"><span class="on"></span><span></span><span></span></div>
      <div class="vert-head"><img class="av" src="${avatar()}" alt="" />
        <span class="u">${esc(usuario())}</span><span class="t">${esc(pz.hora || "")}</span></div>
    </div>
    ${marca}
    <div class="vert-cuerpo">
      <div class="vert-texto">${esc(textoOverlay)}</div>
      ${sticker}
    </div>
  </div>`;
}

function vistaNota(pz) {
  return `<div class="nota-burbuja">${esc(pz.texto)}</div>
    <div class="nota-pie">Nota · ${esc(fechaTexto(pz.fecha))}</div>`;
}

// ---------- Editores ----------
function directivaIA(pz) {
  if (!pz.directiva_imagen) return "";
  if (pz.directiva_imagen.tipo === "GENERAR_IA")
    return `<div class="directiva-ia"><b>Prompt de imagen:</b> ${esc(pz.directiva_imagen.prompt_ia)}</div>
      <div class="editor-fila"><button class="btn-borde" disabled>Generar imagen (Fase 2)</button></div>`;
  return `<div class="directiva-ia"><b>Qué fotografiar:</b> ${esc(pz.directiva_imagen.descripcion_foto)}</div>
    ${botonSubir()}`;
}

function botonSubir() {
  return `<div class="editor-fila"><label class="btn-borde">📷 Subir foto
    <input type="file" class="subir" accept="image/*" hidden /></label></div>`;
}

function editorPublicacion(pz, i) {
  return `<div class="editor">
    <label>Idea</label><div class="directiva-ia">${esc(pz.idea)}</div>
    <label style="margin-top:8px;">Caption</label>
    <textarea class="f-caption">${esc(pz.caption)}</textarea>
    <label style="margin-top:8px;">Hashtags (separados por espacio)</label>
    <textarea class="f-hashtags" style="min-height:44px;">${esc((pz.hashtags || []).join(" "))}</textarea>
    ${directivaIA(pz)}
  </div>`;
}

function editorHistoria(pz, i) {
  const ops = ["encuesta","pregunta","cuestionario","cuenta_regresiva","control_deslizante","ninguno"];
  return `<div class="editor">
    <label>Idea</label><div class="directiva-ia">${esc(pz.idea)}</div>
    <label style="margin-top:8px;">Texto en pantalla</label>
    <textarea class="f-texto" style="min-height:48px;">${esc(pz.texto_en_pantalla)}</textarea>
    <label style="margin-top:8px;">Interacción (sticker)</label>
    <select class="f-interaccion" style="width:100%;padding:10px;background:#000;color:#fff;border:1px solid #262626;border-radius:8px;">
      ${ops.map(o => `<option value="${o}" ${pz.interaccion === o ? "selected" : ""}>${o}</option>`).join("")}
    </select>
    ${directivaIA(pz)}
  </div>`;
}

function editorNota(pz, i) {
  return `<div class="editor">
    <label>Texto de la nota (máx. 60)</label>
    <textarea class="f-nota" maxlength="60" style="min-height:44px;">${esc(pz.texto)}</textarea>
    <div class="contador"><span class="cont">${(pz.texto || "").length}</span>/60</div>
  </div>`;
}

function editorInstantanea(pz, i) {
  return `<div class="editor">
    <label>Idea del momento</label>
    <textarea class="f-idea" style="min-height:44px;">${esc(pz.idea)}</textarea>
    <label style="margin-top:8px;">Qué captar (foto en vivo, tú la tomas)</label>
    <textarea class="f-desc" style="min-height:44px;">${esc(pz.descripcion_foto)}</textarea>
    ${botonSubir()}
  </div>`;
}

// ---------- Conexión de eventos por tarjeta ----------
function wirePieza(div, cat, i, pz) {
  const cap = div.querySelector(".f-caption");
  if (cap) cap.addEventListener("input", () => {
    pz.caption = cap.value;
    const n = div.querySelector(".cap") || div.querySelector(".vert-texto");
    if (n) n.textContent = cap.value;
    autoguardar();
  });
  const ht = div.querySelector(".f-hashtags");
  if (ht) ht.addEventListener("input", () => {
    pz.hashtags = ht.value.split(/\s+/).map(s => s.replace(/^#/, "")).filter(Boolean);
    const n = div.querySelector(".ig-hashtags");
    if (n) n.textContent = pz.hashtags.map(h => "#" + h).join(" ");
    autoguardar();
  });
  const tx = div.querySelector(".f-texto");
  if (tx) tx.addEventListener("input", () => {
    pz.texto_en_pantalla = tx.value;
    const n = div.querySelector(".vert-texto");
    if (n) n.textContent = tx.value;
    autoguardar();
  });
  const sel = div.querySelector(".f-interaccion");
  if (sel) sel.addEventListener("change", () => {
    pz.interaccion = sel.value;
    const nueva = crearTarjeta(cat, i, pz);
    div.replaceWith(nueva);
    autoguardar();
  });
  const nota = div.querySelector(".f-nota");
  if (nota) nota.addEventListener("input", () => {
    pz.texto = nota.value;
    const n = div.querySelector(".nota-burbuja"); if (n) n.textContent = nota.value;
    const c = div.querySelector(".cont"); if (c) c.textContent = nota.value.length;
    autoguardar();
  });
  const idea = div.querySelector(".f-idea");
  if (idea) idea.addEventListener("input", () => {
    pz.idea = idea.value;
    const n = div.querySelector(".vert-texto"); if (n) n.textContent = idea.value;
    autoguardar();
  });
  const desc = div.querySelector(".f-desc");
  if (desc) desc.addEventListener("input", () => { pz.descripcion_foto = desc.value; autoguardar(); });

  const subir = div.querySelector(".subir");
  if (subir) subir.addEventListener("change", async () => {
    if (!subir.files.length) return;
    const form = new FormData();
    form.append("categoria", cat);
    form.append("indice", i);
    form.append("foto", subir.files[0]);
    try {
      mostrarAviso("Subiendo…");
      const r = await api("POST", "/api/subir", { form });
      pz.imagen_subida = r.url;
      const nueva = crearTarjeta(cat, i, pz);
      div.replaceWith(nueva);
      autoguardar();
      mostrarAviso("Foto subida");
    } catch (e) { mostrarAviso("No se pudo subir"); }
  });
}

// ---------- Generar plan ----------
async function generarPlan() {
  const cont = $("#contenido");
  cont.innerHTML = '<div class="cargando"><div class="spinner"></div>Generando tu plan e investigando tendencias…<br>Puede tardar hasta un minuto.</div>';
  $("#btn-generar").disabled = true;
  try {
    plan = await api("POST", "/api/generar");
    renderCabecera();
    render();
    mostrarAviso("Plan generado");
  } catch (e) {
    cont.innerHTML = `<div class="vacio">No se pudo generar el plan.<br><small>${esc(e.message)}</small></div>`;
  } finally {
    $("#btn-generar").disabled = false;
  }
}

// ---------- Ajustes de perfil ----------
async function guardarPerfil() {
  const form = new FormData();
  form.append("usuario", $("#ajuste-usuario").value);
  const f = $("#ajuste-foto").files[0];
  if (f) form.append("foto", f);
  try {
    perfil = await api("POST", "/api/perfil", { form });
    renderCabecera();
    render();
    $("#panel-ajustes").classList.add("oculto");
    mostrarAviso("Perfil actualizado");
  } catch (e) { mostrarAviso("No se pudo guardar el perfil"); }
}

// ---------- Eventos globales ----------
document.addEventListener("DOMContentLoaded", () => {
  $("#btn-login").addEventListener("click", hacerLogin);
  $("#clave").addEventListener("keydown", (e) => { if (e.key === "Enter") hacerLogin(); });
  $("#btn-generar").addEventListener("click", generarPlan);

  $("#tabs").addEventListener("click", (e) => {
    const b = e.target.closest(".tab");
    if (!b) return;
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("activa"));
    b.classList.add("activa");
    catActiva = b.dataset.cat;
    render();
  });

  $("#btn-ajustes").addEventListener("click", () => {
    $("#ajuste-usuario").value = perfil.usuario || "";
    $("#ajuste-foto-prev").src = avatar();
    $("#panel-ajustes").classList.remove("oculto");
  });
  $("#cerrar-ajustes").addEventListener("click", () => $("#panel-ajustes").classList.add("oculto"));
  $("#ajuste-foto").addEventListener("change", (e) => {
    if (e.target.files[0]) $("#ajuste-foto-prev").src = URL.createObjectURL(e.target.files[0]);
  });
  $("#guardar-perfil").addEventListener("click", guardarPerfil);

  // Arranque: ¿hay sesión?
  iniciarApp().catch(() => mostrarLogin());
});
