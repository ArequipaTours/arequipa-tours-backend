// venta_boletos.js

// Se asume que las variables globales "viajeId" y "userOrigin" ya están definidas en el HTML

// Arreglo global para el carrito
let cart = [];
// Asiento actual al abrir el modal de datos del pasajero
let currentSeatName = null;

// =========================
// FUNCIONES PRINCIPALES
// =========================

// Clic en un asiento disponible
function onSeatClick(seatName) {
  if (cart.find(item => item.seatName === seatName)) {
    openMessageModal("Atención", "Este asiento ya ha sido reservado.");
    return;
  }
  currentSeatName = seatName;
  document.getElementById("seatModal").style.display = "block";
  document.getElementById("seatName").innerText = seatName;
}

// Cerrar modal de pasajero
function closeModal() {
  document.getElementById("seatModal").style.display = "none";
  document.getElementById("seatForm").reset();
  currentSeatName = null;
}

// Al enviar formulario de pasajero
document.getElementById("seatForm").addEventListener("submit", function(e) {
  e.preventDefault();
  if (!currentSeatName) return;
  
  // Convertir a mayúsculas
  const passengerName = document.getElementById("name").value.toUpperCase();
  const ci = document.getElementById("id").value.toUpperCase();
  const edad = document.getElementById("edad").value;
  const phone = document.getElementById("phone").value;
  const pais = document.getElementById("pais").value.toUpperCase();
  const price = document.getElementById("price").value;
  
  const seatObj = { 
    seatName: currentSeatName, 
    passengerName, 
    ci, 
    edad, 
    phone, 
    pais, 
    price 
  };
  
  const existingIndex = cart.findIndex(item => item.seatName === currentSeatName);
  if (existingIndex >= 0) {
    cart[existingIndex] = seatObj;
  } else {
    cart.push(seatObj);
  }
  
  markSeatAsReserved(currentSeatName);
  renderCartItems();
  closeModal();
});

// =========================
// MARCAR / DESMARCAR ASIENTOS
// =========================

function markSeatAsReserved(seatName) {
  let seatElem = document.querySelector(`td.seat[data-seat-name="${seatName}"]`) ||
                 document.querySelector(`div.seat[data-seat-name="${seatName}"]`);
  if (seatElem) {
    seatElem.classList.remove("available");
    seatElem.classList.add("reserved");
    seatElem.style.backgroundColor = "#FFD700"; // Amarillo
  }
}

function unmarkSeat(seatName) {
  let seatElem = document.querySelector(`td.seat[data-seat-name="${seatName}"]`) ||
                 document.querySelector(`div.seat[data-seat-name="${seatName}"]`);
  if (seatElem) {
    seatElem.classList.remove("reserved");
    seatElem.classList.add("available");
    seatElem.style.backgroundColor = "";
  }
}

// =========================
// RENDERIZAR CARRITO
// =========================

function renderCartItems() {
  const cartItemsDiv = document.getElementById("cartItems");
  cartItemsDiv.innerHTML = "";
  if (cart.length === 0) {
    cartItemsDiv.innerHTML = "<p>No hay asientos reservados.</p>";
    return;
  }
  cart.forEach(item => {
    const p = document.createElement("p");
    p.innerHTML = `
      <strong>Asiento:</strong> ${item.seatName} |
      <strong>Nombre:</strong> ${item.passengerName} |
      <strong>Precio:</strong> ${item.price} Bs
      <button class="delete" style="margin-left:10px;">Eliminar</button>
    `;
    p.querySelector(".delete").addEventListener("click", () => {
      removeFromCart(item.seatName);
      openConfirmModal();
    });
    cartItemsDiv.appendChild(p);
  });
}

function removeFromCart(seatName) {
  cart = cart.filter(item => item.seatName !== seatName);
  unmarkSeat(seatName);
  renderCartItems();
}

// =========================
// CONFIRMACIÓN DE COMPRA
// =========================

function openConfirmModal() {
  if (cart.length === 0) {
    openMessageModal("Atención", "No hay asientos en el carrito.");
    return;
  }
  
  const summaryTableBody = document.getElementById("summaryTable").querySelector("tbody");
  summaryTableBody.innerHTML = "";
  let total = 0;
  cart.forEach(item => {
    total += parseFloat(item.price);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${item.seatName}</td>
      <td>${item.passengerName}</td>
      <td>${item.price}</td>
      <td><button class="delete" style="margin-left:10px;">Eliminar</button></td>
    `;
    tr.querySelector(".delete").addEventListener("click", () => {
      removeFromCart(item.seatName);
      openConfirmModal();
    });
    summaryTableBody.appendChild(tr);
  });
  document.getElementById("totalPrice").innerText = total.toFixed(2);
  document.getElementById("confirmModal").style.display = "block";
}

function closeConfirmModal() {
  document.getElementById("confirmModal").style.display = "none";
}

function confirmPurchase() {
  const paymentMethodElem = document.querySelector('input[name="payment"]:checked');
  if (!paymentMethodElem) {
    openMessageModal("Atención", "Debe seleccionar un medio de pago.");
    return;
  }
  const paymentMethod = paymentMethodElem.value;
  
  const carrilInput = document.getElementById("carrilInput");
  const carrilValue = carrilInput.value.trim();
  if (!carrilValue) {
    openMessageModal("Atención", "Debe ingresar el carril.");
    return;
  }
  
  // Leer el estado del toggle para "El Alto"
  const elAltoToggle = document.getElementById("elAltoToggle");
  let subOrigenValue = "";
  if (elAltoToggle && elAltoToggle.checked) {
    subOrigenValue = "El Alto";
  }
  
  const payload = {
    asientos: cart,
    payment: paymentMethod,
    carril: carrilValue,
    subOrigen: subOrigenValue
  };
  
  closeConfirmModal();
  
  const loadingModal = document.getElementById("loadingModal");
  loadingModal.style.display = "block";
  
  fetch(`/ventanilla/confirmar_impresion/${viajeId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  })
  .then(response => response.json())
  .then(data => {
    loadingModal.style.display = "none";
    if (data.success) {
      showConfirmationMessage("Compra confirmada.");
      cart = [];
      renderCartItems();
      window.open(`/ventanilla/boletos/pdf/${data.venta_id}`, '_blank');
      setTimeout(() => { window.location.reload(); }, 1000);
    } else {
      if (data.msg === "Viaje ya cerrado") {
        openMessageModal("Error", "El viaje ya se encuentra cerrado. La página se recargará.");
        setTimeout(() => { window.location.reload(); }, 3000);
      } else {
        openMessageModal("Error", data.msg);
      }
    }
  })
  .catch(err => {
    loadingModal.style.display = "none";
    console.error("Error al confirmar la compra:", err);
    openMessageModal("Error", "Error en la compra.");
  });
}

// =========================
// MANEJO DE MODALES
// =========================

function openPrintModal() {
  document.getElementById("printModal").style.display = "block";
}

function closePrintModal() {
  document.getElementById("printModal").style.display = "none";
  window.location.reload();
}

function openMessageModal(title, message) {
  document.getElementById("messageTitle").innerText = title;
  document.getElementById("messageBody").innerText = message;
  document.getElementById("messageModal").style.display = "block";
}

function closeMessageModal() {
  document.getElementById("messageModal").style.display = "none";
}

window.addEventListener("click", function(event) {
  const modalIds = ["seatModal", "confirmModal", "loadingModal", "printModal", "messageModal"];
  modalIds.forEach(id => {
    const modal = document.getElementById(id);
    if (event.target === modal) {
      if (id === "seatModal") closeModal();
      if (id === "confirmModal") closeConfirmModal();
      if (id === "printModal") closePrintModal();
      if (id === "messageModal") closeMessageModal();
    }
  });
});

document.querySelector('.confirm').addEventListener('click', function() {
  openConfirmModal();
});

function showConfirmationMessage(message) {
  const confirmationMessage = document.getElementById("confirmationMessage");
  const confirmationText = document.getElementById("confirmationText");
  confirmationText.innerText = message;
  confirmationMessage.style.display = "block";
  setTimeout(() => {
    confirmationMessage.style.display = "none";
  }, 3000);
}

// =========================
// ACTUALIZAR DINÁMICAMENTE
// =========================

function updateJourneyInfo() {
  const container = document.getElementById("journeyInfo");
  if (!container) return;
  
  const originalOrigen = container.getAttribute("data-origen");
  const originalDestino = container.getAttribute("data-destino");
  const originalFecha = container.getAttribute("data-fecha");
  const originalHora = container.getAttribute("data-hora");
  
  const elAltoToggle = document.getElementById("elAltoToggle");
  let displayOrigen = originalOrigen;
  let displayHora = originalHora;
  
  if (elAltoToggle && elAltoToggle.checked) {
    displayOrigen = "El Alto";
    const parts = originalHora.split(":");
    if (parts.length === 2) {
      let hour = parseInt(parts[0]);
      let minute = parseInt(parts[1]);
      minute += 30;
      if (minute >= 60) {
        minute -= 60;
        hour += 1;
      }
      // Ajustar formato HH:MM con ceros
      displayHora = (hour < 10 ? "0" + hour : hour) + ":" + (minute < 10 ? "0" + minute : minute);
    }
  }
  
  const journeyTextElem = document.getElementById("journeyText");
  if (journeyTextElem) {
    journeyTextElem.innerHTML = `<strong>
      Origen: ${displayOrigen} &nbsp;&nbsp;
      Destino: ${originalDestino} <br>
      Fecha: ${originalFecha} &nbsp;&nbsp; Hora: ${displayHora}
    </strong>`;
  }
}

// Cuando cargue el DOM
document.addEventListener("DOMContentLoaded", function() {
  const elAltoToggle = document.getElementById("elAltoToggle");
  if (elAltoToggle && typeof userOrigin !== "undefined") {
    // Si el operador es de El Alto, encender toggle
    if (userOrigin.trim().toLowerCase() === "el alto") {
      elAltoToggle.checked = true;
    }
    // Al cambiar el toggle, actualizar la info
    elAltoToggle.addEventListener("change", updateJourneyInfo);
  }
  
  // Llamar una vez para mostrar la info original
  updateJourneyInfo();
  
  // Convertir a mayúsculas inputs de texto
  const textInputs = document.querySelectorAll("#seatForm input[type='text']");
  textInputs.forEach(input => {
    input.addEventListener("input", function() {
      this.value = this.value.toUpperCase();
    });
  });
});
