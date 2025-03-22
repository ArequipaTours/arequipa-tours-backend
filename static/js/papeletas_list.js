/******************************************************
  Variables para la paginación y filtros
******************************************************/
let skip = 0;
const limit = 10;
let reachedEnd = false;
let loading = false;

// Variables para los filtros de búsqueda
let currentOrigen = "";
let currentDestino = "";
let currentFecha = "";

/******************************************************
  Carga inicial al cargar el DOM
******************************************************/
document.addEventListener("DOMContentLoaded", function() {
  loadData();
});

/******************************************************
  Botones "Cargar más" y "Buscar"
******************************************************/
document.getElementById("btnLoadMore").addEventListener("click", function() {
  loadData();
});

document.getElementById("btnBuscar").addEventListener("click", function() {
  currentOrigen = document.getElementById("origenSelect").value.trim();
  currentDestino = document.getElementById("destinoSelect").value.trim();
  currentFecha = document.getElementById("fechaInput").value.trim();

  skip = 0;
  reachedEnd = false;
  document.getElementById("papeletasBody").innerHTML = "";
  loadData();
});

/******************************************************
  loadData(): Cargar un chunk (skip, limit) con filtros
******************************************************/
function loadData() {
  if (reachedEnd || loading) return;
  loading = true;
  showLoadingOverlay();

  const url = `/papeletas/data?skip=${skip}&limit=${limit}` +
              `&origen=${encodeURIComponent(currentOrigen)}` +
              `&destino=${encodeURIComponent(currentDestino)}` +
              `&fecha=${encodeURIComponent(currentFecha)}`;

  fetch(url)
    .then(res => res.json())
    .then(response => {
      hideLoadingOverlay();
      loading = false;
      if (!response.success) {
        showFloatMessage("Error al obtener datos.", true);
        return;
      }
      const rows = response.data;
      if (rows.length < limit) {
        reachedEnd = true;
      }
      appendRows(rows);
      skip += rows.length;
    })
    .catch(err => {
      hideLoadingOverlay();
      loading = false;
      showFloatMessage("Error de comunicación: " + err, true);
    });
}

/******************************************************
  Insertar filas en <tbody id="papeletasBody">
******************************************************/
function appendRows(rows) {
  const tbody = document.getElementById("papeletasBody");
  rows.forEach(pap => {
    const tr = document.createElement("tr");

    // ✅ Lógica para diferenciar entre La Paz y El Alto
    let isGenerado = false;
    let canImprimir = false;

    if (pap.origen === "El Alto") {
      isGenerado = pap.estado_el_alto === "generado";
      canImprimir = pap.papeletaElAlto === true;
    } else {
      isGenerado = pap.estado === "generado";
      canImprimir = pap.papeleta === true;
    }

    const estadoClass = isGenerado ? "estado-cell generado" : "";
    const btnGenerarDisabled = canImprimir ? "disabled" : "";
    const btnImprimirDisabled = canImprimir ? "" : "disabled";

    tr.innerHTML = `
      <td>${pap.chofer}</td>
      <td>${pap.bus}</td>
      <td>${pap.origen}</td>
      <td>${pap.destino}</td>
      <td>${pap.fecha}</td>
      <td>${pap.hora}</td>
      <td class="${estadoClass}">${isGenerado ? 'generado' : pap.estado}</td>
      <td>
        <button class="btn-accion btn-imprimir"
                id="btnImprimir_${pap.viaje_id}_${pap.origen.replace(/\s/g, '')}"
                ${btnImprimirDisabled}
                onclick="imprimirPapeleta('${pap.viaje_id}', '${pap.origen}')">
          Imprimir
        </button>
        <button class="btn-accion btn-generar"
                id="btnGenerar_${pap.viaje_id}_${pap.origen.replace(/\s/g, '')}"
                ${btnGenerarDisabled}
                onclick="openGenerateModal('${pap.viaje_id}', '${pap.origen}')">
          Generar
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

/******************************************************
  Mostrar / ocultar overlay de carga
******************************************************/
function showLoadingOverlay() {
  document.getElementById("loadingOverlay").style.display = "block";
}
function hideLoadingOverlay() {
  document.getElementById("loadingOverlay").style.display = "none";
}

/******************************************************
  Mensajes flotantes
******************************************************/
function showFloatMessage(text, isError=false) {
  const floatMsg = document.getElementById("floatMsg");
  floatMsg.innerText = text;
  if (isError) {
    floatMsg.classList.add("error");
  } else {
    floatMsg.classList.remove("error");
  }
  floatMsg.style.display = "block";
  setTimeout(() => {
    floatMsg.style.display = "none";
  }, 3000);
}

/******************************************************
  Modal "Generar"
******************************************************/
let currentViajeId = null;
let currentOrigenPapeleta = null;

function openGenerateModal(viajeId, origen) {
  currentViajeId = viajeId;
  currentOrigenPapeleta = origen;
  document.getElementById("inputComision").value = "";
  document.getElementById("inputPeaje").value = "";
  document.getElementById("generateModal").style.display = "block";
}
function closeGenerateModal() {
  document.getElementById("generateModal").style.display = "none";
  currentViajeId = null;
  currentOrigenPapeleta = null;
}

/******************************************************
  confirmGenerate => POST /papeleta/liquidacion/generate/<viajeId>
******************************************************/
function confirmGenerate() {
  const comVal = document.getElementById("inputComision").value.trim();
  const peajeVal = document.getElementById("inputPeaje").value.trim() || "0";
  const pct = parseFloat(comVal);
  const peaje = parseFloat(peajeVal);

  if (isNaN(pct) || pct < 0 || pct > 100) {
    showFloatMessage("Porcentaje inválido (0 - 100).", true);
    return;
  }
  if (isNaN(peaje) || peaje < 0) {
    showFloatMessage("Peaje inválido (>= 0).", true);
    return;
  }

  showLoadingOverlay();
  fetch(`/papeleta/liquidacion/generate/${currentViajeId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ comision: pct, peaje: peaje, origen: currentOrigenPapeleta })
  })
  .then(res => res.json())
  .then(data => {
    hideLoadingOverlay();
    if (data.success) {
      showFloatMessage("¡Papeleta generada con éxito!");

      const origenKey = currentOrigenPapeleta.replace(/\s/g, '');
      const btnImp = document.getElementById("btnImprimir_" + currentViajeId + "_" + origenKey);
      if (btnImp) btnImp.disabled = false;

      const btnGen = document.getElementById("btnGenerar_" + currentViajeId + "_" + origenKey);
      if (btnGen) btnGen.disabled = true;

      const row = btnImp ? btnImp.closest("tr") : null;
      if (row) {
        const tdEstado = row.querySelector("td:nth-child(7)");
        if (tdEstado) {
          tdEstado.textContent = "generado";
          tdEstado.classList.add("estado-cell", "generado");
        }
      }

      closeGenerateModal();
    } else {
      showFloatMessage("Error generando la papeleta: " + (data.msg || "Desconocido"), true);
    }
  })
  .catch(err => {
    hideLoadingOverlay();
    showFloatMessage("Error de comunicación: " + err, true);
  });
}

/******************************************************
  Imprimir => GET /papeleta/liquidacion/print/<viajeId>
******************************************************/
function imprimirPapeleta(viajeId, origen) {
  const origenKey = origen.replace(/\s/g, '');
  window.location.href = `/papeleta/liquidacion/print/${viajeId}?origen=${origenKey}`;
}
