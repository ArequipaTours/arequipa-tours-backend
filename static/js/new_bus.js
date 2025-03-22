// new_bus.js

const pisosSelect = document.getElementById("pisos");
const floorInputsContainer = document.getElementById("floorInputs");
const seatContainer = document.getElementById("seatContainer");
const totalAsientosSpan = document.getElementById("totalAsientos");
const btnAddExtraSeat = document.getElementById("btnAddExtraSeat"); // Botón "Añadir Asiento Extra"

let floorsData = [];

/**
 * Genera los inputs (filas/columnas) para cada piso, en orden descendente (si 2 pisos => piso2, piso1).
 */
function generateFloorInputs() {
  const numPisos = parseInt(pisosSelect.value) || 1;
  floorInputsContainer.innerHTML = "";
  floorsData = [];

  for (let i = numPisos; i >= 1; i--) {
    const div = document.createElement("div");
    div.classList.add("floor-input-group");

    // "Piso i - Filas:"
    const labelFilas = document.createElement("label");
    labelFilas.innerText = `Piso ${i} - Filas:`;
    div.appendChild(labelFilas);

    const inputFilas = document.createElement("input");
    inputFilas.type = "number";
    inputFilas.min = "1";
    inputFilas.value = "2";
    inputFilas.required = true;
    inputFilas.classList.add("form-control");
    inputFilas.id = `filas_piso_${i}`;
    div.appendChild(inputFilas);

    const labelCols = document.createElement("label");
    labelCols.innerText = "Columnas:";
    labelCols.style.marginLeft = "10px";
    div.appendChild(labelCols);

    const inputCols = document.createElement("input");
    inputCols.type = "number";
    inputCols.min = "1";
    inputCols.value = "3";
    inputCols.required = true;
    inputCols.classList.add("form-control");
    inputCols.id = `columnas_piso_${i}`;
    div.appendChild(inputCols);

    floorInputsContainer.appendChild(div);

    floorsData.push({
      floor: i,
      filas: parseInt(inputFilas.value),
      columnas: parseInt(inputCols.value),
      seats: []
    });

    inputFilas.addEventListener("input", updateStructure);
    inputCols.addEventListener("input", updateStructure);
  }
  updateStructure();
}

/**
 * Calcula total de asientos con type="seat".
 */
function updateTotalSeats() {
  let total = 0;
  floorsData.forEach(floor => {
    floor.seats.forEach(seat => {
      if (seat.type === "seat") total++;
    });
  });
  totalAsientosSpan.textContent = total;
}

/**
 * Genera la estructura de asientos (filas × columnas) para cada piso,
 * preservando asientos extra (isExtra).
 */
function updateStructure() {
  seatContainer.innerHTML = "";

  // Leer filas/columnas actualizadas y retener asientos extra
  floorsData.forEach(floorData => {
    const fInput = document.getElementById(`filas_piso_${floorData.floor}`);
    const cInput = document.getElementById(`columnas_piso_${floorData.floor}`);
    floorData.filas = parseInt(fInput.value) || 1;
    floorData.columnas = parseInt(cInput.value) || 1;

    const extraSeats = floorData.seats.filter(s => s.isExtra);
    floorData.seats = extraSeats;
  });

  floorsData.forEach(floorData => {
    const pisoTitle = document.createElement("h5");
    pisoTitle.textContent = `Piso ${floorData.floor}`;
    pisoTitle.classList.add("text-center", "mt-3");
    seatContainer.appendChild(pisoTitle);

    for (let r = 0; r < floorData.filas; r++) {
      // Pasillo si r===2 y filas>2
      if (r === 2 && floorData.filas > 2) {
        const aisleRow = document.createElement("div");
        aisleRow.classList.add("aisle-row");
        aisleRow.style.height = "80px"; // Ajustar si deseas
        seatContainer.appendChild(aisleRow);
      }

      const rowDiv = document.createElement("div");
      rowDiv.classList.add("seat-row");

      for (let c = 0; c < floorData.columnas; c++) {
        const seatElem = document.createElement("div");
        seatElem.classList.add("seat-cell", "seat-cell-seat");

        const seatObj = {
          type: "seat",
          seatNumber: "",
          seatElement: seatElem,
          floor: floorData.floor,
          row: r,
          col: c,
          isExtra: false
        };
        floorData.seats.push(seatObj);

        seatElem.addEventListener("click", () => {
          showSeatMenu(seatElem, seatObj);
        });

        rowDiv.appendChild(seatElem);
      }
      seatContainer.appendChild(rowDiv);
    }

    // Re-append asientos extra
    floorData.seats.forEach(s => {
      if (s.isExtra) seatContainer.appendChild(s.seatElement);
    });
  });

  updateTotalSeats();
}

/**
 * Popup => cambiar 'type' (seat, bano, escalera, entrada) 
 * y si es seat => seatNumber manual.
 */
function showSeatMenu(seatDiv, seatObj) {
  const existingMenu = document.querySelector(".type-menu");
  if (existingMenu) existingMenu.remove();

  const menu = document.createElement("div");
  menu.classList.add("type-menu");
  menu.innerHTML = `
    <div style="background:#f5f5f5; padding:20px; border:1px solid #ccc; text-align:center;">
      <label>Tipo de Celda:</label>
      <select id="seatTypeSelect">
        <option value="seat">Asiento normal</option>
        <option value="bano">BAÑO</option>
        <option value="escalera">ESC</option>
        <option value="entrada">ENT</option>
      </select>
      <br><br>
      <div id="manualSeatNumberContainer" style="display:none; margin-bottom:10px;">
        <label>Número/Nombre Asiento:</label>
        <input type="text" id="manualSeatNumber" placeholder="Ej: 25B, A1..." style="margin-left:5px;">
      </div>
      <br>
      <button id="menuOkBtn" class="btn btn-primary me-2">OK</button>
      <button id="menuCancelBtn" class="btn btn-secondary">Cancelar</button>
    </div>
  `;
  document.body.appendChild(menu);

  const seatTypeSelect = menu.querySelector("#seatTypeSelect");
  const manualSeatNumberContainer = menu.querySelector("#manualSeatNumberContainer");
  const manualSeatNumberInput = menu.querySelector("#manualSeatNumber");
  seatTypeSelect.value = seatObj.type;

  function toggleSeatNumberInput() {
    if (seatTypeSelect.value === "seat") {
      manualSeatNumberContainer.style.display = "block";
    } else {
      manualSeatNumberContainer.style.display = "none";
    }
  }
  toggleSeatNumberInput();

  if (seatObj.seatNumber) {
    manualSeatNumberInput.value = seatObj.seatNumber;
  }

  seatTypeSelect.addEventListener("change", toggleSeatNumberInput);

  const btnOK = menu.querySelector("#menuOkBtn");
  const btnCancel = menu.querySelector("#menuCancelBtn");

  btnOK.addEventListener("click", () => {
    seatObj.type = seatTypeSelect.value;

    seatDiv.classList.remove("seat-cell-seat", "seat-cell-bano", "seat-cell-escalera", "seat-cell-entrada");
    seatDiv.style.backgroundColor = "";
    seatDiv.style.color = "#fff";
    seatDiv.textContent = "";

    if (seatObj.type === "seat") {
      const seatNum = manualSeatNumberInput.value.trim();
      if (!seatNum) {
        alert("Por favor, ingrese el número/identificador del asiento.");
        return; 
      }
      seatObj.seatNumber = seatNum;
      seatDiv.classList.add("seat-cell-seat");
      seatDiv.textContent = seatNum;
    } else {
      seatObj.seatNumber = "";
      seatDiv.classList.add("seat-cell-" + seatObj.type);
      seatDiv.style.backgroundColor = "#fff";
      seatDiv.style.color = "#000";
      if (seatObj.type === "bano") seatDiv.textContent = "BAÑO";
      else if (seatObj.type === "escalera") seatDiv.textContent = "ESC";
      else if (seatObj.type === "entrada") seatDiv.textContent = "ENT";
    }

    updateTotalSeats();
    document.body.removeChild(menu);
  });

  btnCancel.addEventListener("click", () => {
    document.body.removeChild(menu);
  });
}

/**
 * Validación antes de guardar:
 * - Campos básicos
 * - Filas/columnas
 * - seatNumber en asientos type="seat"
 */
function validateForm() {
  const placa = document.getElementById("placa").value.trim();
  const modelo = document.getElementById("modelo").value.trim();
  const propietario = document.getElementById("propietario").value.trim();
  const estado = document.getElementById("estado").value;
  const pisosVal = document.getElementById("pisos").value;

  // Sin "tipoServicio"
  if (!placa || !modelo || !propietario || !estado || !pisosVal) {
    showFloatingMessage("Complete todos los campos básicos.", "error");
    return false;
  }

  // Filas/columnas
  let valid = true;
  floorsData.forEach(floor => {
    const fInput = document.getElementById(`filas_piso_${floor.floor}`);
    const cInput = document.getElementById(`columnas_piso_${floor.floor}`);
    if (!fInput.value || !cInput.value) valid = false;
  });
  if (!valid) {
    showFloatingMessage("Complete la configuración de filas/columnas.", "error");
    return false;
  }

  // Asientos type="seat" => seatNumber no vacío
  for (const floor of floorsData) {
    for (const seat of floor.seats) {
      if (seat.type === "seat") {
        if (!seat.seatNumber || seat.seatNumber.trim() === "") {
          showFloatingMessage("Hay asientos 'seat' sin número manual.", "error");
          return false;
        }
      }
    }
  }

  return true;
}

/**
 * Mensaje flotante de error/éxito
 */
function showFloatingMessage(msg, type) {
  const div = document.createElement("div");
  div.className = "floating-message " + type + " show";
  div.textContent = msg;
  document.body.appendChild(div);

  setTimeout(() => {
    div.classList.remove("show");
    setTimeout(() => {
      document.body.removeChild(div);
    }, 500);
  }, 3000);
}

/**
 * Overlay de carga
 */
function showLoadingOverlay() {
  const overlay = document.getElementById("loadingOverlay");
  overlay.style.display = "flex";
}

/**
 * Creación de Asientos Extra (draggables)
 */
if (btnAddExtraSeat) {
  btnAddExtraSeat.addEventListener("click", () => {
    if (floorsData.length === 0) return;
    createDraggableSeat(floorsData[0]);
  });
}

function createDraggableSeat(floorData) {
  const seatElem = document.createElement("div");
  seatElem.classList.add("draggable-seat");
  seatElem.style.left = "50px";
  seatElem.style.top = "50px";

  // Botón "X" para eliminar
  const delBtn = document.createElement("button");
  delBtn.classList.add("delete-btn");
  delBtn.textContent = "X";
  delBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    seatContainer.removeChild(seatElem);
    floorData.seats = floorData.seats.filter(s => s !== seatObj);
    updateTotalSeats();
  });
  seatElem.appendChild(delBtn);

  const seatObj = {
    type: "seat",
    seatNumber: "",
    isExtra: true,
    posX: 50,
    posY: 50,
    floor: floorData.floor,
    seatElement: seatElem
  };

  floorData.seats.push(seatObj);

  makeElementDraggable(seatElem, seatObj);

  // Al hacer click => popup
  seatElem.addEventListener("click", (e) => {
    e.stopPropagation();
    showSeatMenu(seatElem, seatObj);
  });

  seatContainer.appendChild(seatElem);
  updateTotalSeats();
}

function makeElementDraggable(element, seatObj) {
  let offsetX = 0, offsetY = 0;
  let isDragging = false;

  element.addEventListener("mousedown", (e) => {
    isDragging = true;
    offsetX = e.clientX - parseInt(element.style.left);
    offsetY = e.clientY - parseInt(element.style.top);
    element.style.zIndex = 9999;
  });

  document.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    const rect = seatContainer.getBoundingClientRect();

    let newLeft = e.clientX - offsetX;
    let newTop = e.clientY - offsetY;

    newLeft = Math.max(0, Math.min(newLeft, rect.width - element.offsetWidth));
    newTop = Math.max(0, Math.min(newTop, rect.height - element.offsetHeight));

    element.style.left = newLeft + "px";
    element.style.top = newTop + "px";

    seatObj.posX = newLeft;
    seatObj.posY = newTop;
  });

  document.addEventListener("mouseup", () => {
    if (isDragging) {
      isDragging = false;
      element.style.zIndex = "";
    }
  });
}

/**
 * Botones Guardar/Cancelar
 */
const btnGuardar = document.getElementById("btnGuardar");
btnGuardar.addEventListener("click", (e) => {
  e.preventDefault();
  if (!validateForm()) return;

  showLoadingOverlay();

  const busData = {
    placa: document.getElementById("placa").value.trim(),
    // tipoServicio eliminado
    modelo: document.getElementById("modelo").value.trim(),
    propietario: document.getElementById("propietario").value.trim(),
    estado: document.getElementById("estado").value,
    pisos: document.getElementById("pisos").value,
    totalAsientos: totalAsientosSpan.textContent,
    estructura_asientos: floorsData.flatMap(f => f.seats)
  };

  document.getElementById("hiddenTotalAsientos").value = busData.totalAsientos;
  document.getElementById("hiddenEstructuraAsientos").value = JSON.stringify(busData.estructura_asientos);

  setTimeout(() => {
    document.getElementById("busForm").submit();
  }, 1500);
});

const btnCancelar = document.getElementById("btnCancelar");
btnCancelar.addEventListener("click", () => {
  window.history.back();
});

/**
 * Inicializar
 */
generateFloorInputs();
pisosSelect.addEventListener("change", generateFloorInputs);
